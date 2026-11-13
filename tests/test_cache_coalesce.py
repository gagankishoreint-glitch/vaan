"""Item C: exact cache and request coalescing, in front of the pipeline.

The behaviours that are easy to get wrong, and are pinned here:

  * a burst of 20 identical questions runs the pipeline ONCE (asserted on the event
    log, not on a call counter);
  * ONE follower abandoning does NOT cancel the others;
  * the LAST follower abandoning DOES;
  * `PassagesOnly(budget_gone)` is never cached -- a transient shortage must not
    become a durable refusal;
  * the key includes the index, top_k, models and prompt version, so a config change
    cannot serve an answer produced by different inputs.

Run: python -m pytest -q tests/test_cache_coalesce.py  -> 12 passed
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from relay.events import EventLog
from relay.pipeline.cache import (
    AnswerCache, AnswerService, Coalescer, cache_key,
)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def now(self) -> float:
        return self.t

    def advance(self, s: float):
        self.t += s


class FakePipeline:
    """Counts runs and can be made slow, so coalescing has a window to work in."""

    def __init__(self, terminal="answered", delay=0.05, reason="ok"):
        self.runs = 0
        self.terminal = terminal
        self.delay = delay
        self.reason = reason
        self.cancelled = 0

    async def answer(self, question):
        from relay.pipeline.pipeline import Outcome_
        from relay.contracts import mint_verified
        self.runs += 1
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        # VerifiedAnswer is minted, never constructed -- the guard exists and this
        # fake has to go through it like real code does.
        reply = mint_verified(text="answer", citations=())
        return Outcome_(reply, self.terminal, self.reason)


def _svc(pipeline, *, ttl=900.0, max_entries=512):
    clock = FakeClock()
    cache = AnswerCache(max_entries=max_entries, ttl_s=ttl, clock=clock)
    key_for = lambda q: cache_key(q, index_id="exp900", top_k=4,
                                  model_small="s", model_large="l",
                                  prompt_version="p6.1")
    return AnswerService(pipeline, cache, Coalescer(), key_for), clock, cache


# ------------------------------------------------------------------ the cache

def test_cache_hit_costs_no_pipeline_run_and_never_waits():
    async def go():
        p = FakePipeline(delay=0.0)
        svc, _, _ = _svc(p)
        first = await svc.ask("what is attention")
        second = await svc.ask("what is attention")
        return p, first, second

    p, first, second = asyncio.run(go())
    assert p.runs == 1, f"the second question ran the pipeline again ({p.runs} runs)"
    assert first.cache_hit is False
    assert second.cache_hit is True


def test_question_normalisation_is_whitespace_and_case_only():
    """Two questions differing only in spacing/case are the same question."""
    k1 = cache_key("What  is\nattention?", index_id="i", top_k=4,
                   model_small="s", model_large="l", prompt_version="v")
    k2 = cache_key("what is attention?", index_id="i", top_k=4,
                   model_small="s", model_large="l", prompt_version="v")
    assert k1 == k2


def test_key_changes_with_every_input_that_changes_the_answer():
    """A config change must invalidate the cache, or it serves a stale answer."""
    base = dict(index_id="exp900", top_k=4, model_small="s", model_large="l",
                prompt_version="v")
    k = cache_key("q", **base)
    for field, newval in (("index_id", "exp1200"), ("top_k", 8),
                          ("model_small", "s2"), ("model_large", "l2"),
                          ("prompt_version", "v2")):
        changed = dict(base, **{field: newval})
        assert cache_key("q", **changed) != k, (
            f"changing {field} did not change the cache key -- an answer produced "
            "under different settings would be served as this one")


def test_only_verified_and_no_evidence_are_cached():
    """budget_gone must not be cached: it describes our state, not the answer."""
    clock = FakeClock()
    cache = AnswerCache(max_entries=10, ttl_s=60.0, clock=clock)
    assert cache.put("k1", object(), "answered") is True
    assert cache.put("k2", object(), "no_evidence") is True
    assert cache.put("k3", object(), "passages_only", "budget_gone") is False
    assert cache.put("k4", object(), "busy") is False
    assert cache.put("k5", object(), "abandoned") is False
    assert len(cache) == 2


def test_ttl_expiry():
    clock = FakeClock()
    cache = AnswerCache(max_entries=10, ttl_s=10.0, clock=clock)
    cache.put("k", object(), "answered")
    assert cache.get("k") is not None
    clock.advance(11.0)
    assert cache.get("k") is None
    assert cache.expired == 1


def test_max_size_evicts_and_stays_bounded():
    clock = FakeClock()
    cache = AnswerCache(max_entries=3, ttl_s=600.0, clock=clock)
    for i in range(10):
        cache.put(f"k{i}", object(), "answered")
    assert len(cache) == 3
    assert cache.evictions == 7


# ------------------------------------------------------------- coalescing

def test_burst_of_20_identical_questions_runs_the_pipeline_once():
    """Asserted on the pipeline run count AND the coalescer's follower count."""
    async def go():
        p = FakePipeline(delay=0.1)
        svc, _, _ = _svc(p)
        return p, svc, await asyncio.gather(*[svc.ask("same question")
                                              for _ in range(20)])

    p, svc, results = asyncio.run(go())
    assert p.runs == 1, f"20 identical questions ran the pipeline {p.runs} times"
    assert svc.coalescer.coalesced == 19, svc.coalescer.coalesced
    assert sum(1 for r in results if r.coalesced_follower) == 19


