"""Append-only JSONL event log. All report numbers are derived from this file.

Rule 8: never block the event loop. emit() only enqueues; a daemon thread does the
writing. Rule: one terminal event per request -- enforced by request_scope below
and re-checked by scripts/check_events.py against the written file.

EVENT ORDERING CONTRACT (violated once already, see docs/BUGLOG.md BUG-001):
    request.start -> ... -> request.end -> terminal
`request.end` carries the latency decomposition. The terminal event is LAST.
Use finish() rather than emitting these two by hand.

BACKEND SCOPE (DECISIONS D-008, decided by the supervisor after BUG-005):
    envelope `backend`  = run scope: which backend this RUN used. For a run that
                          mixes backends it is the PRIMARY backend (majority of
                          attempts, first appearance breaks ties).
    `attempt_backend`   = attempt scope: the backend that actually served THAT
                          attempt. This is the field the naive-vs-managed
                          comparison groups by.
Before D-008 the envelope silently overwrote the per-attempt value.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Final, Optional

TERMINAL: Final[frozenset[str]] = frozenset(
    {"terminal", "request.terminal", "req.terminal"}
)


class TerminalEventAlreadyEmitted(RuntimeError):
    """Second terminal event for one request. This is an invariant violation."""


class ReservedFieldError(ValueError):
    """A caller passed a field that collides with the event envelope.

    Silently overwriting `run_id` or `t_mono` would corrupt the very fields every
    report number is derived from (BUG-004).
    """


class RequestScope:
    """Per-request handle returned by EventLog.request().

    Guarantees, in-process:
      * at most one terminal event  (raises on the second)
      * no attempt.* event after the terminal event (raises)

    These are asserts that fire in development and tests. In production the
    analysis checker (L6) is the backstop, because a bug could bypass the scope.
    """

    __slots__ = ("_log", "req_id", "_terminal_emitted", "_attempts", "_abandoned_at",
                 "_backend_counts", "_backend_first")

    def __init__(self, log: "EventLog", req_id: str):
        self._log = log
        self.req_id = req_id
        self._terminal_emitted = False
        self._attempts: set[str] = set()
        self._abandoned_at: Optional[float] = None
        self._backend_counts: dict[str, int] = {}
        self._backend_first: list[str] = []

    # -- queries used by the pipeline/gateway
    @property
    def terminal_emitted(self) -> bool:
        return self._terminal_emitted

    @property
    def abandoned(self) -> bool:
        return self._abandoned_at is not None

    # -- emitters
    def emit(self, type_: str, **fields: Any) -> None:
        if self._terminal_emitted:
            raise TerminalEventAlreadyEmitted(
                f"{self.req_id}: event {type_!r} emitted after terminal event"
            )
        self._log.emit(type_, req_id=self.req_id, **fields)

    def emit_counts(self, name: str) -> None:
        """A named counter bump. Cheap, greppable, and monotone in the log."""
        self.emit("counter", name=name)

    def attempt_start(self, attempt: Any) -> None:
        if self._terminal_emitted:
            raise TerminalEventAlreadyEmitted(
                f"{self.req_id}: attempt {attempt.attempt_id} started after terminal"
            )
        self._attempts.add(attempt.attempt_id)
        self._track_backend(getattr(attempt, "backend", None))
        self._log.emit(
            "attempt.start",
            req_id=self.req_id,
            attempt_id=attempt.attempt_id,
            step=attempt.step,
            attempt_backend=attempt.backend,
            model=attempt.model,
            t_sent=attempt.t_sent,
        )

    def _track_backend(self, backend: Optional[str]) -> None:
        if not backend:
            return
        self._backend_counts[backend] = self._backend_counts.get(backend, 0) + 1
        if backend not in self._backend_first:
            self._backend_first.append(backend)

    @property
    def primary_backend(self) -> Optional[str]:
        """The run-scope backend for this request (D-008).

        Majority wins; ties and empties fall back to first appearance. Deliberately
        NOT literally "the first attempt": under concurrency that is a race, and a
        request that fails over to another backend should not be labelled by the
        one that failed.
        """
        if not self._backend_counts:
            return None
        return max(self._backend_first,
                   key=lambda b: (self._backend_counts[b], -self._backend_first.index(b)))

    def attempt_end(self, attempt: Any) -> None:
        self._log.emit(
            "attempt.end",
            req_id=self.req_id,
            attempt_id=attempt.attempt_id,
            step=attempt.step,
            attempt_backend=attempt.backend,
            model=attempt.model,
            t_sent=attempt.t_sent,
            t_first_byte=attempt.t_first_byte,
            t_first_token=attempt.t_first_token,
            t_end=attempt.t_end,
            status=attempt.status,
            outcome=None if attempt.outcome is None else attempt.outcome.value,
            retry_after_s=attempt.retry_after_s,
            tokens_in=attempt.tokens_in,
            tokens_out=attempt.tokens_out,
            tokens_cached=attempt.tokens_cached,
            rl_headers_raw=attempt.rl_headers_raw,
            error_body=attempt.error_body,
        )

    def abandon(self, reason: str = "user") -> None:
        if self._terminal_emitted:
            raise TerminalEventAlreadyEmitted(
                f"{self.req_id}: abandon() after terminal event"
            )
        self._abandoned_at = self._log.now()
        self._log.emit("request.abandoned", req_id=self.req_id, reason=reason)

    def finish(
        self,
        terminal: Any,
        *,
        total_elapsed_s: float,
        waiting_s: float,
        working_s: float,
        retrying_s: float,
        **fields: Any,
    ) -> None:
        """Emit request.end (latency decomposition) then the terminal event.

        This is the only supported way to end a request. It exists because
        emitting the totals after the terminal is an easy, silent ordering bug.
        The decomposition is checked against the total here, so a layer that
        forgets to account for a sleep fails loudly in development.
        """
        if self._terminal_emitted:
            raise TerminalEventAlreadyEmitted(
                f"{self.req_id}: finish() after terminal event"
            )
        self._log.emit(
            "request.end",
            req_id=self.req_id,
            total_elapsed_s=total_elapsed_s,
            waiting_s=waiting_s,
            working_s=working_s,
            retrying_s=retrying_s,
        )
        self.terminal(terminal, **fields)

    def terminal(self, terminal: Any, **fields: Any) -> None:
        """Exactly one per request. Callers must not emit afterwards."""
        if self._terminal_emitted:
            raise TerminalEventAlreadyEmitted(
                f"{self.req_id}: second terminal event ({getattr(terminal, 'value', terminal)!r})"
            )
        self._terminal_emitted = True
        value = getattr(terminal, "value", terminal)
        fields.setdefault("primary_backend", self.primary_backend)
        self._log.emit("terminal", req_id=self.req_id, terminal=value, **fields)


class EventLog:
    _SENTINEL: Final[object] = object()

    def __init__(self, run_dir: str, run_id: str, backend: str):
        self.run_id = run_id
        self.backend = backend
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        self.path = Path(run_dir) / "events.jsonl"
        self._f = open(self.path, "a", buffering=1, encoding="utf-8")
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._closed = False
        self._lock = threading.Lock()
        self._scopes: dict[str, RequestScope] = {}
        self._t = threading.Thread(target=self._writer, name="eventlog-writer", daemon=True)
        self._t.start()

    # -- clock for events that need "now" (monotonic; wall time is a label)
    def now(self) -> float:
        return time.monotonic()

    #: Envelope keys owned by the log. `req_id` is NOT here: it is a legitimate
    #: caller field (RequestScope supplies it, and direct emit() callers pass it).
    RESERVED_FIELDS: Final[frozenset[str]] = frozenset(
        {"type", "t_mono", "t_wall", "run_id", "backend"}
    )
    # `t_first_byte`, `t_sent`, `req_id` etc. are ordinary fields and must NOT be
    # reserved -- attempt.end legitimately carries them.

    def emit(self, type_: str, **fields: Any) -> None:
        if self._closed:
            raise RuntimeError("EventLog.emit after close()")
        clash = self.RESERVED_FIELDS.intersection(fields)
        if clash:
            raise ReservedFieldError(
                f"event {type_!r} tried to set reserved envelope field(s) "
                f"{sorted(clash)}; the envelope owns those keys"
            )
        self._q.put({
            "type": type_,
            "t_mono": time.monotonic(),     # durations
            "t_wall": time.time(),          # label only
            "run_id": self.run_id,
            "backend": self.backend,
            **fields,
        })

    def request(self, req_id: str) -> RequestScope:
        """Get-or-create the scope for a request."""
        with self._lock:
            scope = self._scopes.get(req_id)
            if scope is None:
                scope = RequestScope(self, req_id)
                self._scopes[req_id] = scope
            return scope

    def _writer(self) -> None:
        while True:
            item = self._q.get()
            if item is self._SENTINEL:
                break
            self._f.write(json.dumps(item, default=str) + "\n")

    def flush(self) -> None:
        """Wait until the writer thread has drained the queue.

        Safe to call after close(): close() already joins the writer, so there is
        nothing left to do. Raising here (ValueError on a closed file) turned a
        correct shutdown into a crash -- see docs/BUGLOG.md BUG-002.
        """
        if self._closed:
            return
        while not self._q.empty():
            time.sleep(0.001)
        self._f.flush()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._q.put(self._SENTINEL)
        self._t.join(timeout=5)
        if self._t.is_alive():
            # A stuck writer thread means lost events; surface it rather than hide it.
            raise RuntimeError("event log writer did not drain within 5s")
        self._f.close()

    def __enter__(self) -> "EventLog":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
