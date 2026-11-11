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
    tpm_bucket: Bucket = field(init=False)
    day_bucket: Bucket = field(init=False)
    req_bucket: Bucket = field(init=False)
    calls: int = 0

    def __post_init__(self):
        now = time.monotonic()
        self.tpm_bucket = Bucket(self.tpm, 60.0, reset_at=now + 60.0)
        self.day_bucket = Bucket(self.tpd, 86400.0, reset_at=now + 86400.0)
        self.req_bucket = Bucket(self.rpd, 86400.0, reset_at=now + 86400.0)
        self._rng = random.Random(self.seed)

    def _headers(self, now: float) -> dict[str, str]:
        return {
            "x-ratelimit-limit-tokens": str(self.tpm),
            "x-ratelimit-remaining-tokens": str(max(0, self.tpm - self.tpm_bucket.used)),
            "x-ratelimit-reset-tokens": f"{max(0.0, self.tpm_bucket.reset_at - now):.2f}s",
            "x-ratelimit-limit-requests": str(self.rpd),
            "x-ratelimit-remaining-requests": str(max(0, self.rpd - self.req_bucket.used)),
            "x-ratelimit-reset-requests": f"{max(0.0, self.req_bucket.reset_at - now):.0f}s",
        }

    async def complete(self, body: dict, raw: Request) -> Any:
        now = time.monotonic()
        self.calls += 1
        max_tokens = int(body.get("max_tokens") or 0)

        # 429 controls first: they are the behaviour under test
        if self.p429_rate and self._rng.random() < self.p429_rate:
            return self._r429(now, "minute", "hostile p429_rate")
        ok, wait, _ = self.req_bucket.take(1, now)
        if not ok:
            return self._r429(now, "day", "request-per-day exhausted")
        ok, wait, _ = self.day_bucket.take(max_tokens or 1, now)
        if not ok:
            return self._r429(now, "day", "tokens-per-day exhausted")
        # NOTE: max_tokens is taken up front, which mirrors the UNVERIFIED hypothesis
        # that TPM is reserved rather than charged on usage (Q-06). Config switch it.
        ok, wait, _ = self.tpm_bucket.take(max_tokens or 1, now)
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
        usage = {"prompt_tokens": max(1, len(json.dumps(body)) // 4),
                 "completion_tokens": n_out,
                 "total_tokens": 0}
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

        content, _ = synthesize_answer(body, n_out)
        if body.get("stream"):
            return StreamingResponse(
                self._stream(content, usage, latency), media_type="text/event-stream")
        return JSONResponse({
            "id": "chatcmpl-standin", "object": "chat.completion",
            "created": int(time.time()), "model": body.get("model"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": usage,
        }, headers=self._headers(time.monotonic()))

    def _r429(self, now: float, kind: str, why: str) -> JSONResponse:
        wait = (self.tpm_bucket.reset_at - now) if kind == "minute" else 60.0
        body = {"error": {"message": f"Rate limit reached: {why}",
                          "type": "tokens" if kind == "minute" else "requests",
                          "code": "rate_limit_exceeded"}}
        return JSONResponse(body, status_code=429,
                            headers={**self._headers(now),
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
    return {"calls": STATE.calls, "tpm_used": STATE.tpm_bucket.used,
            "day_used": STATE.day_bucket.used, "rpd_used": STATE.req_bucket.used}


@app.post("/__reset")
async def reset():
    global STATE
    STATE = build_state()
    return {"ok": True}
