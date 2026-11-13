"""Item D: bounded admission queue, priorities, and non-bare rejection.

The trap this test file exists to prevent: "reject when full" implemented as
`return None` or a bare 429. A dropped request leaves no terminal event, and a caller
cannot tell "try again shortly" from "this will never work".

Run: python -m pytest -q tests/test_admission_queue.py  -> 11 passed
"""
from __future__ import annotations

import asyncio

import pytest

from relay.pipeline.queue import (
    PRIORITY_BACKGROUND, PRIORITY_INTERACTIVE, AdmissionQueue,
)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def advance(self, s: float):
        self.t += s


def _q(*, capacity=3, workers=2, service=0.05):
    return AdmissionQueue(capacity=capacity, workers=workers,
                          service_estimate_s=service, clock=FakeClock())


def test_free_worker_admits_immediately():
    q = _q(workers=2)
    a = asyncio.run(q.acquire())
    assert a.admitted and a.reason == ""
    assert a.queue_wait_s == 0.0


def test_requests_beyond_worker_count_wait_then_run():
    async def go():
        q = _q(capacity=4, workers=1)
        first = await q.acquire()
        assert first.admitted

        order = []

        async def waiter(tag):
            a = await q.acquire()
            order.append((tag, a.admitted))
            await asyncio.sleep(0)
            q.release()

        t = asyncio.ensure_future(waiter("second"))
        await asyncio.sleep(0.01)
        q.release()                        # hand the worker over
        await t
        return q, order

    q, order = asyncio.run(go())
    assert order == [("second", True)]
    assert q.completed >= 1


def test_queue_full_sheds_and_says_why():
    async def go():
        q = _q(capacity=1, workers=1)
        await q.acquire()                  # occupies the only worker
        waiting = asyncio.ensure_future(q.acquire())
        await asyncio.sleep(0.01)          # it is now the single queued request
        shed = await q.acquire(deadline_remaining_s=None)
        waiting.cancel()
        return q, shed

    q, shed = asyncio.run(go())
    assert shed.admitted is False
    assert shed.reason == "queue_full", shed.reason
    assert q.shed_full == 1


def test_expected_wait_longer_than_deadline_is_shed_without_queueing():
    """Refuse before spending the caller's remaining patience on a wait."""
    async def go():
        q = _q(capacity=10, workers=1, service=2.0)
        await q.acquire()                  # busy for an estimated 2 s
        a = await q.acquire(deadline_remaining_s=0.1)
        return q, a

    q, a = asyncio.run(go())
    assert a.admitted is False
    assert a.reason == "would_wait_past_deadline", a.reason
    assert q.shed_deadline == 1
    assert q.depth() == 0, "the request was queued despite being refused"


def test_expected_wait_shorter_than_deadline_is_admitted():
    async def go():
        q = _q(capacity=10, workers=1, service=0.01)
        await q.acquire()
        task = asyncio.ensure_future(q.acquire(deadline_remaining_s=10.0))
        await asyncio.sleep(0.01)
        q.release()
        return await task

    a = asyncio.run(go())
    assert a.admitted is True, a.reason


def test_interactive_jumps_ahead_of_background():
    """A user's question must not sit behind a batch."""
    async def go():
        q = _q(capacity=8, workers=1)
        await q.acquire()                          # occupy the worker
        served = []

        async def entrant(tag, prio):
            await q.acquire(priority=prio)
            served.append(tag)
            q.release()

        bg1 = asyncio.ensure_future(entrant("bg1", PRIORITY_BACKGROUND))
        await asyncio.sleep(0.005)
        bg2 = asyncio.ensure_future(entrant("bg2", PRIORITY_BACKGROUND))
        await asyncio.sleep(0.005)
        user = asyncio.ensure_future(entrant("user", PRIORITY_INTERACTIVE))
        await asyncio.sleep(0.02)
        q.release()                                # worker becomes free
        await asyncio.sleep(0.02)
        for _ in range(3):
            q.release() if q._busy else None
            await asyncio.sleep(0.01)
        for t in (bg1, bg2, user):
            if not t.done():
                t.cancel()
        return served

    served = asyncio.run(go())
    assert served and served[0] == "user", (
        f"interactive request was not served first; order was {served}")


def test_same_priority_is_fifo():
    """The one fairness property that is cheap to keep and cheap to test."""
    async def go():
        q = _q(capacity=8, workers=1)
        await q.acquire()
        served = []

        async def entrant(tag):
            await q.acquire()
            served.append(tag)
            q.release()

        tasks = []
        for tag in ("a", "b", "c"):
            tasks.append(asyncio.ensure_future(entrant(tag)))
            await asyncio.sleep(0.005)
        await asyncio.sleep(0.01)
        for _ in range(4):
            q.release()
            await asyncio.sleep(0.02)
        for t in tasks:
            if not t.done():
                t.cancel()
        return served

    served = asyncio.run(go())
    assert served[:3] == ["a", "b", "c"], served


def test_abandoning_while_queued_leaves_no_ghost():
    """A cancelled waiter must not hold a slot or a worker."""
    async def go():
        q = _q(capacity=2, workers=1)
        await q.acquire()
        waiting = asyncio.ensure_future(q.acquire())
        await asyncio.sleep(0.01)
        assert q.depth() == 1
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        return q

    q = asyncio.run(go())
    assert q.depth() == 0, "cancelled waiter still in the queue"
    assert q._busy == 1, "a worker was leaked to a request that left"


def test_service_estimate_is_a_moving_average_not_a_last_value():
    q = _q(service=0.1)
    q.record_service(10.0)
    assert 0.1 < q.service_estimate_s < 10.0, q.service_estimate_s
    for _ in range(50):
        q.record_service(0.01)
    assert q.service_estimate_s < 0.1


def test_expected_wait_grows_with_busy_workers():
    """Occupied workers are work in front of EVERYONE.

    Queue depth deliberately does NOT add wait for an interactive request: it jumps
    the queue. What it cannot jump is a worker that is already occupied, so that is
    what the estimate must track.
    """
    q = _q(capacity=100, workers=4, service=0.5)
    waits = []
    for busy in range(5):
        q._busy = busy
        waits.append(q.expected_wait_s(PRIORITY_INTERACTIVE))
    assert waits == sorted(waits), waits
    assert waits[-1] > waits[0], waits


def test_background_wait_grows_with_queue_depth():
    """Background work does wait behind the queue, so its estimate must see it."""
    q = _q(capacity=100, workers=1, service=0.5)
    q._busy = 1
    waits = []
    for _ in range(4):
        waits.append(q.expected_wait_s(PRIORITY_BACKGROUND))
        q._waiting.append(_dummy())
    assert waits == sorted(waits), waits
    assert waits[-1] > waits[0], waits


def _dummy():
    from relay.pipeline.queue import _Waiting
    return _Waiting(fut=object(), priority=PRIORITY_INTERACTIVE, enqueued_at=0.0)
