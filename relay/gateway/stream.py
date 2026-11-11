"""SSE parsing and the three timestamps.

A streamed reply has three distinguishable moments, and conflating them is what
makes "TTFT" numbers in reports incomparable with each other:

  first_delta  the first SSE `data:` frame arrives with any delta -- often just
               `{"delta":{"role":"assistant"}}`, which carries NO content. This is
               the earliest sign the connection is alive and the model has started.
  model_ttft   the first frame carrying non-empty CONTENT. This is the model's
               first token. Measured from the moment the request was sent.
  user_ttft    the first byte of the VERIFIED answer that actually reaches the user
               -- i.e. after verification has finished. Measured from the moment the
               request was sent by the caller.

They are ordered first_delta <= model_ttft <= user_ttft, and the gap between the
last two is the cost of verification: the user waits for the model AND for us.
Reporting only one number hides which part is slow.

Run:
    python -m pytest -q tests/test_clock.py tests/test_p4_p6.py   -> all pass
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


@dataclass
class StreamTimings:
    """Wall-clock (clock-space) stamps for one streamed attempt. None = never seen."""
    t_sent: float
    first_delta: Optional[float] = None
    model_ttft: Optional[float] = None
    t_end: Optional[float] = None
    content_parts: list[str] = field(default_factory=list)
    usage: Optional[dict] = None
    n_deltas: int = 0
    #: Rate-limit headers as received. The streamed path used to drop these on the
    #: floor, so streamed attempts -- which is every answer the pipeline sends --
    #: never reconciled the local bucket with the provider's view at all, and never
    #: learned the provider's real limits. Non-streaming requests did. That made the
    #: gateway's rate-limit behaviour depend on which code path happened to be used.
    headers: Optional[dict] = None

    @property
    def text(self) -> str:
        return "".join(self.content_parts)

    def ttft(self) -> Optional[float]:
        """Seconds from send to first CONTENT token. None when no content arrived."""
        return None if self.model_ttft is None else self.model_ttft - self.t_sent

    def delta_latency(self) -> Optional[float]:
        return None if self.first_delta is None else self.first_delta - self.t_sent


def parse_sse_line(line: str) -> Optional[dict]:
    """One `data:` line -> dict, or None for comments/blank/[DONE]/bad JSON."""
    line = line.strip()
    if not line or line.startswith(":"):
        return None
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def delta_text(frame: dict) -> str:
    """The content string a frame carries, or "" if it carries none.

    A frame with `delta.role` and no `content` is a real frame and NOT a first
    token; returning "" for it is what keeps model_ttft honest.
    """
    choices = frame.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    return delta.get("content") or ""


def usage_from(frame: dict) -> Optional[dict]:
    u = frame.get("usage")
    return u if isinstance(u, dict) else None


async def consume(lines: AsyncIterator[str], clock, t_sent: float,
                  deadline_at: Optional[float] = None,
                  headers: Optional[dict] = None) -> StreamTimings:
    """Read an SSE line iterator, stamping each frame AS IT ARRIVES.

    Stamping at arrival is the whole point. An earlier version buffered frames
    until the first content arrived and stamped during replay, which made
    `first_delta` and `model_ttft` identical within microseconds -- the role-only
    frame's real arrival time was destroyed by the buffering. The two numbers then
    looked like one measurement and the distinction was gone (BUG-017).

    `deadline_at` applies to the FIRST CONTENT frame only: a connection that is
    open and emitting role frames but has produced no content by the deadline has
    failed, while one that has started answering is merely slow and is allowed to
    finish.
    """
    st = StreamTimings(t_sent=t_sent, headers=headers)
    async for raw in lines:
        now = clock.now()
        frame = parse_sse_line(raw)
        if frame is None:
            continue
        if st.first_delta is None:
            st.first_delta = now
        st.n_deltas += 1
        txt = delta_text(frame)
        if txt:
            if st.model_ttft is None:
                st.model_ttft = now
            st.content_parts.append(txt)
        u = usage_from(frame)
        if u:
            st.usage = u
        if (deadline_at is not None and st.model_ttft is None
                and now >= deadline_at):
            raise TimeoutError("no content before the deadline")
    st.t_end = clock.now()
    if st.model_ttft is None:
        raise TimeoutError("stream ended with no content")
    return st
