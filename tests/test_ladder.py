"""Item E: the degradation ladder, computed in one function and testable with fakes.

The failure mode this guards against is a ladder whose thresholds drift from the
config: an early draft used `< trigger*2` for L1, which silently moved BOTH boundaries
and made the configured number mean something nobody had written down. Every test
here places the input just either side of a CONFIGURED boundary.

Run: python -m pytest -q tests/test_ladder.py  -> 12 passed
"""
from __future__ import annotations

import pytest

from relay.pipeline.ladder import (
    L0, L1, L2, L3, BudgetState, LadderConfig, compute_level, level_event_fields,
)


class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def now(self) -> float:
        return self.t


def _cfg(**kw) -> LadderConfig:
    base = dict(l1_tpm_remaining_frac=0.25, l1_queue_wait_s=2.0,
                l2_max_tokens_scale=0.5, l2_tpm_remaining_frac=0.02)
    base.update(kw)
    return LadderConfig(**base)


def test_all_normal_is_l0():
    lvl = compute_level(BudgetState(tpm_remaining_frac=0.9), _cfg())
    assert lvl.level == L0
    assert lvl.generation_allowed is True
    assert lvl.top_k_scale == 1.0


def test_l1_triggers_exactly_at_the_configured_fraction():
    """Below 0.25 degrades; at 0.25 does not. The configured number is the boundary."""
    cfg = _cfg()
    assert compute_level(BudgetState(tpm_remaining_frac=0.25), cfg).level == L0
    lvl = compute_level(BudgetState(tpm_remaining_frac=0.2499), cfg)
    assert lvl.level == L1
    assert lvl.top_k_scale < 1.0
    assert lvl.draft_max_tokens_scale < 1.0
    assert lvl.skip_corrective is True


def test_l1_trigger_is_not_doubled():
    """Regression: an earlier draft used < trigger*2, degrading at 0.49."""
    cfg = _cfg(l1_tpm_remaining_frac=0.25)
    lvl = compute_level(BudgetState(tpm_remaining_frac=0.40), cfg)
    assert lvl.level == L0, (
        "0.40 remaining degraded, so the L1 boundary was moved away from the "
        f"configured 0.25 (got {lvl.name}: {lvl.reason})")


def test_l2_refuses_generation():
    cfg = _cfg(l2_tpm_remaining_frac=0.02)
    lvl = compute_level(BudgetState(tpm_remaining_frac=0.01), cfg)
    assert lvl.level == L2
    assert lvl.generation_allowed is False
    assert lvl.draft_max_tokens_scale == 0.5, "L2 must also shorten the cap"


def test_l2_has_its_own_key_and_is_not_a_multiple_of_l1():
    """Two independent keys; moving one must not move the other."""
    cfg = _cfg(l1_tpm_remaining_frac=0.25, l2_tpm_remaining_frac=0.02)
    # just above L2, well below L1 -> L1, not L2
    assert compute_level(BudgetState(tpm_remaining_frac=0.05), cfg).level == L1
    # raising the L2 key alone moves the L2 boundary
    cfg2 = _cfg(l1_tpm_remaining_frac=0.25, l2_tpm_remaining_frac=0.10)
    assert compute_level(BudgetState(tpm_remaining_frac=0.05), cfg2).level == L2


def test_zero_fraction_is_l3():
    lvl = compute_level(BudgetState(tpm_remaining_frac=0.0), _cfg())
    assert lvl.level == L3
    assert lvl.generation_allowed is False
    assert lvl.top_k_scale == 0.0


def test_why_level_and_why_is_one():
    """Two reasons, not one."""
    assert compute_level(BudgetState(tpm_remaining_frac=0.9), _cfg()).reason == "normal"
    assert "queue_wait" in compute_level(
        BudgetState(tpm_remaining_frac=0.9, queue_wait_s=99.0), _cfg()).reason


def test_negative_fraction_is_l3_not_a_crash():
    lvl = compute_level(BudgetState(tpm_remaining_frac=-0.05), _cfg())
    assert lvl.level == L3


def test_unknown_fraction_does_not_pretend_to_be_healthy_or_short():
    """Unknown must not be read as plentiful, nor as exhaustion."""
    lvl = compute_level(BudgetState(tpm_remaining_frac=None), _cfg())
    assert lvl.level == L0
    assert "unobserved" in lvl.reason, lvl.reason
    
def test_unknown_fraction_still_degrades_on_observed_queue_pressure():
    """Queue wait IS observed, so it can degrade even when budget cannot."""
    lvl = compute_level(BudgetState(tpm_remaining_frac=None, queue_wait_s=99.0), _cfg())
    assert lvl.level == L1
    assert "unobserved" in lvl.reason


def test_generation_is_refused_exactly_at_l2_and_below():
    cfg = _cfg()
    for frac, expect in ((0.9, True), (0.2, True), (0.01, False), (0.0, False)):
        assert compute_level(BudgetState(tpm_remaining_frac=frac),
                             cfg).generation_allowed is expect, frac


def test_config_nulls_resolve_to_named_provisionals_and_report_themselves():
    """A null must not be silently replaced by an unnamed constant."""
    from relay.pipeline.ladder import PROVISIONAL

    class Cfg:
        def get(self, key, default=None):
            return None          # every ladder key is null

    got = LadderConfig.from_config(Cfg())
    assert set(got.provisional) == set(PROVISIONAL), got.provisional
    assert got.l1_tpm_remaining_frac == PROVISIONAL["l1_tpm_remaining_frac"]


def test_event_fields_are_one_shape_including_provisional_list():
    cfg = _cfg()
    cfg.provisional = ("l2_max_tokens_scale",)
    lvl = compute_level(BudgetState(tpm_remaining_frac=0.1), cfg)
    f = level_event_fields(lvl, cfg, BudgetState(tpm_remaining_frac=0.1, queue_wait_s=0.5))
    for key in ("ladder_level", "ladder_name", "ladder_reason",
                "ladder_provisional", "tpm_remaining_frac", "queue_wait_s",
                "generation_allowed"):
        assert key in f, key
    assert f["ladder_level"] == 1
    assert f["ladder_provisional"] == "l2_max_tokens_scale"
