"""P5: minimal rate-limit-aware gateway. Single owner of limit state.

Order per call (PRD s5): deadline -> budget reserve -> breaker -> send -> reconcile
-> classify -> retry. Every threshold comes from config; a null raises at the point
of use rather than becoming a number nobody chose.

Two policies, switchable, because the report needs the harm demonstrated:
  managed  honour retry-after, respect a global retry budget, never sleep past the
           deadline, release the slot while sleeping.
  naive    retry immediately, ignore retry-after, ignore the deadline.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from relay.clock import Clock
from relay.config import Config
from relay.contracts import Attempt, Outcome
from relay.events import EventLog, RequestScope
from relay.ratelimit_headers import parse_rl_headers


class DeadlineExceeded(Exception):
    pass


class BreakerOpen(Exception):
    pass


@dataclass
class Budget:
    """Local view of the provider's buckets.

    take() is synchronous and does the check and the decrement with no await
    between them (rule 9). It is never allowed to go negative.
    """
    tpm: int
    rpd: int
    tpm_used: int = 0
    rpd_used: int = 0
    tpm_reset_at: float = 0.0
    rpd_reset_at: float = 0.0
    #: The provider's advertised limits, learned from response headers. Without
    #: these, `remaining` cannot be converted to a usage figure (BUG-010).
    provider_limit_tpm: Optional[int] = None
    provider_limit_rpd: Optional[int] = None

    def take(self, tokens: int, now: float) -> None:
        if now >= self.tpm_reset_at:
            self.tpm_used, self.tpm_reset_at = 0, now + 60.0
        if now >= self.rpd_reset_at:
            self.rpd_used, self.rpd_reset_at = 0, now + 86400.0
        if self.tpm_used + tokens > self.tpm:
            raise DeadlineExceeded(f"local TPM budget exhausted: "
                                   f"{self.tpm_used}+{tokens} > {self.tpm}")
        if self.rpd_used + 1 > self.rpd:
            raise DeadlineExceeded("local RPD budget exhausted")
        self.tpm_used += tokens      # check and take, no await between
        self.rpd_used += 1
        assert self.tpm_used <= self.tpm and self.rpd_used <= self.rpd

    def learn_limits(self, limit_tpm: Optional[int], limit_rpd: Optional[int]) -> None:
        """Record the provider's advertised limits so `remaining` means something."""
        if limit_tpm:
            self.provider_limit_tpm = limit_tpm
        if limit_rpd:
            self.provider_limit_rpd = limit_rpd

    def reconcile(self, remaining_tpm: Optional[int], remaining_rpd: Optional[int],
                  now: float) -> None:
        """Adopt the provider's view of the bucket, but only DOWNWARD.

        Taking the provider's `remaining` verbatim is wrong for a long-lived gateway:
        the provider's window may be nearly empty from traffic this process did not
        send, which would starve every request for the rest of that minute. We
        therefore only raise our recorded usage when the provider says we have less,
        never reset it to a spent value -- our own window reset stays authoritative.
        """
        # Only skip when we KNOW our window has rolled over (a take() has already
        # reset it). `tpm_reset_at == 0.0` means "never taken", not "stale".
        if self.tpm_reset_at and now >= self.tpm_reset_at:
            return                      # our window is stale; keep local truth
        # `remaining` is only meaningful against the provider's OWN limit. Using our
        # local limit to reconstruct usage is a units mismatch: it silently pinned
        # every request to "budget exhausted" the moment the two disagreed
        # (BUG-010). We therefore reconcile only the RATIO, and only downward.
        if remaining_tpm is not None and self.provider_limit_tpm:
            used_frac = 1.0 - (remaining_tpm / self.provider_limit_tpm)
            provider_used = int(used_frac * self.tpm)
            self.tpm_used = max(self.tpm_used, min(provider_used, self.tpm))
        if remaining_rpd is not None and self.provider_limit_rpd:
            used_frac = 1.0 - (remaining_rpd / self.provider_limit_rpd)
            provider_used = int(used_frac * self.rpd)
            self.rpd_used = max(self.rpd_used, min(provider_used, self.rpd))


class Breaker:
    def __init__(self, fail_threshold: int, open_s: float):
        self.fail_threshold = fail_threshold
        self.open_s = open_s
        self.fails = 0
        self.opened_at: Optional[float] = None

    def state(self, now: float) -> str:
        if self.opened_at is None:
            return "closed"
        if now - self.opened_at >= self.open_s:
            return "half-open"
        return "open"

    def record(self, ok: bool, now: float) -> None:
        if ok:
            self.fails = 0
            self.opened_at = None
            return
        self.fails += 1
        if self.fails >= self.fail_threshold:
            self.opened_at = now


