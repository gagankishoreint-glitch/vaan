import dataclasses

import pytest

from relay.contracts import (
    Attempt,
    Chunk,
    Citation,
    NoEvidence,
    Outcome,
    PassagesOnly,
    Reply,
    Terminal,
    VerifiedAnswer,
    is_reply,
    mint_verified,
)


# ------------------------------------------------------------ the mint gate (H1)

def test_direct_construction_rejected():
    with pytest.raises(TypeError):
        VerifiedAnswer(text="x", citations=())


def test_cannot_forge_with_private_flag_name_typo():
    """Guessing at the escape hatch must not work if someone renames it."""
    with pytest.raises(TypeError):
        VerifiedAnswer(text="x", citations=(), _minted=False)


def test_mint_verified_works():
    c = Citation(chunk_id="attn-v7:s3.2:c04", quote="Scaled Dot-Product Attention")
    v = mint_verified("text", (c,))
    assert isinstance(v, VerifiedAnswer)
    assert v.citations[0].chunk_id == "attn-v7:s3.2:c04"
    assert v._minted is True


def test_verified_answer_is_frozen():
    v = mint_verified("text", ())
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.text = "tampered"          # type: ignore[misc]


def test_citation_is_frozen():
    c = Citation("a", "q")
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.quote = "tampered"         # type: ignore[misc]


def test_chunk_is_frozen():
    c = Chunk("id", "attention", "3.2", 4, "txt")
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.text = "t"                 # type: ignore[misc]


# ------------------------------------------------------------ H1 at the send boundary

@pytest.mark.parametrize("obj,ok", [
    (mint_verified("t", ()), True),
    (NoEvidence("not stated"), True),
    (PassagesOnly("budget gone", (), "budget_gone"), True),
    ("raw string", False),
    ({"text": "dict"}, False),
    (None, False),
    (object(), False),
])
def test_is_reply_is_the_h1_gate(obj, ok):
    assert is_reply(obj) is ok


def test_reply_union_covers_exactly_three():
    import typing

    args = typing.get_args(Reply)
    assert set(args) == {VerifiedAnswer, NoEvidence, PassagesOnly}


# ------------------------------------------------------------ contracts are stable

def test_attempt_defaults_and_enums():
    a = Attempt("a1", "q1", "draft", "groq", "m", t_sent=0.0)
    assert a.t_end is None and a.rl_headers_raw == {}
    assert a.outcome is None
    assert Outcome.RATE_LIMITED_UNKNOWN.value == "rate_limited_unknown"
    assert Terminal.PASSAGES_ONLY.value == "passages_only"


def test_attempt_is_mutable_and_has_no_shared_dict():
    """field(default_factory=dict) -- catching the classic shared-mutable bug."""
    a, b = Attempt("a1", "q", "d", "g", "m", 0.0), Attempt("a2", "q", "d", "g", "m", 0.0)
    a.rl_headers_raw["x"] = "1"
    assert b.rl_headers_raw == {}


def test_no_evidence_nearest_default_empty():
    assert NoEvidence("m").nearest == ()


def test_passages_only_reason_is_free_text_but_documented():
    """Reasons are a fixed vocabulary in docs; the type stays permissive."""
    for r in ("budget_gone", "verify_failed", "breaker_open", "queue_full"):
        assert PassagesOnly("m", (), r).reason == r
