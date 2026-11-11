import pytest

from relay.ratelimit_headers import parse_duration, parse_rl_headers


@pytest.mark.parametrize("raw,exp", [
    ("7.66s", 7.66), ("2m59.56s", 179.56), ("150ms", 0.15),
    ("1h2m3s", 3723.0), ("2", 2.0), ("0s", 0.0), ("1d", 86400.0),
    (" 5S ", 5.0),
])
def test_ok(raw, exp):
    assert parse_duration(raw) == pytest.approx(exp)


@pytest.mark.parametrize("raw", [None, "", "abc", "5x", "m5", "1h-2m"])
def test_bad(raw):
    assert parse_duration(raw) is None


def test_headers_semantics():
    h = {"retry-after": "2", "x-ratelimit-remaining-tokens": "17997",
         "x-ratelimit-reset-tokens": "7.66s", "x-ratelimit-remaining-requests": "14370",
         "x-ratelimit-reset-requests": "2m59.56s"}
    p = parse_rl_headers(h)
    assert p["remaining_tpm"] == 17997 and p["remaining_rpd"] == 14370
    assert p["reset_tpm_s"] == pytest.approx(7.66)
    assert p["retry_after_s"] == 2.0
    assert p["raw"]["x-ratelimit-reset-requests"] == "2m59.56s"


# ------------------------------------------------------------------ P0 additions

def test_headers_case_insensitive_mapping():
    """http headers are case-insensitive; a real response may use any casing."""
    h = {"X-RateLimit-Remaining-Tokens": "123", "Retry-After": "3"}
    p = parse_rl_headers(h)
    assert p["remaining_tpm"] == 123
    assert p["retry_after_s"] == pytest.approx(3.0)


def test_headers_accept_list_of_tuples():
    """httpx.Headers.items() yields pairs; this is the shape the gateway will pass."""
    p = parse_rl_headers([("x-ratelimit-remaining-tokens", "5"),
                          ("x-ratelimit-limit-tokens", "8000")])
    assert p["remaining_tpm"] == 5
    assert p["limit_tpm"] == 8000


def test_missing_headers_are_none_not_zero():
    """Absent must not look like 'budget exhausted'."""
    p = parse_rl_headers({})
    assert p["remaining_tpm"] is None
    assert p["remaining_rpd"] is None
    assert p["retry_after_s"] is None
    assert p["raw"] == {}


def test_unparseable_kept_raw():
    """A 429 we cannot parse must stay visible verbatim for the probe."""
    p = parse_rl_headers({"retry-after": "soon", "x-ratelimit-reset-tokens": "7.66 s"})
    assert p["retry_after_s"] is None
    assert p["reset_tpm_s"] is None
    assert p["raw"]["retry-after"] == "soon"
    assert p["raw"]["x-ratelimit-reset-tokens"] == "7.66 s"


def test_duplicate_key_first_wins_and_does_not_raise():
    """Duplicate headers are a stand-in risk; deterministic, no exception."""
    p = parse_rl_headers([("x-ratelimit-remaining-tokens", "10"),
                          ("x-ratelimit-remaining-tokens", "20")])
    assert p["remaining_tpm"] == 10
