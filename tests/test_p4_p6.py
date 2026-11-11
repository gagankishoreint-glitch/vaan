"""One failure-path test per new mechanism. No more than that (compressed mode)."""
from __future__ import annotations

import pytest

from relay.contracts import Citation, NoEvidence, PassagesOnly, VerifiedAnswer, mint_verified
from relay.gateway.gateway import Budget, Breaker
from relay.pipeline.pipeline import send_reply
from relay.pipeline.verify import check_citations, check_numbers_present
from relay.retrieval.text import contains_quote, normalize


# ---------------------------------------------------------------- H1 exit gate

def test_send_reply_rejects_a_bare_string():
    with pytest.raises(TypeError, match="H1 violation"):
        send_reply("here is my answer")   # type: ignore[arg-type]


def test_send_reply_accepts_all_three():
    for r in (mint_verified("t", ()), NoEvidence("no"), PassagesOnly("p", (), "budget_gone")):
        assert send_reply(r) is r


# ---------------------------------------------------------------- budget

def test_budget_never_goes_negative():
    b = Budget(tpm=100, rpd=10)
    b.take(60, now=1.0)
    with pytest.raises(Exception):
        b.take(60, now=1.0)
    assert b.tpm_used == 60


def test_budget_resets_after_window():
    b = Budget(tpm=100, rpd=10)
    b.take(90, now=1.0)
    b.take(90, now=100.0)      # past the 60s window
    assert b.tpm_used == 90


def test_budget_reconcile_uses_provider_ratio_not_our_limit():
    """BUG-010: reconstructing usage from `remaining` against OUR limit pinned the
    budget to exhausted whenever the two limits differed."""
    b = Budget(tpm=10**9, rpd=10**9)
    b.learn_limits(8000, 1000)
    b.reconcile(remaining_tpm=4000, remaining_rpd=500, now=1.0)
    assert b.tpm_used == 5 * 10**8, b.tpm_used     # half of OUR limit, not 4000


def test_budget_reconcile_without_learned_limits_is_a_noop():
    b = Budget(tpm=8000, rpd=1000)
    b.reconcile(4000, 500, now=1.0)
    assert b.tpm_used == 0


# ---------------------------------------------------------------- breaker

def test_breaker_opens_after_threshold_and_half_opens():
    br = Breaker(fail_threshold=2, open_s=10.0)
    br.record(False, now=0.0)
    assert br.state(0.0) == "closed"
    br.record(False, now=0.0)
    assert br.state(0.0) == "open"
    assert br.state(11.0) == "half-open"


# ---------------------------------------------------------------- verification

def test_unknown_chunk_id_is_rejected():
    r = check_citations("answer", [Citation("nope:s1:c0000", "x")], {})
    assert not r and "unknown chunk_id" in r.reason


def test_non_verbatim_quote_is_rejected():
    from relay.contracts import Chunk
    ch = {"a:s1:c0000": Chunk("a:s1:c0000", "attention", "1", 1, "the cat sat")}
    r = check_citations("answer", [Citation("a:s1:c0000", "the dog sat")], ch)
    assert not r and "not verbatim" in r.reason


def test_number_not_in_sources_is_rejected():
    r = check_numbers_present("it uses 8 heads", ["we use h = 6 heads"])
    assert not r and "8" in r.reason


def test_number_in_sources_passes():
    assert check_numbers_present("it uses 8 heads", ["we use h = 8 heads"])


# ---------------------------------------------------------------- normalisation

def test_hyphenated_line_break_still_matches():
    """A quote spanning a PDF line break must verify (NFKC + de-hyphenation)."""
    assert contains_quote("the transfor-\nmation is good", "the transformation is good")


def test_ligature_normalises():
    assert normalize("\ufb01ne") == "fine"


# ---------------------------------------------------------------- retry loop

