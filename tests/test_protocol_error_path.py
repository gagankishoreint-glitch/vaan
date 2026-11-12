"""5c follow-up: what the gateway DOES with a StreamProtocolError.

The parser raising it is only half a feature. Before this, nothing in the gateway
caught `StreamProtocolError`, so it escaped `Gateway.call()` as an unhandled
exception -- the pipeline would see a raw exception rather than a terminal reply, and
no `attempt.end` would be written for the failing attempt.

Policy, decided here and pinned:
  * outcome    SERVER_ERROR (retryable), NOT TIMEOUT -- different causes
  * breaker    counts as a FAILURE (the provider returned unusable bytes)
  * retry      obeys `_next_delay`, exactly like a 5xx, so the deadline still binds
  * surface    if no retry is available, it propagates as StreamProtocolError
  * log        `protocol_error` distinguishes it from a real 5xx

No new `Outcome` member: `Outcome` lives in contracts.py, and SERVER_ERROR is the
correct severity.

Run: python -m pytest -q tests/test_protocol_error_path.py  -> 3 passed
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from relay.config import load_config
from relay.gateway.gateway import Gateway
from relay.gateway.stream import StreamProtocolError


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        self.t += 0.01
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.t += seconds


class _Scope:
    def __init__(self, log):
        self.log = log
        self.req = log.request("proto-err")
        self.req_id = self.req.req_id

    def attempt_start(self, a):
        return self.req.attempt_start(a)

    def attempt_end(self, a):
        return self.req.attempt_end(a)

    def emit(self, *a, **k):
        return self.log.emit(*a, **k)


def _gateway(handler, policy="managed"):
    cfg = load_config()
    td = tempfile.mkdtemp()
    from relay.events import EventLog
    log = EventLog(td, run_id="proto", backend="standin")
    clock = FakeClock()
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport,
                               base_url="https://x.test/openai/v1")
    gw = Gateway.from_config(cfg, clock, log, base_url="https://x.test/openai/v1",
                            api_key="k", client=client, policy=policy)
    return gw, log, td, client


def _events(td: Path) -> list[dict]:
    out = []
    for f in Path(td).glob("*.jsonl"):
        out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return out


def test_garbage_stream_is_recorded_as_server_error_not_timeout():
    """The failure path: a 200 whose body is not SSE."""
    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"},
            content=b"<html>502 Bad Gateway</html>\n")

    gw, log, td, client = _gateway(handler)
    scope = _Scope(log)

    async def go():
        try:
            await gw.call(scope=scope, step="draft", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=0.5, stream=True)
        except StreamProtocolError:
            pass
        finally:
            await client.aclose()
            log.close()

    asyncio.run(go())
    ends = [e for e in _events(Path(td)) if e["type"] == "attempt.end"]
    assert ends, "the failing attempt must still write attempt.end"
    e = ends[0]
    assert e["outcome"] == "server_error", e["outcome"]
    assert e["outcome"] != "timeout", "a protocol fault is not a timeout"
    assert e.get("protocol_error"), "the fault text must reach the log"
    assert e.get("sse_raw"), "the offending bytes must reach the log"


def test_breaker_counts_a_protocol_error_as_a_failure():
    """Unusable bytes are a provider fault; the breaker must see it."""
    def handler(request):
        return httpx.Response(200, content=b"not a stream at all\n")

    gw, log, td, client = _gateway(handler)
    scope = _Scope(log)
    before = gw.breaker.fails

    async def go():
        try:
            await gw.call(scope=scope, step="draft", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=0.3, stream=True)
        except StreamProtocolError:
            pass
        finally:
            await client.aclose()
            log.close()

    asyncio.run(go())
    assert gw.breaker.fails > before, (
        "a protocol error left the breaker untouched, so a provider emitting garbage "
        "would never trip it")


def test_protocol_error_surfaces_when_no_retry_is_available():
    """Naive policy = 1 attempt, so the error must reach the caller."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, content=b"garbage\n")

    gw, log, td, client = _gateway(handler, policy="naive")
    scope = _Scope(log)

    async def go():
        with pytest.raises(StreamProtocolError):
            await gw.call(scope=scope, step="draft", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=0.3, stream=True)
        await client.aclose()
        log.close()

    asyncio.run(go())
    assert calls["n"] >= 1
