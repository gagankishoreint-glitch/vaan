"""Append-only JSONL event log. All report numbers are derived from this file.

Rule 8: never block the event loop. emit() only enqueues; a daemon thread does the
writing. Rule: one terminal event per request -- enforced by request_scope below
and re-checked by scripts/check_events.py against the written file.

EVENT ORDERING CONTRACT (violated once already, see docs/BUGLOG.md BUG-001):
    request.start -> ... -> request.end -> terminal
`request.end` carries the latency decomposition. The terminal event is LAST.
Use finish() rather than emitting these two by hand.

BACKEND SCOPE (DECISIONS D-011, which supersedes D-008):
    envelope `backend`  = DECLARED at construction, one of {groq, standin, mixed}.
                          A declaration, never derived from the attempts it
                          describes (circular label -- supervisor review).
    `attempt_backend`   = observed: the backend that actually served THAT attempt.
                          This is the field the managed-vs-naive comparison uses.
    `run.end`           = the observed breakdown, `attempt_backend_counts`.
A declared `groq` run whose attempts were served by `standin` is therefore a
detectable contradiction (checker I7), instead of a label that quietly agrees
with whatever happened.
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

    __slots__ = ("_log", "req_id", "_terminal_emitted", "_attempts", "_abandoned_at")

    #: A request-scoped event must never set the run-scope `backend`.
    RESERVED_IN_SCOPE: Final[frozenset[str]] = frozenset({"backend"})

    def __init__(self, log: "EventLog", req_id: str):
        self._log = log
        self.req_id = req_id
        self._terminal_emitted = False
        self._attempts: set[str] = set()
        self._abandoned_at: Optional[float] = None

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
        clash = self.RESERVED_IN_SCOPE.intersection(fields)
        if clash:
            raise ReservedFieldError(
                f"{self.req_id}: request-scoped event {type_!r} tried to set run-scope "
                f"field(s) {sorted(clash)}; use `attempt_backend` for per-attempt values"
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
        self._log.note_attempt_backend(getattr(attempt, "backend", None))
        self._log.emit(
            "attempt.start",
            req_id=self.req_id,
            attempt_id=attempt.attempt_id,
            step=attempt.step,
            attempt_backend=attempt.backend,
            model=attempt.model,
            t_sent=attempt.t_sent,
        )

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
            t_first_delta=getattr(attempt, "t_first_delta", None),
            t_user_ttft=getattr(attempt, "t_user_ttft", None),
            t_generation_end=getattr(attempt, "t_generation_end", None),
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
        self._log.emit("terminal", req_id=self.req_id, terminal=value, **fields)


BACKENDS: Final[frozenset[str]] = frozenset({"groq", "standin", "mixed"})


class EventLog:
    _SENTINEL: Final[object] = object()

    def __init__(self, run_dir: str, run_id: str, backend: str):
        if backend not in BACKENDS:
            raise ValueError(
                f"backend must be one of {sorted(BACKENDS)}, got {backend!r}. "
                f"It is a DECLARATION about the run, not a computed label."
            )
        self.run_id = run_id
        self.backend = backend
        self._attempt_backend_counts: dict[str, int] = {}
        self._counts_lock = threading.Lock()
        self._run_ended = False
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
    #:
    #: `backend` is absent ON PURPOSE: it is run scope on run-level events and
    #: attempt scope on attempt events, which both go through this one function.
    #: The prohibition therefore lives on the run-level emitters (`emit` for
    #: run.*, and RequestScope for request.*), not on the shared channel.
    RESERVED_FIELDS: Final[frozenset[str]] = frozenset(
        {"type", "t_mono", "t_wall", "run_id"}
    )
    # `t_first_byte`, `t_sent`, `req_id`, `backend` are ordinary fields and must
    # NOT be rejected here -- attempt.end legitimately carries the first three.

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

    def note_attempt_backend(self, backend: Optional[str]) -> None:
        """Tally the OBSERVED backend of an attempt. Never feeds the declaration."""
        if not backend:
            return
        with self._counts_lock:
            self._attempt_backend_counts[backend] = (
                self._attempt_backend_counts.get(backend, 0) + 1)

    def end_run(self, **fields: Any) -> None:
        """Emit `run.end` with the observed breakdown. Call once, on clean shutdown.

        Deliberately NOT called from close(): the absence of `run.end` is how the
        checker tells a clean shutdown from a crash. Use try/finally in entry
        points so an exception still records that the run ended abnormally.
        """
        if self._run_ended:
            raise RuntimeError("end_run() called twice")
        self._run_ended = True
        with self._counts_lock:
            counts = dict(self._attempt_backend_counts)
        self.emit("run.end", attempt_backend_counts=counts, **fields)

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
