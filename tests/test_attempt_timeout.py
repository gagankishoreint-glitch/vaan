"""Item A: the per-attempt timeout, separate from the outer deadline.

`gateway.attempt_timeout_s` was declared in config and read by nobody. Two different
limits are in play and conflating them is the easy mistake:

  attempt_timeout_s   one HTTP attempt. Expiry is RETRYABLE.
  deadline_s          the whole logical call. Expiry ENDS the request.

The attempt gets the SMALLER of (remaining deadline, attempt_timeout_s), so a
per-attempt cap can never extend the outer deadline -- the failure mode that makes
"just add a timeout" dangerous.

Run: python -m pytest -q tests/test_attempt_timeout.py  -> 8 passed
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


class FakeClock:
    """Monotonic, and `sleep` advances it. No real waiting in these tests."""

    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.t += seconds


class _Scope:
    def __init__(self, log):
        self.log = log
        self.req = log.request("attempt-timeout")
        self.req_id = self.req.req_id

    def attempt_start(self, a):
        return self.req.attempt_start(a)

    def attempt_end(self, a):
        return self.req.attempt_end(a)

    def emit(self, *a, **k):
        return self.log.emit(*a, **k)


def _gw(handler, *, attempt_timeout_s=None, policy="managed", max_attempts=3):
    from relay.events import EventLog
    cfg = load_config()
    td = tempfile.mkdtemp()
    log = EventLog(td, run_id="at", backend="standin")
    clock = FakeClock()
    gw = Gateway.from_config(
        cfg, clock, log, base_url="https://x.test/openai/v1", api_key="k",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                 base_url="https://x.test/openai/v1"),
        policy=policy)
    gw.attempt_timeout_s = attempt_timeout_s
    gw.max_attempts = max_attempts
    return gw, log, Path(td)


def _ends(td: Path) -> list[dict]:
    out = []
    for f in td.glob("*.jsonl"):
        out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return [e for e in out if e["type"] == "attempt.end"]


def _run(gw, log, *, deadline_s=5.0):
    scope = _Scope(log)

    async def go():
        try:
            return await gw.call(scope=scope, step="draft", model="m",
                                 messages=[{"role": "user", "content": "hi"}],
                                 max_tokens=10, deadline_s=deadline_s)
        finally:
            await gw.client.aclose()
            log.close()

    return asyncio.run(go())


# ------------------------------------------------------- the budget decision

def test_attempt_timeout_wins_when_it_is_smaller():
    gw, _, _ = _gw(lambda r: httpx.Response(200), attempt_timeout_s=2.0)
    budget, why = gw._attempt_budget(deadline_s=30.0, t_start=gw.clock.now())
    assert (budget, why) == (2.0, "attempt_timeout")


def test_deadline_wins_when_it_is_smaller():
    """The floor of 1.0 s is preserved: a nearly-spent deadline still tries once."""
    gw, _, _ = _gw(lambda r: httpx.Response(200), attempt_timeout_s=60.0)
    budget, why = gw._attempt_budget(deadline_s=0.2, t_start=gw.clock.now())
    assert why == "deadline"
    assert budget == pytest.approx(1.0), budget


def test_null_attempt_timeout_means_no_cap():
    """null in config must NOT become an invented number."""
    gw, _, _ = _gw(lambda r: httpx.Response(200), attempt_timeout_s=None)
    budget, why = gw._attempt_budget(deadline_s=7.0, t_start=gw.clock.now())
    assert (budget, why) == (7.0, "deadline")


def test_attempt_timeout_can_never_extend_the_outer_deadline():
    """The important safety property, checked over a range of settings."""
    gw, _, _ = _gw(lambda r: httpx.Response(200), attempt_timeout_s=100.0)
    for deadline in (0.1, 1.0, 5.0, 30.0):
        budget, _ = gw._attempt_budget(deadline_s=deadline, t_start=gw.clock.now())
        assert budget <= max(1.0, deadline), (deadline, budget)


# ------------------------------------------------------- the failure path

def test_hung_attempt_is_retried_and_each_attempt_records_its_own_end():
    """The stand-in 'hang' mode: the response never completes.

    A per-attempt expiry must be RETRYABLE, and every attempt must leave an
    `attempt.end` -- so a retried request cannot look like a single attempt.
    """
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        await asyncio.sleep(3600)          # hang: simulates STANDIN_HANG_S
        return httpx.Response(200, json={"choices": []})

    gw, log, td = _gw(handler, attempt_timeout_s=0.05, max_attempts=3)

    with pytest.raises(Exception):
        _run(gw, log, deadline_s=30.0)

    ends = _ends(td)
    assert len(ends) >= 2, (
        f"expected several attempts, each with its own attempt.end; got {len(ends)}")
    assert all(e["outcome"] == "timeout" for e in ends), [e["outcome"] for e in ends]
    assert all(e["attempt_timed_out"] is True for e in ends), (
        "a per-attempt expiry must be flagged, or it is indistinguishable from the "
        "outer deadline in the log")
    assert all(e["timeout_limit"] == "attempt_timeout" for e in ends)
    assert calls["n"] >= 2, "the attempt was not retried"


def test_attempt_timeout_does_not_sleep_past_the_deadline():
    """Retries must respect the outer deadline, not just the per-attempt cap."""
    async def handler(request):
        await asyncio.sleep(3600)
        return httpx.Response(200)

    gw, log, td = _gw(handler, attempt_timeout_s=0.05, max_attempts=50)
    with pytest.raises(Exception):
        _run(gw, log, deadline_s=2.0)

    # FakeClock advanced by the sleeps; the whole call must stop near the deadline.
    assert gw.clock.now() <= 2.0 + 5.0, (
        f"call ran to t={gw.clock.now()} against a 2.0 s deadline")


def test_outer_deadline_expiry_is_not_flagged_as_an_attempt_timeout():
    """The two causes must stay distinguishable in the log."""
    async def handler(request):
        await asyncio.sleep(3600)
        return httpx.Response(200)

    gw, log, td = _gw(handler, attempt_timeout_s=None, max_attempts=1)
    with pytest.raises(Exception):
        _run(gw, log, deadline_s=1.0)

    ends = _ends(td)
    assert ends, "an attempt.end must still be written"
    assert ends[0]["attempt_timed_out"] is False
    assert ends[0]["timeout_limit"] == "deadline"


def test_successful_attempt_records_no_timeout_flag():
    """Absence of a timeout must be visible, not merely implied."""
    def handler(request):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    gw, log, td = _gw(handler, attempt_timeout_s=5.0, max_attempts=1)
    _run(gw, log, deadline_s=10.0)
    e = _ends(td)[0]
    assert e["outcome"] == "ok"
    assert e["attempt_timed_out"] is None, e["attempt_timed_out"]
