"""Item H: the instruction prefix must stay byte-stable and come FIRST.

Run: /tmp/auditenv/bin/python -m pytest -q tests/test_prompt_prefix.py

Two separate properties, both about the prefix the provider caches on:

1. ORDER. The instructions are the prefix and the passages are the suffix. If they
   ever swap, the prefix changes on every request and caching is worth nothing.
2. STABILITY. The prefix must be byte-identical across requests. Any timestamp,
   request id, level, model name or retry counter interpolated into it destroys the
   cache and the only symptom is a bill.
"""
import re
from relay.pipeline.pipeline import DRAFT_PROMPT, format_passages


def _prefix_of(prompt: str) -> str:
    """Everything before the passages -- the part a prefix cache can keep."""
    return prompt.split("Passages:")[0]


def test_instructions_come_before_passages():
    out = DRAFT_PROMPT.format(passages="[c1] text", question="q?")
    assert out.index("Answer the question") < out.index("Passages:")
    assert out.index("Passages:") < out.index("Question:")


def test_prefix_is_byte_identical_across_requests():
    # Different passages and questions must not perturb the prefix.
    a = _prefix_of(DRAFT_PROMPT.format(passages="[c1] alpha", question="what is alpha?"))
    b = _prefix_of(DRAFT_PROMPT.format(passages="[c9] omega", question="what is omega?"))
    assert a == b


def test_prefix_carries_no_per_request_values():
    prefix = _prefix_of(DRAFT_PROMPT.format(passages="x", question="y"))
    # Anything that varies per request and would silently break the cache.
    for pattern, name in [
        (r"\{", "an unformatted placeholder"),
        (r"req[-_]", "a request id"),
        (r"\bL[0-3]\b", "a ladder level"),
        (r"\b20\d\d-\d\d-\d\d\b", "a date"),
        (r"\d+\.\d+\s*s\b", "a latency"),
    ]:
        assert not re.search(pattern, prefix), f"prefix contains {name}: {prefix!r}"


def test_prefix_is_identical_for_every_ladder_level():
    # The level changes routing, not instructions. If the level leaks into the
    # prefix, every degradation invalidates the cache for no benefit.
    prefix = _prefix_of(DRAFT_PROMPT.format(passages="x", question="y"))
    for lvl in ("L0", "L1", "L2", "L3"):
        assert lvl not in prefix


def test_passages_are_labelled_by_chunk_id():
    class _C:
        def __init__(self, i, t):
            self.chunk_id, self.text = i, t
    class _H:
        def __init__(self, i, t):
            self.chunk = _C(i, t)

    out = format_passages([_H("c1", "alpha"), _H("c2", "beta")])
    assert out == "[c1] alpha\n\n[c2] beta"