@dataclass
class Gateway:
    cfg: Config
    clock: Clock
    log: EventLog
    base_url: str
    api_key: str
    budget: Budget
    breaker: Breaker
    client: httpx.AsyncClient
    policy: str = "managed"
    retry_budget_ratio: float = 0.1
    max_tokens_map: dict = field(default_factory=dict)
    _retries_used: int = 0
    _calls: int = 0
    _attempt_n: int = 0
    #: Retry credit in "retries"; grows by retry_budget_ratio per call so the
    #: policy is a share of traffic over time, not per-call (see BUG-009).
    _retry_credit: float = 0.0

    @classmethod
    def from_config(cls, cfg: Config, clock: Clock, log: EventLog, *,
                    base_url: str, api_key: str, client: httpx.AsyncClient,
                    policy: Optional[str] = None) -> "Gateway":
        policy = policy or cfg.get("gateway.retry_policy", "managed")
        b = cfg.get("gateway.breaker", {})
        return cls(
            cfg=cfg, clock=clock, log=log, base_url=base_url, api_key=api_key,
            budget=Budget(tpm=cfg.get("models.small.tpm"), rpd=cfg.get("models.small.rpd")),
            breaker=Breaker(b.get("fail_threshold", 5), b.get("open_s", 10.0)),
            client=client, policy=policy,
            retry_budget_ratio=cfg.get("gateway.retry_budget_ratio", 0.1),
        )

    async def call(self, *, scope: RequestScope, step: str, model: str,
                   messages: list[dict], max_tokens: int,
                   deadline_s: float, stream: bool = False) -> dict:
        """One logical model call, with retries. Returns the parsed 200 body."""
        self._calls += 1
        self._retry_credit += self.retry_budget_ratio
        self._attempt_n += 1
        attempt_id = f"{scope.req_id}-{step}-{self._attempt_n}"
        t_start = self.clock.now()

        if self.breaker.state(t_start) == "open":
            raise BreakerOpen(f"breaker open, reopens in "
                              f"{self.breaker.opened_at + self.breaker.open_s - t_start:.1f}s")
        self.budget.take(max_tokens, t_start)

        attempt = Attempt(attempt_id, scope.req_id, step, "standin" if "8009" in self.base_url
                          else "groq", model, t_sent=t_start)
        scope.attempt_start(attempt)
        try:
            resp = await asyncio.wait_for(
                self.client.post("/chat/completions", json={
                    "model": model, "messages": messages,
                    "max_tokens": max_tokens, "stream": False}),
                timeout=max(1.0, deadline_s - (self.clock.now() - t_start)))
        except asyncio.TimeoutError:
            attempt.outcome = Outcome.TIMEOUT
            attempt.t_end = self.clock.now()
            scope.attempt_end(attempt)
            self.breaker.record(False, attempt.t_end)
            raise DeadlineExceeded("attempt timed out") from None
        finally:
            pass

        attempt.t_first_byte = self.clock.now()
        attempt.t_end = self.clock.now()
        attempt.status = resp.status_code
        attempt.rl_headers_raw = dict(resp.headers)
        rl = parse_rl_headers(resp.headers)
        attempt.retry_after_s = rl["retry_after_s"]
        body = resp.json()
        usage = body.get("usage") or {}
        attempt.tokens_in = usage.get("prompt_tokens")
        attempt.tokens_out = usage.get("completion_tokens")
        self.budget.learn_limits(rl.get("limit_tpm"), rl.get("limit_rpd"))
        self.budget.reconcile(rl.get("remaining_tpm"), rl.get("remaining_rpd"),
                              self.clock.now())

        if resp.status_code == 200:
            attempt.outcome = Outcome.OK
            attempt.t_first_token = attempt.t_first_byte
            scope.attempt_end(attempt)
            self.breaker.record(True, attempt.t_end)
            return body

        if resp.status_code == 429:
            attempt.outcome = (Outcome.RATE_LIMITED_DAY
                               if (attempt.retry_after_s or 0) >= 60
                               else Outcome.RATE_LIMITED_MIN)
        elif resp.status_code == 413:
            attempt.outcome = Outcome.TOO_LARGE
        else:
            attempt.outcome = Outcome.SERVER_ERROR
        attempt.error_body = resp.text[:2000]
        scope.attempt_end(attempt)
        self.breaker.record(False, attempt.t_end)

        return await self._maybe_retry(scope, attempt, step, model, messages,
                                       max_tokens, deadline_s, t_start)

    async def _maybe_retry(self, scope, attempt, step, model, messages,
                           max_tokens, deadline_s, t_start) -> dict:
        if attempt.outcome is Outcome.RATE_LIMITED_DAY:
            raise DeadlineExceeded("day limit: never retry")
        elapsed = self.clock.now() - t_start
        if elapsed >= deadline_s:
            raise DeadlineExceeded("deadline exhausted before retry")

        if self.policy == "naive":
            # Demonstrates the harm: ignore retry-after, no budget, no deadline check.
            await self.clock.sleep(0.01)
            return await self.call(scope=scope, step=step, model=model,
                                   messages=messages, max_tokens=max_tokens,
                                   deadline_s=deadline_s)

        # managed. A ratio of 0.1 over 10 calls earns 1 retry; the floor below lets
        # the FIRST failures retry at all, which is what a user-facing service does
        # (a cold gateway must not refuse to retry anything). It is a config value.
        floor = self.cfg.get("gateway.retry_credit_floor", 0.0)
        if self._retry_credit + floor < 1.0:
            raise DeadlineExceeded(
                f"retry budget exhausted ({self._retries_used} retries over "
                f"{self._calls} calls at ratio {self.retry_budget_ratio})")
        wait = attempt.retry_after_s if attempt.retry_after_s is not None else 1.0
        if elapsed + wait >= deadline_s:
            raise DeadlineExceeded("retry-after would exceed the deadline")
        self._retries_used += 1
        self._retry_credit -= 1.0
        scope.emit("retry.sleep", attempt_id=attempt.attempt_id, sleep_s=round(wait, 3))
        await self.clock.sleep(wait)     # slot released: we are not holding a worker
        return await self.call(scope=scope, step=step, model=model,
                               messages=messages, max_tokens=max_tokens,
                               deadline_s=deadline_s)
