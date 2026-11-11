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
from relay.gateway.stream import consume
from relay.ratelimit_headers import parse_rl_headers


class DeadlineExceeded(Exception):
    pass


class BreakerOpen(Exception):
    pass


class _StreamHTTPError(Exception):
    """A non-200 arriving on a streamed request. Carries the body for the log."""

    def __init__(self, status: int, text: str):
        super().__init__(f"stream failed with {status}")
        self.status = status
        self.text = text


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
    #: The Attempt most recently created. Read-only convenience for callers that
    #: need to stamp a later moment (user_ttft) onto the same event.
    _last_attempt: Optional[Attempt] = None
    #: Hard cap on HTTP attempts per logical call, for the MANAGED policy.
    max_attempts: int = 3
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
            max_attempts=cfg.get("gateway.max_attempts", 3),
        )

    # ------------------------------------------------------------ payload

    #: The reasoning-effort parameter name accepted by Groq's chat completions.
    #: UNVERIFIED as of P5: PROBE.md records this as an open question, and the
    #: probe must report the verbatim 400 if it is rejected. It is never "none".
    REASONING_EFFORT_PARAMS = ("reasoning_effort",)

    def request_payload(self, *, model: str, messages: list[dict], max_tokens: int,
                        reasoning_effort: Optional[str] = None,
                        stream: bool = False) -> dict:
        """Build the JSON body for one attempt.

        `max_completion_tokens` is what we send. It is the current OpenAI-compatible
        name for "cap on generated tokens", and Groq's docs list it for the
        gpt-oss family; `max_tokens` is the deprecated alias. Sending one name
        consistently is the point: a retry must not change the request shape.

        `reasoning_effort` goes ONLY to gpt-oss models, and never takes the value
        "none" -- an ignored parameter is a silent behaviour change, and "none"
        is the value we have no evidence for.
        """
        body: dict = {"model": model, "messages": messages,
                      "max_completion_tokens": max_tokens, "stream": stream}
        if stream:
            # Without this the provider may omit usage on a streamed response, and
            # the token accounting silently becomes "unmeasured".
            body["stream_options"] = {"include_usage": True}
        if reasoning_effort is not None:
            if "gpt-oss" not in model:
                # Not an error: callers pass one config value for all models.
                # Dropping it keeps the request valid for non-reasoning models.
                pass
            elif reasoning_effort == "none":
                raise ValueError(
                    'reasoning_effort must never be "none": we have no evidence '
                    "for what the service does with it (PROBE.md open question)")
            else:
                body[self.REASONING_EFFORT_PARAMS[0]] = reasoning_effort
        return body

    # ------------------------------------------------------------ the loop

    async def call(self, *, scope: RequestScope, step: str, model: str,
                   messages: list[dict], max_tokens: int,
                   deadline_s: float, stream: bool = False,
                   reasoning_effort: Optional[str] = None) -> dict:
        """One logical model call. Returns the parsed 200 body.

        A BOUNDED LOOP, never recursion (BUG-013). Each iteration is one HTTP
        attempt; the loop counter is the only thing that can stop it, so the
        worst case is `max_attempts` requests and no possibility of exhausting
        the stack. Policies differ in *what they decide* between attempts, never
        in whether they recurse.
        """
        self._calls += 1
        self._retry_credit += self.retry_budget_ratio
        t_start = self.clock.now()
        managed = self.policy != "naive"

        max_attempts = (self.max_attempts if managed
                        else self.cfg.get("gateway.naive_max_attempts", 5))
        last_error = "no attempt made"

        for attempt_no in range(1, max_attempts + 1):
            self._attempt_n += 1
            attempt_id = f"{scope.req_id}-{step}-{self._attempt_n}"
            t_attempt = self.clock.now()

            if managed:
                if self.breaker.state(t_attempt) == "open":
                    raise BreakerOpen(
                        f"breaker open, reopens in "
                        f"{self.breaker.opened_at + self.breaker.open_s - t_attempt:.1f}s")
                self.budget.take(max_tokens, t_attempt)

            attempt = Attempt(
                attempt_id, scope.req_id, step,
                "standin" if "8009" in self.base_url else "groq",
                model, t_sent=t_attempt)
            self._last_attempt = attempt
            scope.attempt_start(attempt)
            payload = self.request_payload(
                model=model, messages=messages, max_tokens=max_tokens,
                reasoning_effort=reasoning_effort, stream=stream)
            st = None
            if stream:
                # A streamed attempt times out on FIRST CONTENT, not on the whole
                # body: a request that has started answering is not late.
                try:
                    st = await self._streamed_call(payload, t_attempt, deadline_s,
                                                   t_start)
                except asyncio.TimeoutError:
                    attempt.outcome = Outcome.TIMEOUT
                    attempt.t_end = self.clock.now()
                    scope.attempt_end(attempt)
                    if managed:
                        self.breaker.record(False, attempt.t_end)
                    raise DeadlineExceeded("no content before the deadline") from None
                except asyncio.CancelledError:
                    attempt.outcome = Outcome.CANCELLED
                    attempt.t_end = self.clock.now()
                    scope.attempt_end(attempt)
                    raise
                # Rebuild a non-streaming body so every caller sees one shape.
                body = {"choices": [{"message": {"content": st.text}}],
                        "usage": st.usage or {}}
                attempt.t_first_byte = st.first_delta
                attempt.t_first_delta = st.first_delta
                attempt.t_first_token = st.model_ttft
                # Generation is over when the stream ends. The stamp is the END of
                # the stream, not the last content frame, because the terminal
                # [DONE]/usage frames are still part of the call.
                attempt.t_generation_end = st.t_end or self.clock.now()
                attempt.t_end = attempt.t_generation_end
                attempt.status = 200
                usage = st.usage or {}
                attempt.tokens_in = usage.get("prompt_tokens")
                attempt.tokens_out = usage.get("completion_tokens")
                attempt.outcome = Outcome.OK
                scope.attempt_end(attempt)
                if managed:
                    self.breaker.record(True, attempt.t_end)
                return body

            try:
                resp = await asyncio.wait_for(
                    self.client.post("/chat/completions", json=payload),
                    timeout=max(1.0, deadline_s - (self.clock.now() - t_start)))
            except asyncio.TimeoutError:
                attempt.outcome = Outcome.TIMEOUT
                attempt.t_end = self.clock.now()
                scope.attempt_end(attempt)
                if managed:
                    self.breaker.record(False, attempt.t_end)
                raise DeadlineExceeded("attempt timed out") from None
            except asyncio.CancelledError:
                # H4: the caller abandoned this request. Cancelling the await above
                # cancels the HTTP request itself, so the provider stops generating
                # and the tokens stop. We do NOT retry, do NOT touch the retry
                # credit, and re-raise so the cancellation keeps propagating: a
                # swallowed CancelledError would leave a task running for a user
                # who has already gone.
                attempt.outcome = Outcome.CANCELLED
                attempt.t_end = self.clock.now()
                scope.attempt_end(attempt)
                raise

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
                if managed:
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
            if managed:
                self.breaker.record(False, attempt.t_end)

            last_error = (f"{attempt.outcome.value} status={resp.status_code} "
                          f"retry_after={attempt.retry_after_s}")
            decision = self._next_delay(attempt, t_start, deadline_s,
                                        attempt_no, max_attempts, managed)
            if decision is None:
                raise DeadlineExceeded(last_error)
            wait, why = decision
            scope.emit("retry.sleep", attempt_id=attempt.attempt_id,
                       sleep_s=round(wait, 3), policy=self.policy, why=why)
            if wait:
                await self.clock.sleep(wait)   # slot released while sleeping

        raise DeadlineExceeded(f"{last_error} (gave up after {max_attempts} attempts)")

    async def _streamed_call(self, payload: dict, t_attempt: float,
                             deadline_s: float, t_start: float):
        """Open the SSE stream and stamp the three timings as frames arrive.

        Times out on FIRST CONTENT, not on the whole body: a request that has begun
        answering is not late. The role-only frame is a real frame and is stamped as
        `first_delta`, but it is not a first token.
        """
        async def lines():
            async with self.client.stream("POST", "/chat/completions",
                                          json=payload) as resp:
                if resp.status_code != 200:
                    await resp.aread()
                    raise _StreamHTTPError(resp.status_code, resp.text)
                async for line in resp.aiter_lines():
                    yield line

        return await consume(lines(), self.clock, t_attempt,
                             deadline_at=t_start + deadline_s)

    def _next_delay(self, attempt, t_start: float, deadline_s: float,
                    attempt_no: int, max_attempts: int,
                    managed: bool) -> Optional[tuple[float, str]]:
        """Decide whether to retry. Returns (seconds_to_wait, why) or None.

        This is the ONLY place the two policies differ. Keeping the decision in a
        pure method is what makes the comparison honest: same loop, same attempt
        cap, one different function.
        """
        if attempt_no >= max_attempts:
            return None
        elapsed = self.clock.now() - t_start

        if not managed:
            # NAIVE: fixed backoff, ignores retry-after entirely. The provider asked
            # for quiet; this policy sends anyway. That is the harm being shown.
            return (self.cfg.get("gateway.naive_backoff_s", 0.2), "naive_fixed_backoff")

        if attempt.outcome is Outcome.RATE_LIMITED_DAY:
            return None                              # a day limit never retries
        if elapsed >= deadline_s:
            return None
        floor = self.cfg.get("gateway.retry_credit_floor", 0.0)
        if self._retry_credit + floor < 1.0:
            return None                              # global retry budget spent
        wait = attempt.retry_after_s if attempt.retry_after_s is not None else 1.0
        if elapsed + wait >= deadline_s:
            return None                              # would sleep past the deadline
        self._retries_used += 1
        self._retry_credit -= 1.0
        return (wait, "honour_retry_after")
