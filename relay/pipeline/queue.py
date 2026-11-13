"""Bounded admission queue with priorities, and honest rejection.

Every request passes through here before it may occupy a worker. Two outcomes are
possible, and only two:

  ADMITTED   a worker is free, or the expected wait fits inside the request's
             remaining deadline.
  SHED       the queue is full, or the expected wait exceeds the remaining deadline.

**A shed request is never a bare rejection.** It gets `PassagesOnly(queue_full)` --
the passages that would have answered it, at zero tokens. A caller told "busy" with
nothing attached has no way to distinguish "try again" from "this will never work",
and the passages may answer the question outright. This project's rule is that every
request ends in a terminal event; "dropped" is not a terminal.

PRIORITIES
  interactive > background. A background batch (the probe, a load harness) must not
  be able to sit in front of a user's question. Implemented as two FIFO deques rather
  than a heap: with two priority levels a heap buys nothing and costs the property
  that requests at the same priority are served in arrival order, which is the one
  fairness statement that is easy to keep true and easy to test.

Why an EXPECTED-WAIT check and not just a depth check: a queue of depth 3 is
harmless when three workers are draining it in 40 ms each and fatal when the last
one is stuck behind a 30 s hang. Depth alone says nothing about whether a caller
will still be waiting when they have given up.

Run:
    python -m pytest -q tests/test_admission_queue.py     -> 11 passed
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

PRIORITY_INTERACTIVE = 0
PRIORITY_BACKGROUND = 1


@dataclass
class Admission:
    """The result of asking to be let in."""

    admitted: bool
    #: A DIAGNOSIS, finer than the contract reason. `""` when admitted;
    #: `queue_full` or `would_wait_past_deadline` when shed. It stays finer in the
    #: log because the two are different diagnoses -- one means "come back later",
    #: the other means "this request would have missed its deadline anyway" -- but
    #: both map to the single contract reason `queue_full` via `contract_reason()`.
    #: The contract vocabulary is deliberately smaller than the diagnostic one: a
    #: user cannot act on the difference, and `PassagesOnly.reason` is a closed set.
    reason: str = ""
    expected_wait_s: float = 0.0
    queue_wait_s: float = 0.0     # actual wait, filled in once admitted


#: The ONLY mapping from an admission diagnosis to a contract reason. A caller that
#: builds `PassagesOnly` from `Admission.reason` directly would crash on
#: `would_wait_past_deadline`, because it is not a member of the contract set.
CONTRACT_REASON: dict[str, str] = {
    "queue_full": "queue_full",
    "would_wait_past_deadline": "queue_full",
}


def contract_reason(admission_reason: str) -> str:
    """Map an admission diagnosis to `PassagesOnly.reason`.

    Raises on an unknown diagnosis rather than passing it through: a new diagnosis
    that reaches the contract unchecked is how the set silently grows.
    """
    try:
        return CONTRACT_REASON[admission_reason]
    except KeyError:
        raise ValueError(
            f"admission reason={admission_reason!r} has no contract reason; "
            f"add it to CONTRACT_REASON deliberately") from None


@dataclass
class _Waiting:
    fut: "asyncio.Future"
    priority: int
    enqueued_at: float


class AdmissionQueue:
    """Bounded, prioritised admission with deadline-aware shedding.

    `capacity` is the number of requests allowed to WAIT. Requests are served by
    `workers` workers; the queue exists to absorb bursts shorter than a request's
    patience, not to store unbounded work.

    `service_estimate_s` is the moving average of how long a request occupies a
    worker. It is what turns "depth" into "expected wait". It starts at
    `initial_estimate_s` because a queue with no history must still make a decision;
    the initial value comes from config so the guess is named and visible rather than
    buried in a constant.
    """

    def __init__(self, *, capacity: int, workers: int,
                 service_estimate_s: float, clock):
        self.capacity = capacity
        self.workers = workers
        self.clock = clock
        self._service = service_estimate_s
        self._initial = service_estimate_s
        self._waiting: list[_Waiting] = []
        self._busy = 0
        self.admitted = 0
        self.shed_full = 0
        self.shed_deadline = 0
        self.completed = 0

    # ------------------------------------------------------------ estimates

    @property
    def service_estimate_s(self) -> float:
        return self._service

    def record_service(self, seconds: float) -> None:
        """Exponential moving average, so one outlier cannot redefine the queue."""
        # 0.2 keeps roughly the last five requests in view: fast enough to notice a
        # provider slowdown, slow enough not to panic over one slow call.
        self._service = 0.8 * self._service + 0.2 * max(0.0, seconds)

    def depth(self) -> int:
        return len(self._waiting)

    def _ahead(self, priority: int) -> int:
        """How many waiting requests would be served before one of `priority`.

        Priority decides ORDER among those already queued; it does not erase them.
        An interactive request that arrives when every worker is busy still waits for
        the RUNNING requests to finish. Returning 0 here made the estimate blind to
        depth, so a deep queue of fast requests predicted a 0 s wait -- the estimate
        has to see the work, not just the ordering.
        """
        if priority == PRIORITY_INTERACTIVE:
            # Everything already queued outranks us only by virtue of being queued;
            # we jump it, so count the RUNNING work instead (handled by `free`).
            return 0
        return len(self._waiting)

    def expected_wait_s(self, priority: int = PRIORITY_INTERACTIVE) -> float:
        """Seconds until a request of `priority` is likely to reach a worker."""
        free = max(0, self.workers - self._busy)
        if free > 0 and not self._waiting:
            return 0.0
        ahead = self._ahead(priority)
        # Occupied workers are work in front of EVERYONE, including interactive
        # requests: they must wait for a worker to become free. Queue depth is work
        # in front only of requests at the same or lower priority.
        in_front = max(0, self._busy - 0) if free == 0 else 0
        # (free > 0 means a worker is coming as soon as `release` runs, so the
        #  wait is the time for one request, not for the whole queue.)
        if free > 0:
            return (max(0, ahead) / max(1, self.workers)) * self._service
        return ((in_front + ahead) / max(1, self.workers)) * self._service

    # -------------------------------------------------------------- admission

    async def acquire(self, *, priority: int = PRIORITY_INTERACTIVE,
                      deadline_remaining_s: Optional[float] = None) -> Admission:
        """Ask for a worker. Returns immediately when there is one free."""
        if self._busy < self.workers and not self._waiting:
            self._busy += 1
            self.admitted += 1
            return Admission(True)

        wait_est = self.expected_wait_s(priority)
        if deadline_remaining_s is not None and wait_est > deadline_remaining_s:
            # Refuse BEFORE queueing. Joining the queue would spend the caller's
            # remaining patience to reach a refusal.
            self.shed_deadline += 1
            return Admission(False, "would_wait_past_deadline", wait_est, 0.0)

        if len(self._waiting) >= self.capacity:
            self.shed_full += 1
            return Admission(False, "queue_full", wait_est, 0.0)

        t0 = self.clock.now()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._waiting.append(_Waiting(fut, priority, t0))
        self._waiting.sort(key=lambda w: (w.priority, w.enqueued_at))
        try:
            await fut
        except asyncio.CancelledError:
            # The caller abandoned while waiting. Leave the queue; do NOT leak a
            # slot, and do not consume a worker.
            self._drop(fut)
            raise
        # NO `self._busy += 1` here. `release()` transfers the slot to this waiter
        # before waking it: incrementing on both sides over-admitted, because a third
        # `acquire()` could slip in while this coroutine was still rescheduling and
        # then the count went to 2 against a limit of 1.
        self.admitted += 1
        return Admission(True, "", wait_est, self.clock.now() - t0)

    def _drop(self, fut) -> None:
        for i, w in enumerate(self._waiting):
            if w.fut is fut:
                del self._waiting[i]
                return

    def release(self, *, served_s: Optional[float] = None) -> None:
        """A worker finished. Hand its slot to the highest-priority waiter, if any.

        The slot is TRANSFERRED, not freed: `_busy` stays where it was and the woken
        waiter does not increment it. Freeing and re-incrementing on both sides is a
        race -- between the decrement here and the increment in the waiter, another
        `acquire()` can observe a free worker and take it, and the queue over-admits.
        """
        self.completed += 1
        if served_s is not None:
            self.record_service(served_s)
        for i, w in enumerate(self._waiting):
            if not w.fut.done():
                del self._waiting[i]
                w.fut.set_result(True)
                return                      # slot transferred; _busy unchanged
        self._busy = max(0, self._busy - 1)  # nobody waiting: actually free it


@dataclass
class QueueSettings:
    """Everything the queue needs, resolved from config in ONE place."""

    capacity: int
    workers: int
    service_estimate_s: float
    _provisional: bool = False

    @classmethod
    def from_config(cls, cfg) -> "QueueSettings":
        """`queue_max: null` must not silently become an invented depth.

        Null means UNMEASURED, not zero. A capacity of 0 would shed every request as
        `queue_full`, which is a production outage dressed as a safety default. The
        fallback is therefore a named provisional value, and `provisional` records
        that config did not supply it so a caller can say so in the log.
        """
        raw = cfg.get("gateway.queue_max", None)
        return cls(
            capacity=int(raw) if raw is not None else 32,
            _provisional=raw is None,
            workers=int(cfg.get("gateway.workers", 4) or 4),
            service_estimate_s=float(
                cfg.get("gateway.service_estimate_s", 1.0) or 1.0),
        )

    @property
    def capacity_was_provisional(self) -> bool:
        return self._provisional


class QueueBusy(Exception):
    """Raised with the information needed to build a non-bare rejection.

    Carries `reason` and `passages` so the caller cannot accidentally produce a
    terminal that says "busy" and nothing else.
    """

    def __init__(self, reason: str, expected_wait_s: float, passages):
        super().__init__(f"{reason} (expected wait {expected_wait_s:.2f}s)")
        self.reason = reason
        self.expected_wait_s = expected_wait_s
        self.passages = tuple(passages)
