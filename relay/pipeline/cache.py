"""Exact-match answer cache and request coalescing.

Both exist for the same reason: a repeated question must not cost a second model
call. They are different mechanisms and are kept separate here.

CACHE
  Key = the normalised question PLUS everything that changes the answer: the index
  build, top_k, model ids, and a prompt version. A cache keyed on the question alone
  is a correctness bug waiting for the first config change -- it would serve an
  answer produced by a different index, or by a prompt that no longer exists, and
  nothing downstream could tell.

  Only `VerifiedAnswer` and `NoEvidence` are cached. `PassagesOnly(budget_gone)` is
  explicitly NOT: it is a statement about *our* state at that moment (`budget_gone`,
  `breaker_open`), and caching it would turn a transient shortage into a durable
  refusal that outlives the shortage. `PassagesOnly` for other reasons is also not
  cached, because an unverified answer is the one thing this project must not
  repeat as if it were verified.

COALESCING
  One in-flight pipeline per key; followers await the leader's result. Cancellation
  is refcounted: the pipeline stops only when the LAST waiter abandons. A naive
  version -- cancel when any waiter leaves -- means one impatient user kills the
  request for everyone else sharing it, which is worse than not coalescing at all
  because it makes the system's behaviour depend on the least patient caller.

Run:
    python -m pytest -q tests/test_cache_coalesce.py     -> 9 passed
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

#: Terminals that may be cached. Everything else is a statement about transient
#: state, or an unverified reply which must never be replayed as a result.
CACHEABLE_TERMINALS = frozenset({"answered", "no_evidence"})


def cache_key(question: str, *, index_id: str, top_k: int,
              model_small: str, model_large: str, prompt_version: str) -> str:
    """The full key. Deliberately includes things that are not the question.

    Normalisation is whitespace-and-case only. Anything more aggressive (stemming,
    synonym folding) risks two different questions colliding, and a false cache hit
    returns an answer to a question nobody asked -- the worst failure available here.
    """
    norm = " ".join(question.split()).casefold()
    return "|".join((norm, index_id, str(top_k), model_small, model_large,
                     prompt_version))


@dataclass
class CacheEntry:
    reply: Any
    terminal: str
    reason: str
    stored_at: float


@dataclass
class AnswerCache:
    """Bounded, TTL'd, exact-match cache. Sized and timed from config."""

    max_entries: int
    ttl_s: float
    clock: Any
    _entries: dict[str, CacheEntry] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expired: int = 0

    def get(self, key: str) -> Optional[CacheEntry]:
        e = self._entries.get(key)
        if e is None:
            self.misses += 1
            return None
        if self.clock.now() - e.stored_at >= self.ttl_s:
            del self._entries[key]
            self.expired += 1
            self.misses += 1
            return None
        self.hits += 1
        return e

    def put(self, key: str, reply: Any, terminal: str, reason: str = "") -> bool:
        """Store, if this outcome is cacheable. Returns whether it was stored."""
        if terminal not in CACHEABLE_TERMINALS:
            return False
        # Evict oldest-inserted first. Deliberately not LRU: tracking recency would
        # need touch-on-read, and an explicit simple policy is easier to reason
        # about than an approximation of one.
        while len(self._entries) >= self.max_entries and self._entries:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
            self.evictions += 1
        self._entries[key] = CacheEntry(reply, terminal, reason, self.clock.now())
        return True

    def __len__(self) -> int:
        return len(self._entries)


@dataclass
class _Flight:
    """One in-flight pipeline and the waiters attached to it."""

    task: "asyncio.Task"
    waiters: int = 1
    followers: int = 0


class Coalescer:
    """One pipeline run per key; followers await it; refcounted cancellation.

    The waiters counter is the whole mechanism. `join()` increments it; a departing
    waiter decrements it, and ONLY a decrement to zero cancels the task. That is what
    makes "one follower abandoning does not cancel the others" true by construction
    rather than by a test happening to pass.
    """

    def __init__(self) -> None:
        self._flights: dict[str, _Flight] = {}
        self.coalesced = 0     # followers that joined an existing flight

    def in_flight(self, key: str) -> bool:
        return key in self._flights

    def leader(self, key: str, coro) -> "_Flight":
        """Start the pipeline for `key` as the leader."""
        task = asyncio.ensure_future(coro)

        def _done(_t):
            self._flights.pop(key, None)

        flight = _Flight(task=task)
        self._flights[key] = flight
        task.add_done_callback(_done)
        return flight

    def join(self, key: str) -> Optional["_Flight"]:
        """Attach to an existing flight, if there is one."""
        flight = self._flights.get(key)
        if flight is None:
            return None
        flight.waiters += 1
        flight.followers += 1
        self.coalesced += 1
        return flight

    def leave(self, key: str, flight: "_Flight") -> bool:
        """A waiter departed. Returns True if the flight was cancelled as a result.

        Cancellation happens only at the LAST departure. A task that has already
        finished is left alone.
        """
        flight.waiters -= 1
        if flight.waiters > 0 or flight.task.done():
            return False
        flight.task.cancel()
        return True


@dataclass
class Answered:
    """What a caller of `AnswerService.ask` gets back.

    `cache_hit` / `coalesced_follower` are on the RESULT, not only in the log, so a
    test can assert them without parsing events, and so a caller can tell a 0-token
    answer from a billed one.
    """

    reply: Any
    terminal: str
    reason: str = ""
    cache_hit: bool = False
    coalesced_follower: bool = False


class AnswerService:
    """Cache in front of the pipeline, then coalescing, then the pipeline.

    Order matters and is fixed here: a cache hit costs nothing and never waits, so it
    is checked first. Only when the answer is not cached does a caller either lead a
    new pipeline run or join one already in flight.
    """

    def __init__(self, pipeline, cache: AnswerCache, coalescer: Coalescer,
                 key_for):
        self.pipeline = pipeline
        self.cache = cache
        self.coalescer = coalescer
        #: `key_for(question) -> str`; injected so the key composition is testable
        #: and so this class does not need to know the config shape.
        self.key_for = key_for

    async def ask(self, question: str) -> Answered:
        key = self.key_for(question)

        hit = self.cache.get(key)
        if hit is not None:
            return Answered(hit.reply, hit.terminal, hit.reason, cache_hit=True)

        flight = self.coalescer.join(key)
        follower = flight is not None
        if flight is None:
            flight = self.coalescer.leader(key, self._run(question))

        try:
            out = await asyncio.shield(flight.task)
        except asyncio.CancelledError:
            # This waiter is leaving. The flight dies only if it was the last one --
            # `leave` enforces that, so an impatient follower cannot kill the run for
            # a leader that is still waiting.
            self.coalescer.leave(key, flight)
            raise
        except Exception:
            self.coalescer.leave(key, flight)
            raise

        # Departure accounting happens in `leave`, called once per waiter. The
        # leader holds the initial count of 1, so it must leave here too.
        self.coalescer.leave(key, flight)

        reply, terminal, reason = out
        self.cache.put(key, reply, terminal, reason)
        return Answered(reply, terminal, reason, cache_hit=False,
                        coalesced_follower=follower)

    async def _run(self, question: str):
        out = await self.pipeline.answer(question)
        return out.reply, out.terminal, out.reason
