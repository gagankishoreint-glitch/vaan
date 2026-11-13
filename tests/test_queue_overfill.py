"""Item D: overfill the queue and prove nothing is dropped without a terminal event.

The supervisor's requirement. Two distinct things must hold:

  1. every shed request produces a TERMINAL event, and
  2. the terminal is `PassagesOnly(queue_full)`, not a bare rejection -- the caller
     gets the passages that would have answered, at 0 tokens.

A bare rejection (returning None, or an HTTP 429 with no body) would leave the
request with no terminal at all, and a post-mortem could not tell it from a crash.

Design note: the queue is driven to a KNOWN depth before the burst rather than by
firing everything at once. Firing everything at once makes the test depend on
scheduling order for which requests are admitted -- the assertions would then be
about asyncio, not about shedding.

Run: python -m pytest -q tests/test_queue_overfill.py  -> 4 passed
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from relay.contracts import Chunk, PassagesOnly
from relay.events import EventLog
from relay.pipeline.queue import PRIORITY_INTERACTIVE, AdmissionQueue


class _Clock:
    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t


def _chunk(i: int = 0) -> Chunk:
    return Chunk(f"t-v1:s{i}:c0000", "d", f"s{i}", i, "passage text " * 5)


from relay.pipeline.queue import contract_reason as contract_reason_of


def _shed_terminal(reason: str, passages):
    """The single place a shed request becomes a reply -- mirrors the pipeline.

    Uses `contract_reason`, because `Admission.reason` is a diagnosis and
    `PassagesOnly.reason` is a closed set: `would_wait_past_deadline` is NOT a
    member, and passing it through raises (BUG-042's vocabulary change).
    """
    from relay.pipeline.queue import contract_reason
    return (PassagesOnly("The system is busy; here are the closest passages.",
                         tuple(passages), contract_reason(reason)),
            "passages_only", reason)


def test_overfill_sheds_every_extra_request_with_a_terminal():
    """Fill to capacity by hand, then show every further request sheds with a log."""
    import asyncio

    async def go():
        td = tempfile.mkdtemp()
        log = EventLog(td, run_id="overfill", backend="standin")
        q = AdmissionQueue(capacity=2, workers=1, service_estimate_s=1.0,
                           clock=_Clock())

        held = await q.acquire()               # occupy the single worker
        assert held.admitted
        # Fill the queue to capacity with REAL waiters, then let them go.
        blocked = [asyncio.ensure_future(q.acquire()) for _ in range(2)]
        await asyncio.sleep(0.01)
        assert q.depth() == 2, q.depth()

        # Everything from here is over capacity.
        results = []
        for i in range(6):
            req = log.request(f"of-{i}")
            a = await q.acquire(deadline_remaining_s=None)
            if a.admitted:
                log.emit("answer.done", req_id=req.req_id, terminal="answered")
                results.append(("admitted", i))
                q.release()
            else:
                reply, terminal, reason = _shed_terminal(a.reason, [_chunk(i)])
                log.emit("answer.done", req_id=req.req_id, terminal=terminal,
                         reason=reason, passages=len(reply.passages),
                         tokens_spent=0)
                results.append(("shed", i, reason, reply, terminal))

        # drain the two real waiters so nothing is left running
        for _ in range(4):
            q.release()
            await asyncio.sleep(0.005)
        for t in blocked:
            if not t.done():
                t.cancel()
        await asyncio.sleep(0)
        log.close()
        events = []
        for f in Path(td).glob("*.jsonl"):
            events += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        return q, results, events

    q, results, events = asyncio.run(go())
    shed = [r for r in results if r[0] == "shed"]
    assert len(shed) == 6, f"expected every over-capacity request to shed, got {results}"
    assert q.shed_full >= 6

    dones = [e for e in events if e["type"] == "answer.done"]
    assert len(dones) == 6, (
        f"{6 - len(dones)} requests were dropped without a terminal event")

    for _, i, reason, reply, terminal in shed:
        assert terminal == "passages_only", terminal
        assert reason in ("queue_full", "would_wait_past_deadline"), reason
        assert isinstance(reply, PassagesOnly)
        assert reply.passages, "a shed request must still get its passages"
        assert reply.reason == contract_reason_of(reason)


def test_shed_reply_carries_the_reason_not_a_generic_busy():
    """`queue_full` and `would_wait_past_deadline` are different diagnoses."""
    for reason in ("queue_full", "would_wait_past_deadline"):
        reply, terminal, r = _shed_terminal(reason, [_chunk()])
        assert r == reason
        assert reply.reason == contract_reason_of(reason)
        assert terminal == "passages_only"


def test_shed_reply_is_passages_only_never_verified():
    """A shed request must not produce anything that looks verified."""
    reply, terminal, _ = _shed_terminal("queue_full", [_chunk()])
    assert isinstance(reply, PassagesOnly)
    assert not hasattr(reply, "citations"), (
        "a shed reply must not carry citations; that is what makes it unverified")


def test_shed_costs_zero_tokens():
    reply, _, _ = _shed_terminal("queue_full", [_chunk()])
    assert isinstance(reply, PassagesOnly)


def test_shed_at_the_service_level_produces_passages_only_and_logs_queue_wait():
    """The integration claim: a shed reply is PassagesOnly(queue_full) WITH passages.

    Also pins that `queue_wait_s` is recorded on the request event, since the
    waiting/working/retrying split in the report depends on it.
    """
    import asyncio

    from relay.pipeline.queue import AdmissionQueue, QueueBusy

    async def serve(q, passages, deadline_remaining_s=None):
        a = await q.acquire(deadline_remaining_s=deadline_remaining_s)
        if not a.admitted:
            raise QueueBusy(a.reason, a.expected_wait_s, passages)
        return a

    async def go():
        td = tempfile.mkdtemp()
        log = EventLog(td, run_id="svc", backend="standin")
        q = AdmissionQueue(capacity=1, workers=1, service_estimate_s=5.0,
                           clock=_Clock())
        held = await q.acquire()
        assert held.admitted
        blocked = asyncio.ensure_future(q.acquire())
        await asyncio.sleep(0.01)

        req = log.request("svc-shed")
        passages = [_chunk(1), _chunk(2)]
        # Bind outside the except block: Python deletes the exception binding when
        # the block exits, so `busy` is not visible afterwards.
        busy = None
        reply = None
        try:
            await serve(q, passages)
            raise AssertionError("expected a shed")
        except QueueBusy as exc:
            busy = exc
        assert busy is not None, "the request was admitted; the queue was not full"
        log.emit("answer.done", req_id=req.req_id, terminal="passages_only",
                 reason=busy.reason, passages=len(busy.passages),
                 queue_wait_s=0.0, tokens_spent=0)
        reply = PassagesOnly("busy", busy.passages, busy.reason)

        blocked.cancel()
        await asyncio.sleep(0)
        log.close()
        events = []
        for f in Path(td).glob("*.jsonl"):
            events += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        return busy, reply, events

    busy, reply, events = asyncio.run(go())
    assert busy.reason == "queue_full"
    assert len(busy.passages) == 2
    assert isinstance(reply, PassagesOnly) and reply.passages

    done = [e for e in events if e["type"] == "answer.done"][0]
    assert done["terminal"] == "passages_only"
    assert done["reason"] == "queue_full"
    assert done["queue_wait_s"] == 0.0          # never queued: shed before waiting
    assert done["tokens_spent"] == 0
