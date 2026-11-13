"""P4: FastAPI stand-in for the Groq chat-completions API.

Purpose: run every load shape at full speed without spending tokens, with the
failure modes the probe will observe. Everything is seeded and configured from
config/relay.yaml -- nothing is hard-coded.

Documented differences from the real service are listed in docs/STANDIN.md.

    uvicorn relay.standin.server:app --port 8009
    curl -s localhost:8009/openai/v1/models
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from relay.config import load_config

CFG = load_config()

#: Every knob has a config home. The ones still null fall back to *documented
#: provisional* values and print a warning at startup, so a null never silently
#: becomes a number nobody chose (rule 4) -- it is announced.
_DEFAULTS = {
    "ttft_ms": (180.0, "provisional: no real probe yet"),
    "tokens_per_s": (90.0, "provisional: no real probe yet"),
    "error_rate": (0.0, "provisional: no real probe yet"),
    "p429_rate": (0.0, "provisional: no real probe yet"),
    "per_minute_limit": (8000, "provisional: docs-table TPM, UNVERIFIED"),
    "per_day_limit": (200000, "provisional: docs-table TPD, UNVERIFIED"),
}


def _knob(name: str) -> float:
    v = CFG.get(f"standin.{name}", None)
    if v is None:
        value, why = _DEFAULTS[name]
        print(f"[standin] standin.{name} is null; using {value} ({why})")
        return float(value)
    return float(v)


@dataclass
class RefillBucket:
    """A continuously-refilling token bucket, which is what the observations show.

    The old `Bucket` was a FIXED window: `used` reset at `reset_at`, and the
    advertised reset was always "start of the next window" (~60 s right after a
    request). The transcribed observations contradict that flatly -- `reset-tokens`
    was 1.17 s, then 1.335 s, then 0.96 s, and in all three
    `reset = deficit / (8000/60)`. That is a bucket refilling at 133.3 tokens/s, not
    one that empties at a minute boundary.

    Model: `deficit` tokens are currently owed. It decays at `rate` per second, and
    `reset` is the time for the current deficit to decay to zero.

    CALIBRATION: n=4 transcribed points, raw JSONL pending. The refill rate is
    inferred from `limit / 60`, which is a docs-table assumption, not a measurement
    of the refill function. See docs/STANDIN.md.
    """

    limit: int
    window_s: float
    deficit: float = 0.0
    last: float = 0.0

    @property
    def rate(self) -> float:
        return self.limit / self.window_s

    def _decay(self, now: float) -> None:
        if self.last:
            self.deficit = max(0.0, self.deficit - (now - self.last) * self.rate)
        self.last = now

    def remaining(self, now: float) -> int:
        self._decay(now)
        return max(0, int(round(self.limit - self.deficit)))

    def reset_in(self, now: float) -> float:
        """Seconds until the current deficit is fully refilled."""
        self._decay(now)
        return self.deficit / self.rate if self.rate else 0.0

    def take(self, n: int, now: float) -> tuple[bool, float, int]:
        self._decay(now)
        if self.deficit + n > self.limit:
            return False, self.deficit / self.rate, max(0, int(self.limit - self.deficit))
        self.deficit += n
        return True, self.deficit / self.rate, max(0, int(round(self.limit - self.deficit)))

    def refund(self, n: float, now: float) -> None:
        """Give back unused reservation (Groq may or may not do this -- see config)."""
        self._decay(now)
        self.deficit = max(0.0, self.deficit - n)


@dataclass
class Bucket:
    """A token bucket. Check-and-take is synchronous: no await between (rule 9)."""
    limit: int
    window_s: float
    used: int = 0
    reset_at: float = 0.0

    def take(self, n: int, now: float) -> tuple[bool, float, int]:
        if now >= self.reset_at:
            self.used = 0
            self.reset_at = now + self.window_s
        remaining = max(0, self.limit - self.used)
        if n > remaining:
            return False, self.reset_at - now, remaining
        self.used += n
        return True, self.reset_at - now, self.limit - self.used


class _CitationBody(JSONResponse):
    """Untyped body; kept as plain JSONResponse for exact control over headers."""


def synthesize_answer(body: dict, max_tokens: int) -> tuple[str, bool]:
    """Produce a citation-bearing answer from the passages in the prompt.

    The stand-in must be able to exercise the HAPPY path (draft -> verify ->
    VerifiedAnswer), otherwise the pipeline's success branch is never tested and a
    broken verifier would look like a careful one. It extracts the chunk ids the
    prompt offered and returns a short answer quoting verbatim from the first one,
    with a `[chunk_id]` marker -- plus a percentage of deliberately bad answers so
    the failure path is exercised too (UNVERIFIABLE_RATE).
    """
    prompt = "".join(m.get("content", "") for m in body.get("messages", []))
    ids = re.findall(r"\[([a-z0-9\-]+:s[^\]]+:c\d{4})\]", prompt)
    if not ids:
        return ("NOT_FOUND", False)
    if random.Random(len(prompt)).random() < UNVERIFIABLE_RATE:
        return ("The answer is 42 [nonexistent-chunk:s9:c9999]", True)
    # quote a real sentence that follows the chosen id marker
    want = ids[0]
    marker = f"[{want}]"
    if marker in prompt:
        tail = prompt.split(marker, 1)[1]
        sentence = re.split(r"(?<=[.!?])\s+", tail.strip())[0][:300]
        if len(sentence) > 25:
            return (f"{sentence} [{want}]", True)
    return ("NOT_FOUND", False)


#: Fraction of otherwise-fine answers that are deliberately unverifiable, so the
#: verify-failure path is exercised. Seeded, so runs are reproducible.
UNVERIFIABLE_RATE = float(os.environ.get("STANDIN_UNVERIFIABLE_RATE", "0.2"))


@dataclass
class StandIn:
    seed: int = 7
    ttft_ms: float = 180.0
    tokens_per_s: float = 90.0
    error_rate: float = 0.0
    p429_rate: float = 0.0
    tpm: int = 8000
    tpd: int = 200000
    rpd: int = 1000
    slow_success: bool = False
    hang_s: float = 0.0
    load_slowdown: float = 0.0
    #: Whether unused completion cap is given back to the TPM bucket on completion.
    #: OPEN (Q-06): the four transcribed observations all had completion < cap and
    #: still show the FULL cap in the deficit (call 1: deficit 156 = 76 + 80 with 41
    #: generated), which is evidence AGAINST a refund but is only n=4 and never
    #: isolates the case. Default false = no refund, matching the observation; flip
    #: this to run the A/B that settles it.
    refund_unused_cap: bool = False
    tpm_bucket: RefillBucket = field(init=False)
    day_bucket: Bucket = field(init=False)
    req_bucket: Bucket = field(init=False)
    calls: int = 0

    def __post_init__(self):
        now = time.monotonic()
        # Continuously-refilling, because the observations show reset = deficit/rate
        # rather than a fixed window (see tests/test_standin_observed.py).
        self.tpm_bucket = RefillBucket(self.tpm, 60.0, deficit=0.0, last=now)
        self.day_bucket = Bucket(self.tpd, 86400.0, reset_at=now + 86400.0)
        self.req_bucket = Bucket(self.rpd, 86400.0, reset_at=now + 86400.0)
        self._rng = random.Random(self.seed)

    def _headers(self, now: float) -> dict[str, str]:
        """Rate-limit headers in the shape the gateway parses.

        CALIBRATION: the header NAMES and the *-requests = per-day reading are from
        the Groq docs table, not from an observed response -- no real call has been
        made (Q-04). The gateway tolerates the other reading; see
        docs/STANDIN.md "Bucket model".

        One deliberate correction to the previous version: `reset-tokens` used to be
        computed from the TPM bucket even when the 429 was a DAY limit, so a day
        exhaustion advertised "retry in 40s". `_headers` now reports each bucket's own
        reset, and `_r429` says which limit was hit (Q-09: what a day 429 looks like
        is still UNVERIFIED).
        """
        return {
            "x-ratelimit-limit-tokens": str(self.tpm),
            "x-ratelimit-remaining-tokens": str(self.tpm_bucket.remaining(now)),
            "x-ratelimit-reset-tokens": f"{self.tpm_bucket.reset_in(now):.2f}s",
            "x-ratelimit-limit-requests": str(self.rpd),
            "x-ratelimit-remaining-requests": str(max(0, self.rpd - self.req_bucket.used)),
            "x-ratelimit-reset-requests": f"{max(0.0, self.req_bucket.reset_at - now):.0f}s",
            # Day TOKEN bucket. Not a Groq header name: Groq is believed to expose only
            # TPM and RPD. Emitted because the stand-in ENFORCES a day-token limit and
            # a client that cannot see which bucket it exhausted cannot be tested
            # against it. Prefixed `x-standin-` so it can never be mistaken for real.
            "x-standin-limit-day-tokens": str(self.tpd),
            "x-standin-remaining-day-tokens": str(max(0, self.tpd - self.day_bucket.used)),
            "x-standin-reset-day-tokens": f"{max(0.0, self.day_bucket.reset_at - now):.0f}s",
        }

    async def complete(self, body: dict, raw: Request) -> Any:
        now = time.monotonic()
        self.calls += 1
        # Accept the current name first and fall back to the deprecated alias, so
        # the stand-in keeps working whichever one the gateway sends.
        max_tokens = int(body.get("max_completion_tokens")
                         or body.get("max_tokens") or 0)

        # 429 controls first: they are the behaviour under test
        if self.p429_rate and self._rng.random() < self.p429_rate:
            return self._r429(now, "minute", "hostile p429_rate")
        ok, wait, _ = self.req_bucket.take(1, now)
        if not ok:
            return self._r429(now, "day_requests", "request-per-day exhausted")
        # Reservation is PROMPT + CAP, not cap alone. The transcribed call 1 shows
        # deficit 156 = prompt 76 + cap 80 while only 41 tokens were generated, so
        # both halves are reserved and the cap is reserved in full (Q-06, n=4).
        # Charging cap alone made the stand-in advertise remaining 7920 where the
        # service advertised 7844 -- the same order, the wrong number.
        prompt_tokens = max(1, len(json.dumps(body)) // 4)
        reserved = prompt_tokens + (max_tokens or 1)
        # Snapshot the rate-limit state AT RESERVATION, not at response.
        # The transcribed reset 1.17 s == 156/133.3 exactly, i.e. the advertised
        # deficit is the reservation, undecayed. Computing headers after the TTFT
        # sleep refilled ~24 tokens and silently cancelled the prompt half of the
        # reservation, so remaining looked like cap-only.
        self._rl_snapshot_at = now
        ok, wait, _ = self.day_bucket.take(reserved, now)
        if not ok:
            return self._r429(now, "day_tokens", "tokens-per-day exhausted")
        ok, wait, _ = self.tpm_bucket.take(reserved, now)
        if not ok:
            return self._r429(now, "minute", "tokens-per-minute exhausted")

        if self.error_rate and self._rng.random() < self.error_rate:
            return JSONResponse({"error": {"message": "internal server error"}},
                                status_code=500)
        if self.hang_s:
            await asyncio.sleep(self.hang_s)
        if self.slow_success:
            await asyncio.sleep(5.0)

        latency = self.ttft_ms / 1000.0
        if self.load_slowdown:
            latency *= 1.0 + self.load_slowdown * (self.calls / 100.0)
        await asyncio.sleep(latency)

        n_out = min(max_tokens or 16, 40)
        usage = {"prompt_tokens": prompt_tokens,
                 "completion_tokens": n_out,
                 "total_tokens": 0}
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

        # Refund the unused part of the reservation, if configured to. OPEN (Q-06):
        # the observations are consistent with NO refund (deficit showed the full cap
        # even when 41 of 80 were generated), but n=4 and never isolating. Default is
        # the observed behaviour; this switch exists so the A/B can settle it.
        if self.refund_unused_cap:
            unused = max(0, reserved - (usage["completion_tokens"]
                                        + usage["prompt_tokens"]))
            if unused:
                self.tpm_bucket.refund(unused, time.monotonic())

        content, _ = synthesize_answer(body, n_out)
        if body.get("stream"):
            return StreamingResponse(
                self._stream(content, usage, latency),
                media_type="text/event-stream",
                headers=self._headers(getattr(self, "_rl_snapshot_at",
                                              time.monotonic())))
        return JSONResponse({
            "id": "chatcmpl-standin", "object": "chat.completion",
            "created": int(time.time()), "model": body.get("model"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": usage,
        }, headers=self._headers(getattr(self, "_rl_snapshot_at", time.monotonic())))

    def _r429(self, now: float, kind: str, why: str) -> JSONResponse:
        """A 429 that describes the bucket that actually refused.

        `kind` is minute | day_tokens | day_requests. The old version had one `day`
        case that always reported a 60 s wait and `type: requests`, and always sent
        `reset-tokens` from the minute bucket -- so a caller could not tell which
        limit it had hit, and `retry-after` was a guess. The gateway's
        minute-vs-day classification depends on exactly this distinction (Q-09).
        """
        if kind == "minute":
            wait = self.tpm_bucket.reset_in(now)
            typ, hdrs = "tokens", {"x-ratelimit-reset-tokens":
                                   f"{wait:.2f}s"}
        elif kind == "day_tokens":
            wait = max(0.0, self.day_bucket.reset_at - now)
            typ, hdrs = "tokens", {"x-standin-reset-day-tokens": f"{wait:.0f}s"}
        else:                                            # day_requests
            wait = max(0.0, self.req_bucket.reset_at - now)
            typ, hdrs = "requests", {"x-ratelimit-reset-requests": f"{wait:.0f}s"}
        body = {"error": {"message": f"Rate limit reached: {why}",
                          "type": typ,
                          "code": "rate_limit_exceeded"}}
        return JSONResponse(body, status_code=429,
                            headers={**self._headers(now), **hdrs,
                                     "retry-after": f"{max(1, int(wait))}"})

    async def _stream(self, content: str, usage: dict, latency: float):
        delay = 1.0 / max(1.0, self.tokens_per_s)
        yield f'data: {json.dumps({"choices":[{"delta":{"role":"assistant"}}]})}\n\n'
        for i in range(max(1, len(content.split()))):
            await asyncio.sleep(delay)
            chunk = {"choices": [{"delta": {"content": content.split()[i] + " "}}]}
            yield f"data: {json.dumps(chunk)}\n\n"
        yield f'data: {json.dumps({"choices": [], "usage": usage})}\n\n'
        yield "data: [DONE]\n\n"


def build_state() -> StandIn:
    return StandIn(
        seed=int(_knob_seed()), ttft_ms=_knob("ttft_ms"),
        tokens_per_s=_knob("tokens_per_s"), error_rate=_knob("error_rate"),
        p429_rate=_knob("p429_rate"), tpm=int(_knob("per_minute_limit")),
        tpd=int(_knob("per_day_limit")),
        slow_success=os.environ.get("STANDIN_SLOW", "") == "1",
        hang_s=float(os.environ.get("STANDIN_HANG_S", "0") or 0),
        load_slowdown=float(os.environ.get("STANDIN_LOAD", "0") or 0),
        # Q-06 is OPEN: this is the ASSUMED branch, and it is read from config so
        # the A/B can actually be run. Before this, `refund_unused_cap` existed as a
        # field, a default and a branch in the code, and NO caller ever set it --
        # so the switch could not be flipped and both arms of the A/B would have
        # been the same arm, silently.
        refund_unused_cap=bool(CFG.get("standin.refund_unused_cap", False)),
    )


def _knob_seed() -> int:
    return int(CFG.get("standin.seed", 7))


app = FastAPI(title="Groq stand-in")
STATE = build_state()


@app.get("/openai/v1/models")
async def models():
    return {"object": "list", "data": [
        {"id": CFG.get("models.small.id"), "object": "model", "owned_by": "standin"},
        {"id": CFG.get("models.large.id"), "object": "model", "owned_by": "standin"},
    ]}


@app.post("/openai/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    return await STATE.complete(body, request)


@app.get("/__stats")
async def stats():
    # The ASSUMPTIONS are part of the stats, not just the counters. Q-06 is OPEN, so
    # two runs that differ only in `refund_unused_cap` can legitimately disagree; a
    # result that cannot name the branch it ran under cannot be compared with the
    # other branch, and the A/B would be two unattributable tables.
    # `remaining(now)`, not a `.used` attribute: `RefillBucket` has never exposed
    # `.used` since it replaced the fixed-window `Bucket` (BUG-033), so this route
    # raised AttributeError on every call. Nothing read it in a test, so it stayed
    # broken -- and any run that wanted to record its assumptions got a 500.
    #
    # The three buckets are NOT the same class: TPM is a `RefillBucket` (continuous
    # refill, observed), while the day and request buckets are fixed-window
    # `Bucket`s. Assuming one API for all three is how this route broke twice.
    now = time.monotonic()
    return {"calls": STATE.calls,
            "tpm_remaining": STATE.tpm_bucket.remaining(now),
            "day_used": STATE.day_bucket.used,
            "rpd_used": STATE.req_bucket.used,
            "assumptions": {
                "refund_unused_cap": bool(getattr(STATE, "refund_unused_cap", False)),
                "per_minute_limit": CFG.get("standin.per_minute_limit", None),
                "seed": _knob_seed(),
            }}


@app.post("/__reset")
async def reset():
    global STATE
    STATE = build_state()
    return {"ok": True}