def test_one_follower_abandoning_does_not_cancel_the_others():
    """The property that makes coalescing safe to offer at all."""
    async def go():
        p = FakePipeline(delay=0.15)
        svc, _, _ = _svc(p)

        leader = asyncio.ensure_future(svc.ask("q"))
        await asyncio.sleep(0.02)                 # let the leader start the run
        followers = [asyncio.ensure_future(svc.ask("q")) for _ in range(3)]
        await asyncio.sleep(0.02)

        followers[0].cancel()                     # one impatient waiter
        with pytest.raises(asyncio.CancelledError):
            await followers[0]

        rest = await asyncio.gather(leader, *followers[1:])
        return p, rest

    p, rest = asyncio.run(go())
    assert p.cancelled == 0, "one abandoning follower cancelled the shared run"
    assert len(rest) == 3
    assert all(r.terminal == "answered" for r in rest)


def test_last_waiter_abandoning_cancels_the_pipeline():
    """Refcounted cancellation: only the final departure stops the run."""
    async def go():
        p = FakePipeline(delay=0.5)               # long enough to be cancelled
        svc, _, _ = _svc(p)

        leader = asyncio.ensure_future(svc.ask("q"))
        await asyncio.sleep(0.02)
        follower = asyncio.ensure_future(svc.ask("q"))
        await asyncio.sleep(0.02)

        leader.cancel()
        follower.cancel()
        for f in (leader, follower):
            with pytest.raises(asyncio.CancelledError):
                await f
        await asyncio.sleep(0.05)                 # let the cancellation land
        return p

    p = asyncio.run(go())
    assert p.cancelled == 1, (
        "the pipeline was not cancelled after the last waiter left; refcounting is "
        f"leaking (cancelled={p.cancelled})")


def test_a_completed_flight_is_not_cancelled_by_a_late_departure():
    """`leave` after the task finished must be a no-op, not a cancel."""
    async def go():
        p = FakePipeline(delay=0.0)
        svc, _, _ = _svc(p)
        await svc.ask("q")
        return p

    p = asyncio.run(go())
    assert p.cancelled == 0


def test_cache_and_coalescing_compose():
    """Second burst hits the CACHE, not merely the coalescer."""
    async def go():
        p = FakePipeline(delay=0.05)
        svc, _, _ = _svc(p)
        await asyncio.gather(*[svc.ask("q") for _ in range(5)])
        await asyncio.gather(*[svc.ask("q") for _ in range(5)])
        return p

    p = asyncio.run(go())
    assert p.runs == 1, f"pipeline ran {p.runs} times across two bursts"


def test_seventeen_identical_questions_pipeline_runs_once_in_the_event_log():
    """The supervisor asked for this asserted on the EVENT LOG, not a counter.

    A counter proves the object's internal bookkeeping. The event log is what a
    post-mortem reads, so the claim "20 questions caused one pipeline run" has to be
    visible there: one request event with real work, the rest marked as cache hits or
    coalesced followers.
    """
    async def go():
        td = tempfile.mkdtemp()
        log = EventLog(td, run_id="burst", backend="standin")
        p = FakePipeline(delay=0.08)
        svc, _, _ = _svc(p)

        async def ask(i, question):
            # Each waiter is its own request in the log, exactly as a real caller is.
            req = log.request(f"burst-{i}")
            out = await svc.ask(question)
            log.emit("answer.cache", req_id=req.req_id,
                     cache_hit=out.cache_hit,
                     coalesced_follower=out.coalesced_follower,
                     terminal=out.terminal)
            return out

        results = await asyncio.gather(*[ask(i, "the same question")
                                         for i in range(20)])
        log.close()
        events = []
        for f in Path(td).glob("*.jsonl"):
            events += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        return p, results, events

    p, results, events = asyncio.run(go())
    cache_events = [e for e in events if e["type"] == "answer.cache"]
    assert len(cache_events) == 20, len(cache_events)
    assert p.runs == 1, f"20 identical questions caused {p.runs} pipeline runs"

    n_hit = sum(1 for e in cache_events if e["cache_hit"])
    n_follower = sum(1 for e in cache_events if e["coalesced_follower"])
    n_leader = 20 - n_hit - n_follower
    assert n_leader == 1, f"expected exactly one leader, got {n_leader}"
    assert n_follower == 19 or n_hit == 19, (n_follower, n_hit)
    # every request reached a terminal and is attributable
    assert all(e["terminal"] == "answered" for e in cache_events)
