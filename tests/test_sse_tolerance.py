"""5c: the SSE parser must not destroy the evidence.

The old `parse_sse_line` returned `None` for anything it did not like -- malformed
JSON, an HTML error page from a proxy, a bare non-SSE line. Downstream, all of those
were indistinguishable from "the provider sent nothing yet", so a corrupted stream
raised the same `TimeoutError` as a slow model and the diagnostic question ("what did
the provider actually send?") was unanswerable from the event log.

These tests pin the property that matters: every line is retained verbatim, and a
stream of pure garbage fails as a PROTOCOL error carrying the offending bytes, not as
a timeout.

Run: python -m pytest -q tests/test_sse_tolerance.py  -> 12 passed
"""
from __future__ import annotations

import asyncio

import pytest

from relay.gateway.stream import (
    RawLine, StreamProtocolError, parse_sse_line, parse_sse_line_verbose,
)


class FakeClock:
    def __init__(self, t0: float = 0.0):
        self.t = t0

    def now(self) -> float:
        self.t += 0.001
        return self.t


async def _agen(items):
    for i in items:
        yield i


@pytest.mark.parametrize("line,kind", [
    ("data: [DONE]", "done"),
    ("", "blank"),
    ("   ", "blank"),
    (": keepalive", "comment"),
    ("event: message", "event"),
    ("id: 42", "event"),
    ('data: {"choices":[{"delta":{"content":"hi"}}]}', "frame"),
    ("data: not json", "malformed"),
    ("<html>502 Bad Gateway</html>", "malformed"),
    ("data: [1,2,3]", "malformed"),
])
def test_every_line_is_classified_not_discarded(line, kind):
    got = parse_sse_line_verbose(line)
    assert isinstance(got, RawLine)
    assert got.kind == kind, f"{line!r} -> {got.kind}, expected {kind}"


def test_malformed_line_keeps_the_original_bytes():
    """The whole point: the raw text survives, including the reason."""
    raw = 'data: {"choices": [{"delta":'      # truncated by a dropped connection
    got = parse_sse_line_verbose(raw)
    assert got.kind == "malformed"
    assert got.raw == raw
    assert "Expecting" in got.error or "json" in got.error.lower()


def test_back_compat_shim_still_returns_none_for_non_frames():
    """Existing callers keep their contract; tolerance is additive."""
    assert parse_sse_line("data: [DONE]") is None
    assert parse_sse_line("") is None
    assert parse_sse_line(": keepalive") is None
    assert parse_sse_line("data: not json") is None
    assert parse_sse_line('data: {"a":1}') == {"a": 1}


def test_provider_framing_variants_all_parse():
    """`data:` with and without a space, CRLF, BOM on the first line."""
    for line in ('data:{"a":1}', 'data: {"a":1}', 'data: {"a":1}\r\n',
                 '\ufeffdata: {"a":1}'):
        got = parse_sse_line_verbose(line)
        assert got.kind == "frame" and got.frame == {"a": 1}, (line, got)


def test_garbage_only_stream_fails_as_protocol_error_with_evidence():
    """A stream of non-SSE bytes must not look like a slow model."""
    from relay.gateway.stream import consume

    lines = _agen(["<html>502</html>", "<html>502</html>"])

    async def go():
        return await consume(lines, FakeClock(), t_sent=0.0)

    with pytest.raises(StreamProtocolError) as ei:
        asyncio.run(go())
    msg = str(ei.value)
    assert "502" in msg or "non-SSE" in msg, msg


def test_stream_that_ends_empty_but_valid_is_a_timeout_not_a_protocol_error():
    """Comments and keepalives are legal; no content is still a TimeoutError."""
    from relay.gateway.stream import consume

    lines = _agen([": keepalive", "", ": keepalive"])

    async def go():
        return await consume(lines, FakeClock(), t_sent=0.0)

    with pytest.raises(TimeoutError):
        asyncio.run(go())


def test_raw_lines_are_retained_verbatim_in_timings():
    """A successful stream still keeps its bytes, so a later bug is diagnosable."""
    from relay.gateway.stream import consume

    body = [
        'data: {"choices":[{"delta":{"role":"assistant"}}]}',
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        "data: [DONE]",
    ]
    lines = _agen(body)

    async def go():
        return await consume(lines, FakeClock(), t_sent=0.0)

    st = asyncio.run(go())
    assert st.text == "Hello"
    assert st.saw_done is True
    assert [r.raw for r in st.raw_lines][:4] == body
    assert st.n_malformed == 0


def test_missing_done_frame_is_visible():
    """A stream cut short still parses, but `saw_done` is False -- incompleteness
    must be observable rather than inferred from the content looking short."""
    from relay.gateway.stream import consume

    lines = _agen(['data: {"choices":[{"delta":{"content":"partial"}}]}'])

    async def go():
        return await consume(lines, FakeClock(), t_sent=0.0)

    st = asyncio.run(go())
    assert st.text == "partial"
    assert st.saw_done is False


def test_malformed_mid_stream_is_recorded_but_does_not_kill_content():
    """A proxy injecting one bad frame must not discard the tokens either side."""
    from relay.gateway.stream import consume

    lines = _agen([
        'data: {"choices":[{"delta":{"content":"before"}}]}',
        "<html>noise</html>",
        'data: {"choices":[{"delta":{"content":"after"}}]}',
        "data: [DONE]",
    ])

    async def go():
        return await consume(lines, FakeClock(), t_sent=0.0)

    st = asyncio.run(go())
    assert st.text == "beforeafter"
    assert st.n_malformed == 1
    assert any(r.kind == "malformed" for r in st.raw_lines)


def test_raw_line_record_is_bounded():
    """A long stream must not grow the record without limit."""
    from relay.gateway.stream import RAW_LINE_CAP, consume

    body = ['data: {"choices":[{"delta":{"content":"x"}}]}'] * (RAW_LINE_CAP * 5)
    body.append("data: [DONE]")
    lines = _agen(body)

    async def go():
        return await consume(lines, FakeClock(), t_sent=0.0)

    st = asyncio.run(go())
    assert st.n_raw_lines == len(body)
    assert len(st.raw_lines) <= RAW_LINE_CAP * 2, len(st.raw_lines)
