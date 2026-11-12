"""Item G: the optional LLM self-check, and the direction it is allowed to move.

The rule that matters: **it can only downgrade**. An optional component that can
approve would let H1 ("nothing unverified is sent") depend on a model call that is not
always made -- and the whole point of the code checks is that they always are.

Run: python -m pytest -q tests/test_selfcheck.py  -> 10 passed
"""
from __future__ import annotations

import pytest

from relay.pipeline.selfcheck import (
    CHECK_PROMPT, SelfCheckConfig, SelfCheckResult, combine, verdict_from,
)


def test_off_by_default():
    """A feature that costs money per answer must be off unless asked for."""
    assert SelfCheckConfig().enabled is False
    assert SelfCheckConfig().should_run() is False


def test_config_reads_the_enabled_flag():
    class Cfg:
        def get(self, k, d=None):
            # NOTE: returns the VALUE, not {key: value}. An earlier version of this
            # stub returned the wrapped form, so `enabled` read as False and the test
            # failed for a reason that had nothing to do with the code under test.
            return {"enabled": True} if k == "pipeline.llm_verify" else d

    cfg = SelfCheckConfig.from_config(Cfg())
    assert cfg.enabled is True
    assert cfg.should_run() is True


def test_boolean_shorthand_is_accepted():
    """`llm_verify: true` must not silently stay off."""
    class Cfg:
        def get(self, k, d=None):
            return True if k == "pipeline.llm_verify" else d

    assert SelfCheckConfig.from_config(Cfg()).enabled is True


def test_null_budget_thresholds_do_not_skip_the_check():
    """An unmeasured rule must not behave like a configured skip."""
    cfg = SelfCheckConfig(enabled=True)          # both thresholds None
    assert cfg.should_run(tpm_remaining_frac=0.0, tpd_remaining_frac=0.0) is True


def test_configured_budget_threshold_skips_the_check():
    cfg = SelfCheckConfig(enabled=True, min_tpm_remaining_frac=0.2)
    assert cfg.should_run(tpm_remaining_frac=0.1) is False
    assert cfg.should_run(tpm_remaining_frac=0.9) is True


@pytest.mark.parametrize("text,expect", [
    ("SUPPORTED", True),
    ("supported.", True),
    (" UNSUPPORTED ", False),
    ("unsupported!", False),
    ("Yes, mostly", None),
    ("", None),
    ("maybe", None),
])
def test_verdict_parsing_is_strict(text, expect):
    """A model answering "yes, mostly" has not given a verdict."""
    assert verdict_from(text) is expect


def test_selfcheck_can_only_downgrade():
    """THE rule. Every combination, explicitly."""
    failed = SelfCheckResult(passed=False, rejected=("c1",))
    passed = SelfCheckResult(passed=True)
    skipped = SelfCheckResult(passed=True, skipped_reason="budget")

    assert combine(code_ok=True, check=passed) is True
    assert combine(code_ok=True, check=failed) is False       # downgraded
    assert combine(code_ok=True, check=skipped) is True       # no opinion: code stands
    # never promoted
    assert combine(code_ok=False, check=passed) is False
    assert combine(code_ok=False, check=skipped) is False


def test_unclear_citations_are_not_endorsements():
    """`unclear` must not be silently read as support."""
    res = SelfCheckResult(passed=False, unclear=("c1", "c2"))
    assert combine(code_ok=True, check=res) is False, (
        "a citation the model could not judge was treated as supported")


def test_skipped_check_reports_it_ran_nothing():
    res = SelfCheckResult(passed=True, skipped_reason="budget gone")
    assert res.ran is False
    assert combine(code_ok=True, check=res) is True


def test_prompt_asks_for_one_word():
    """A paragraph answer cannot be parsed reliably and costs tokens to read."""
    assert "SUPPORTED" in CHECK_PROMPT and "UNSUPPORTED" in CHECK_PROMPT
    assert "exactly one word" in CHECK_PROMPT
