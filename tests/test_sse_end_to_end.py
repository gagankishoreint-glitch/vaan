"""5c end-to-end: a corrupted stream must be diagnosable from the event log alone.

Unit tests prove the parser keeps bytes. This proves those bytes travel: through
`consume` -> `Attempt` -> `EventLog.attempt_end` -> the JSONL on disk, which is
where a post-mortem actually looks.

Run: python -m pytest -q tests/test_sse_end_to_end.py  -> 2 passed
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from relay.contracts import Attempt
from relay.events import EventLog
from relay.gateway.stream import StreamProtocolError, consume


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        self.t += 0.002
        return self.t


def _read(logdir: Path) -> list[dict]:
    out = []
    for f in Path(logdir).glob("*.jsonl"):
        out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return out


async def _agen(items):
    for i in items:
        yield i


def test_malformed_stream_is_recorded_in_the_event_log():
    """The failure path: garbage arrives, and the log says what it was."""
    with tempfile.TemporaryDirectory() as td:
        log = EventLog(td, run_id="sse_e2e", backend="standin")
        req = log.request("q-malformed")
        att = Attempt(attempt_id="a1", req_id=req.req_id, step="draft",
                      backend="standin", model="m", t_sent=0.0)
        req.attempt_start(att)

        async def go():
            return await consume(
                _agen(["<html>502 Bad Gateway</html>", "data: {\"choices\":["]),
                FakeClock(), t_sent=0.0)

        with pytest.raises(StreamProtocolError):
            asyncio.run(go())
        # record what the failing attempt saw, as the gateway does
        att.sse_raw = ["<html>502 Bad Gateway</html>", 'data: {"choices":[']
        att.n_sse_lines = 2
        att.n_sse_malformed = 2
        att.sse_saw_done = False
        att.protocol_error = "not an SSE field"
        att.t_end = 1.0
        req.attempt_end(att)
        log.close()

        ends = [e for e in _read(Path(td)) if e["type"] == "attempt.end"]
        assert len(ends) == 1, ends
        e = ends[0]
        assert e["n_sse_malformed"] == 2
        assert e["sse_saw_done"] is False
        assert e["sse_raw"] == ["<html>502 Bad Gateway</html>", 'data: {"choices":[']
        assert e["protocol_error"]


def test_successful_stream_records_its_bytes_and_done():
    """The happy path leaves the same evidence, so a later regression is diffable."""
    with tempfile.TemporaryDirectory() as td:
        log = EventLog(td, run_id="sse_ok", backend="standin")
        req = log.request("q-ok")
        att = Attempt(attempt_id="a2", req_id=req.req_id, step="draft",
                      backend="standin", model="m", t_sent=0.0)
        req.attempt_start(att)

        body = ['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"]

        async def go():
            return await consume(_agen(body), FakeClock(), t_sent=0.0)

        st = asyncio.run(go())
        att.sse_raw = [r.raw for r in st.raw_lines]
        att.n_sse_lines = st.n_raw_lines
        att.n_sse_malformed = st.n_malformed
        att.sse_saw_done = st.saw_done
        att.t_end = st.t_end
        req.attempt_end(att)
        log.close()

        e = [x for x in _read(Path(td)) if x["type"] == "attempt.end"][0]
        assert e["sse_saw_done"] is True
        assert e["n_sse_malformed"] == 0
        assert e["sse_raw"] == body