def _gateway(policy, cfg=None, handler=None):
    import asyncio, httpx
    from relay.clock import RealClock
    from relay.config import load_config
    from relay.gateway.gateway import Gateway
    cfg = cfg or load_config()
    calls = {"n": 0}

    def _h(request):
        calls["n"] += 1
        return handler(request)

    async def build():
        c = httpx.AsyncClient(transport=httpx.MockTransport(_h),
                              base_url="http://x/openai/v1")
        gw = Gateway.from_config(cfg, RealClock(), None, base_url="http://x/openai/v1",
                                 api_key="k", client=c, policy=policy)
        return c, gw
    return build, calls


class _S:
    req_id = "b"

    def attempt_start(self, a):
        pass

    def attempt_end(self, a):
        pass

    def emit(self, *a, **k):
        pass


def _always_429(retry_after=5):
    import httpx
    return httpx.Response(429, headers={"retry-after": str(retry_after)},
                          json={"error": {"message": "rate limited"}})


def test_naive_is_bounded_and_never_recurses():
    """BUG-013: naive called itself recursively and died with RecursionError
    after 489 requests. It must stop at naive_max_attempts."""
    import asyncio
    from relay.config import load_config
    cfg = load_config()
    build, calls = _gateway("naive", cfg, lambda r: _always_429())

    async def go():
        c, gw = await build()
        with pytest.raises(Exception):
            await gw.call(scope=_S(), step="d", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=3.0)
        await c.aclose()

    asyncio.run(go())
    assert calls["n"] == cfg.get("gateway.naive_max_attempts"), calls["n"]


def test_naive_ignores_retry_after_and_deadline():
    """Naive still retries when retry-after would blow the deadline. That is
    the harm being demonstrated, so a test must pin it rather than fix it."""
    import asyncio
    build, calls = _gateway("naive", None, lambda r: _always_429(retry_after=60))

    async def go():
        c, gw = await build()
        with pytest.raises(Exception):
            await gw.call(scope=_S(), step="d", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=1.0)
        await c.aclose()

    asyncio.run(go())
    assert calls["n"] > 1     # managed would stop at 1


def test_managed_stops_after_one_attempt_when_retry_after_exceeds_deadline():
    import asyncio
    build, calls = _gateway("managed", None, lambda r: _always_429(retry_after=5))

    async def go():
        c, gw = await build()
        with pytest.raises(Exception):
            await gw.call(scope=_S(), step="d", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=3.0)
        await c.aclose()

    asyncio.run(go())
    assert calls["n"] == 1, calls["n"]


def test_never_retry_a_day_limit():
    import asyncio
    build, calls = _gateway("managed", None, lambda r: _always_429(retry_after=3600))

    async def go():
        c, gw = await build()
        with pytest.raises(Exception):
            await gw.call(scope=_S(), step="d", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=30.0)
        await c.aclose()

    asyncio.run(go())
    assert calls["n"] == 1


# ---------------------------------------------------------------- payload

def test_payload_uses_max_completion_tokens_not_max_tokens():
    from relay.gateway.gateway import Gateway
    from relay.config import load_config
    gw = Gateway.from_config(load_config(), None, None, base_url="http://x",
                             api_key="k", client=None)
    b = gw.request_payload(model="openai/gpt-oss-20b", messages=[], max_tokens=400)
    assert "max_completion_tokens" in b
    assert "max_tokens" not in b


def test_reasoning_effort_sent_to_gpt_oss_only():
    from relay.gateway.gateway import Gateway
    from relay.config import load_config
    gw = Gateway.from_config(load_config(), None, None, base_url="http://x",
                             api_key="k", client=None)
    assert gw.request_payload(model="openai/gpt-oss-20b", messages=[],
                              max_tokens=10, reasoning_effort="low")["reasoning_effort"] == "low"
    # a non-reasoning model must not receive the parameter at all
    assert "reasoning_effort" not in gw.request_payload(
        model="llama-3.3-70b", messages=[], max_tokens=10, reasoning_effort="low")


def test_reasoning_effort_none_is_refused():
    from relay.gateway.gateway import Gateway
    from relay.config import load_config
    gw = Gateway.from_config(load_config(), None, None, base_url="http://x",
                             api_key="k", client=None)
    with pytest.raises(ValueError, match="never be"):
        gw.request_payload(model="openai/gpt-oss-20b", messages=[],
                           max_tokens=10, reasoning_effort="none")
