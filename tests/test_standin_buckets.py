"""5e: the stand-in's 429 must say WHICH bucket refused, and when it resets.

The old `_r429` had one `day` case that always reported `retry-after: 60`,
always `type: requests`, and always sent `reset-tokens` computed from the MINUTE
bucket. A client could not tell a per-day exhaustion from a per-minute one, and a
day 429 advertised a retry a few seconds away. Anything testing minute-vs-day
classification (Q-09) was therefore testing the stand-in's bug.

CALIBRATION: no real Groq response has been observed. The header names and the
"*-requests is per day" reading come from the docs table. Every claim about what
the REAL service sends is marked UNVERIFIED here and in docs/STANDIN.md.

Run: python -m pytest -q tests/test_standin_buckets.py  -> 6 passed
"""
from __future__ import annotations

import pytest

from relay.ratelimit_headers import parse_rl_headers
from relay.standin.server import Bucket, RefillBucket, StandIn


def _standin(**kw) -> StandIn:
    s = StandIn.__new__(StandIn)          # no __init__ side effects / no app state
    s.tpm, s.tpd, s.rpd = kw.get("tpm", 1000), kw.get("tpd", 100000), kw.get("rpd", 100)
    s.ttft_ms, s.tokens_per_s = 0.0, 1000.0
    s.error_rate = s.p429_rate = 0.0
    s.hang_s = s.slow_success = 0.0
    s.load_slowdown = 0.0
    s.seed = 7
    import random
    s._rng = random.Random(7)
    s.calls = 0
    import time
    now = time.monotonic()
    s.tpm_bucket = RefillBucket(s.tpm, 60.0, deficit=0.0, last=now)
    s.day_bucket = Bucket(s.tpd, 86400.0, reset_at=now + 86400.0)
    s.req_bucket = Bucket(s.rpd, 86400.0, reset_at=now + 86400.0)
    return s


def _hdr(resp) -> dict:
    return {k.lower(): v for k, v in resp.headers.items()}


def test_minute_429_reports_the_minute_bucket():
    s = _standin()
    s.tpm_bucket.deficit = s.tpm              # minute exhausted
    import time
    r = s._r429(time.monotonic(), "minute", "tokens-per-minute exhausted")
    h = _hdr(r)
    parsed = parse_rl_headers(h)
    assert r.status_code == 429
    assert parsed["remaining_tpm"] == 0
    assert parsed["reset_tpm_s"] is not None and parsed["reset_tpm_s"] > 0
    assert "retry-after" in h


def test_day_token_429_does_not_advertise_a_minute_reset():
    """The bug: a day 429 sent reset-tokens from the minute bucket."""
    s = _standin()
    import time
    now = time.monotonic()
    s.day_bucket.reset_at = now + 86400.0
    s.day_bucket.used = s.tpd
    r = s._r429(now, "day_tokens", "tokens-per-day exhausted")
    h = _hdr(r)
    ra = int(float(h["retry-after"]))
    assert ra > 3600, (
        f"a day-limit 429 must not tell the client to retry in {ra}s; "
        "the day bucket resets in ~86400s")
    assert h["x-standin-remaining-day-tokens"] == "0"
    assert float(h["x-standin-reset-day-tokens"].rstrip("s")) > 3600


def test_day_request_429_is_typed_as_requests():
    s = _standin()
    import time
    now = time.monotonic()
    s.req_bucket.reset_at = now + 86400.0
    s.req_bucket.used = s.rpd
    r = s._r429(now, "day_requests", "request-per-day exhausted")
    h = _hdr(r)
    assert r.body is not None
    import json as _json
    body = _json.loads(bytes(r.body))
    assert body["error"]["type"] == "requests", body
    assert int(h["x-ratelimit-remaining-requests"]) == 0


def test_three_buckets_are_independent():
    """Draining the day bucket must not move the minute counters, and vice versa."""
    s = _standin(tpm=1000, tpd=5000, rpd=10)
    s.day_bucket.used = 5000
    import time
    h = _hdr(s._r429(time.monotonic(), "day_tokens", "x"))
    # minute bucket untouched
    assert int(h["x-ratelimit-remaining-tokens"]) == 1000
    assert int(h["x-ratelimit-remaining-requests"]) == 10
    s2 = _standin(tpm=1000, tpd=5000, rpd=10)
    s2.tpm_bucket.deficit = 1000
    import time
    h2 = _hdr(s2._r429(time.monotonic(), "minute", "x"))
    assert int(h2["x-standin-remaining-day-tokens"]) == 5000


def test_day_token_headers_are_namespaced_as_standin():
    """A stand-in-only header must never look like a real Groq header."""
    s = _standin()
    import time
    h = _hdr(s._r429(time.monotonic(), "minute", "x"))
    for k in h:
        if "day" in k:
            assert k.startswith("x-standin-"), (
                f"{k!r} looks like a provider header but is a stand-in invention")


def test_bucket_model_assumptions_are_documented():
    """The per-day reading is an ASSUMPTION, and the code says so.

    Q-04 is OPEN: whether *-requests really describes a day has never been observed.
    If this assertion fails, the label was dropped and the assumption became silent.
    """
    import inspect
    from relay.standin import server as mod

    src = inspect.getsource(mod.StandIn._headers)
    assert "UNVERIFIED" in src, "the bucket-model assumption lost its label"
    assert "Q-04" in src, "the open question reference was dropped"
