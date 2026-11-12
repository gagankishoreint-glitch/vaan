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
    #: floor, so streamed attempts never reconciled the local bucket with the
    #: provider's view and never learned the provider's real limits; non-streaming
    #: requests did. That made the gateway's rate-limit behaviour depend on which
    #: code path happened to be used -- a mode-dependent bug, settled only when the
    #: streamed path was brought to parity. (`pipeline.stream` defaults to false, so
    #: this was latent rather than universal, and would have bitten the moment
    #: streaming was enabled.)
    headers: Optional[dict] = None
    #: Every line received, verbatim, with its parse outcome. Bounded: a runaway
    #: stream must not be able to exhaust memory through the event log. `n_raw_lines`
    #: counts everything seen; `raw_lines` keeps the first and last few.
    raw_lines: list[RawLine] = field(default_factory=list)
    n_raw_lines: int = 0
    n_malformed: int = 0
    #: First malformed line's text and error, kept even if `raw_lines` is trimmed.
    first_malformed: Optional[str] = None
    first_malformed_error: Optional[str] = None
    #: True when the provider sent `[DONE]`. A stream that ends WITHOUT this was cut
    #: short -- the content may be incomplete, which is not the same as a clean end.
    saw_done: bool = False

    @property
    def text(self) -> str:
        return "".join(self.content_parts)

    def ttft(self) -> Optional[float]:
        """Seconds from send to first CONTENT token. None when no content arrived."""
        return None if self.model_ttft is None else self.model_ttft - self.t_sent

    def delta_latency(self) -> Optional[float]:
        return None if self.first_delta is None else self.first_delta - self.t_sent


class StreamProtocolError(Exception):
    """The bytes on the wire were not a stream we can interpret.

    Distinct from TimeoutError on purpose: a timeout means the provider was slow, this
    means the provider (or a proxy) sent something unintelligible. They want different
    responses -- one retries, the other should be investigated.
    """


#: Line shapes an SSE stream can legally contain that are NOT data frames. They are
#: not errors and must not be recorded as malformed.
_NON_DATA_PREFIXES = ("event:", "id:", "retry:", ":")


@dataclass
class RawLine:
    """One line as received, and what it parsed to.

    `raw` is the line VERBATIM (trailing newline stripped, nothing else). Keeping it
    is the point: when a stream fails, the question "what did the provider actually
    send" has to be answerable from the event log alone. The previous parser threw
    unparseable lines away, so a stream that delivered nothing and a stream that
    delivered garbage produced the identical outcome -- `TimeoutError`, no evidence.
    """
    raw: str
    kind: str                 # frame | done | blank | comment | event | malformed
    frame: Optional[dict] = None
    error: Optional[str] = None


def parse_sse_line_verbose(line: str) -> RawLine:
    """Parse one SSE line, never discarding it and never raising.

    Tolerant on purpose. Providers differ in framing: some send `data:` with a space,
    some without; some emit `event:`/`id:`/`retry:` fields; some emit JSON split oddly
    or with a BOM; a proxy may inject an HTML error page mid-stream. The old parser
    answered all of that with `None`, which made real corruption invisible.

    Returns a `RawLine` for EVERY input, including blanks and malformed JSON, so the
    caller can decide. `kind == "malformed"` is the only case that carries `error`.
    """
    if line is None:
        return RawLine(raw="", kind="blank")
    raw = line.rstrip("\r\n")
    stripped = raw.strip()
    if not stripped:
        return RawLine(raw=raw, kind="blank")
    # A BOM may appear on the first line of a stream; strip it before dispatching.
    if stripped.startswith("\ufeff"):
        stripped = stripped.lstrip("\ufeff")
        raw = stripped
    if stripped.startswith(":"):
        return RawLine(raw=raw, kind="comment")
    for pfx in _NON_DATA_PREFIXES:
        if pfx == ":":
            continue
        if stripped.startswith(pfx):
            return RawLine(raw=raw, kind="event")
    if not stripped.startswith("data:"):
        # Not an SSE field at all: an HTML error page, a bare `[DONE]`, a truncated
        # chunk. Recorded rather than dropped.
        if stripped == "[DONE]":
            return RawLine(raw=raw, kind="done")
        return RawLine(raw=raw, kind="malformed",
                       error=f"not an SSE field: {stripped[:80]!r}")
    payload = stripped[5:].strip()
    if not payload:
        return RawLine(raw=raw, kind="blank")
    if payload == "[DONE]":
        return RawLine(raw=raw, kind="done")
    try:
        frame = json.loads(payload)
    except json.JSONDecodeError as e:
        return RawLine(raw=raw, kind="malformed", error=f"{e}: {payload[:120]!r}")
    if not isinstance(frame, dict):
        return RawLine(raw=raw, kind="malformed",
                       error=f"data frame is {type(frame).__name__}, not an object")
    return RawLine(raw=raw, kind="frame", frame=frame)


def parse_sse_line(line: str) -> Optional[dict]:
    """Back-compat shim: frame dict, or None for anything else.

    Kept because the old contract is referenced by tests and reads well for callers
    that genuinely only want the frame. New code should use
    `parse_sse_line_verbose`, which does not destroy the evidence.
    """
    got = parse_sse_line_verbose(line)
    return got.frame if got.kind == "frame" else None


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


#: How many verbatim lines to retain per attempt. Enough to diagnose a failure,
#: small enough that a 10-minute stream cannot blow up the event log.
RAW_LINE_CAP = 40


def _record(st: StreamTimings, got: RawLine) -> None:
    """Bounded, lossless-where-it-matters recording of one line."""
    st.n_raw_lines += 1
    if got.kind == "malformed":
        st.n_malformed += 1
        if st.first_malformed is None:
            st.first_malformed = got.raw
            st.first_malformed_error = got.error
    if len(st.raw_lines) < RAW_LINE_CAP:
        st.raw_lines.append(got)
    elif st.n_raw_lines % 100 == 0:
        # keep a liveness trace without holding every line
        st.raw_lines.append(RawLine(raw="", kind="truncated-marker"))


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
        got = parse_sse_line_verbose(raw)
        _record(st, got)
        frame = got.frame
        if got.kind == "done":
            st.saw_done = True
            continue
        if frame is None:
            # blank / comment / event field / malformed: none of these is a delta.
            # Malformed lines are RECORDED (above) and are not silently equivalent
            # to a quiet stream.
            if got.kind == "malformed" and st.first_delta is None:
                # A stream that opens with garbage is a provider/proxy fault, not a
                # slow model. Surface it now rather than waiting for the deadline.
                raise StreamProtocolError(
                    f"stream opened with a non-SSE line: {got.error}")
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
        if st.n_malformed and st.n_malformed == st.n_raw_lines:
            raise StreamProtocolError(
                f"stream contained only malformed lines ({st.n_malformed}); "
                f"first: {st.first_malformed_error}")
        raise TimeoutError("stream ended with no content")
    return st
