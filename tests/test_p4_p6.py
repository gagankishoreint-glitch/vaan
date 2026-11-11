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
