"""BUG-043: a non-200 on a STREAMED request must behave like the buffered path.

Run: /tmp/auditenv/bin/python -m pytest -q tests/test_stream_http_error.py

Before this, `_streamed_call` raised the private `_StreamHTTPError` on any non-200 and
NOTHING caught it. Measured with max_attempts=3 and one 500: 1 attempt, breaker
still closed, no attempt.end. Three consequences, each pinned below:

  1. no retry        -- one 500 ended a request with two attempts left
  2. breaker blind   -- a streamed 5xx never counted as a failure
  3. no attempt.end  -- the attempt was charged and invisible (BUG-023's hole)

Classification is by STATUS, from the same table the buffered path uses, so a 429 and
a 500 cannot mean one thing streamed and another buffered.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from relay.config import load_config
from relay.events import EventLog
from relay.gateway.gateway import (
    DeadlineExceeded, Gateway, UpstreamError, _StreamHTTPError,
)


def _Scope(log, rid="s"):
    """A REAL RequestScope.

    An earlier stub implemented `attempt_end` as a no-op, which made every
    "attempt.end was written" assertion vacuous -- the events could not exist
    regardless of the code under test. The log is the evidence; the scope must be
    the real one so the evidence is actually written.
    """
    from relay.events import RequestScope
    return RequestScope(log, rid)


def _gateway(handler, *, policy="managed", max_attempts=3):
    cfg = load_config()
    td = tempfile.mkdtemp()
    log = EventLog(td, run_id="s", backend="standin")
    client = httpx.AsyncClient(
        base_url="http://127.0.0.1:8009/openai/v1",
        transport=httpx.MockTransport(handler))
    gw = Gateway.from_config(cfg, clock=_clock(), log=log,
                             base_url="http://127.0.0.1:8009/openai/v1",
                             api_key="x", client=client, policy=policy)
    gw.max_attempts = max_attempts
    gw.breaker.fail_threshold = 99      # tests that want the breaker set it lower
    return gw, log, td, client


def _clock():
    from relay.clock import RealClock
    return RealClock()


def _events(td):
    with open(Path(td) / "events.jsonl", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


#: A 500 carries no `retry-after`, so the gateway falls back to a 1.0 s wait before
#: retrying. A deadline under 1 s therefore makes "no retry" the CORRECT outcome, and
#: a test that used one would pass whether or not the bug was fixed. Every test that
#: asserts a retry must leave room for that wait.
DEADLINE = 5.0


async def _call(gw, scope, stream=True, deadline=DEADLINE):
    return await gw.call(scope=scope, step="draft", model="m",
                         messages=[{"role": "user", "content": "hi"}],
                         max_tokens=10, deadline_s=deadline, stream=stream)


def _status_handler(status, headers=None, body=b"boom"):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(status, content=body, headers=headers or {})
    return handler, calls


# ---------------------------------------------------------------- 1. retry

def test_a_streamed_500_is_RETRIED_not_fatal():
    """The regression test for BUG-043: a 500 must not end the request at once.

    The retry budget, not `max_attempts`, is the binding limit here:
    `retry_budget_ratio` 0.1 per call against a `retry_credit_floor` of 1.0 means ONE
    retry is affordable, so 2 HTTP attempts is correct and 3 would mean the credit
    was ignored. The old streamed path made exactly 1 -- no retry at all.
    """
    handler, calls = _status_handler(500)
    gw, log, td, client = _gateway(handler)

    async def go():
        scope = _Scope(log)
        try:
            await _call(gw, scope)
        except UpstreamError:
            pass
        finally:
            await client.aclose()
            log.close()

    asyncio.run(go())
    assert calls["n"] == 2, (
        f"{calls['n']} HTTP attempts; the retry credit affords exactly 1 retry and the "
        f"old code made 0 because _StreamHTTPError escaped the retry loop")


# ---------------------------------------------------------------- 2. breaker

def test_a_streamed_5xx_counts_as_a_breaker_failure():
    handler, _ = _status_handler(500)
    gw, log, td, client = _gateway(handler)
    before = gw.breaker.fails

    async def go():
        try:
            await _call(gw, _Scope(log))
        except UpstreamError:
            pass
        finally:
            await client.aclose()
            log.close()

    asyncio.run(go())
    assert gw.breaker.fails > before, (
        "a streamed 5xx left the breaker untouched, so a provider failing only on "
        "the stream path would never trip it")


def test_a_streamed_5xx_storm_opens_the_breaker_and_blocks_further_calls():
    handler, calls = _status_handler(500)
    gw, log, td, client = _gateway(handler)
    gw.breaker.fail_threshold = 3

    async def go():
        for _ in range(2):
            try:
                await _call(gw, _Scope(log))
            except UpstreamError:
                pass
        n_after_two = calls["n"]
        # 2 failures per call (attempt + retry) against fail_threshold 3, so the
        # breaker is open after the first call's retry and the second call is refused
        # before any HTTP is sent.
        try:
            await _call(gw, _Scope(log))
        except Exception:
            pass
        finally:
            await client.aclose()
            log.close()
        return n_after_two

    n_after_two = asyncio.run(go())
    assert calls["n"] == n_after_two, (
        "the breaker was open but the streamed path still sent HTTP requests")


# ---------------------------------------------------------------- 3. attempt.end

def test_every_failed_streamed_attempt_writes_attempt_end():
    handler, _ = _status_handler(503)
    gw, log, td, client = _gateway(handler)

    async def go():
        try:
            await _call(gw, _Scope(log))
        except UpstreamError:
            pass
        finally:
            await client.aclose()
            log.close()

    asyncio.run(go())
    ends = [e for e in _events(td) if e["type"] == "attempt.end"]
    # 2 = the first attempt plus the one retry the credit affords (see above).
    assert len(ends) == 2, f"expected one attempt.end per HTTP attempt, got {len(ends)}"
    for e in ends:
        assert e["outcome"] == "server_error", e["outcome"]
        assert e["status"] == 503, e


def test_the_attempt_end_carries_the_error_body_for_the_log():
    handler, _ = _status_handler(500, body=b"upstream exploded")
    gw, log, td, client = _gateway(handler, max_attempts=1)

    async def go():
        try:
            await _call(gw, _Scope(log))
        except UpstreamError:
            pass
        finally:
            await client.aclose()
            log.close()

    asyncio.run(go())
    e = [e for e in _events(td) if e["type"] == "attempt.end"][0]
    assert "upstream exploded" in (e.get("error_body") or ""), e.get("error_body")


# ---------------------------------------------------------------- 4. classification

def test_a_streamed_429_minute_limit_is_rate_limited_min():
    handler, _ = _status_handler(429, headers={"retry-after": "2"})
    gw, log, td, client = _gateway(handler, max_attempts=1)

    async def go():
        try:
            await _call(gw, _Scope(log))
        except UpstreamError:
            pass
        finally:
            await client.aclose()
            log.close()

    asyncio.run(go())
    e = [e for e in _events(td) if e["type"] == "attempt.end"][0]
    assert e["outcome"] == "rate_limited_min", e["outcome"]


def test_a_streamed_day_limit_429_is_budget_gone_not_upstream():
    """A provider day limit is a BUDGET refusal on the stream path too (BUG-042)."""
    handler, _ = _status_handler(
        429, headers={"retry-after": "120",
                      "x-ratelimit-remaining-requests": "0"})
    gw, log, td, client = _gateway(handler, max_attempts=1)

    async def go():
        try:
            await _call(gw, _Scope(log))
        except DeadlineExceeded:
            return "budget"
        except UpstreamError:
            return "upstream"
        finally:
            await client.aclose()
            log.close()

    assert asyncio.run(go()) == "budget"


def test_a_streamed_413_is_too_large():
    handler, _ = _status_handler(413)
    gw, log, td, client = _gateway(handler, max_attempts=1)

    async def go():
        try:
            await _call(gw, _Scope(log))
        except Exception:
            pass
        finally:
            await client.aclose()
            log.close()

    asyncio.run(go())
    e = [e for e in _events(td) if e["type"] == "attempt.end"][0]
    assert e["outcome"] == "too_large", e["outcome"]


# ---------------------------------------------------------------- 5. reason

@pytest.mark.asyncio
async def test_a_streamed_500_storm_ends_as_upstream_error_in_the_pipeline():
    """End to end: the reason a user sees, not just the exception type."""
    from relay.pipeline.pipeline import REASON_NAMES
    assert REASON_NAMES[UpstreamError] == "upstream_error"


def test_the_naive_policy_still_surfaces_the_error_immediately():
    """The naive policy ignores `retry-after` and retries a fixed number of times.

    `max_attempts` is the MANAGED cap. NAIVE reads `gateway.naive_max_attempts`
    (5), which is the point of the comparison: it keeps hammering a provider that
    asked for quiet. This test pins that the STREAMED path obeys the same policy as
    the buffered one -- 5, not 1 and not 3.
    """
    handler, calls = _status_handler(500)
    gw, log, td, client = _gateway(handler, policy="naive", max_attempts=1)

    async def go():
        try:
            await _call(gw, _Scope(log))
        except UpstreamError:
            pass
        finally:
            await client.aclose()
            log.close()

    asyncio.run(go())
    assert calls["n"] == 5, (
        f"{calls['n']} attempts; NAIVE uses gateway.naive_max_attempts (5), and the "
        f"streamed path must follow the same policy as the buffered one")


# ---------------------------------------------------------------- end to end
def test_a_streamed_500_storm_reaches_the_user_as_upstream_error():
    """The whole chain: streamed 500 -> UpstreamError -> pipeline -> reason + text.

    The pipeline half is exercised directly, because `answer()` needs a retriever and
    a corpus this sandbox does not have. What is checked here is that the exception
    the streamed path now raises maps to the reason a user sees, and that the text
    does not claim a budget problem.
    """
    from relay.pipeline.pipeline import REASON_MESSAGES, REASON_NAMES, reason_for

    handler, calls = _status_handler(500)
    gw, log, td, client = _gateway(handler)

    async def go():
        err = None
        try:
            await _call(gw, _Scope(log))
        except UpstreamError as e:
            err = e
        finally:
            await client.aclose()
            log.close()
        return err

    err = asyncio.run(go())
    assert err is not None, "a streamed 500 storm raised nothing"
    assert calls["n"] >= 2, "no retry happened, so this is not the real path"
    reason, message = reason_for(err)
    assert reason == "upstream_error", reason
    assert REASON_NAMES[UpstreamError] == "upstream_error"
    assert REASON_MESSAGES[UpstreamError] == message
    assert "budget" not in message.lower(), (
        "a 500 storm must not read as a budget problem (BUG-042)")
