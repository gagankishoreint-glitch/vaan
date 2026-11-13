"""Item F: model cascade, decided in one function and logged per attempt.

Shape: draft -> large at L0; rewrite and verify -> small always; at L1 and above
EVERYTHING -> small.

The subtle bit is the ORDER: the ladder check comes first. Sending the draft to the
large model at L1 would undo the level that was just chosen, which is why a
"cascade" that only looks at the step is wrong even though it passes a per-step test.

**Dependency on item B is asserted, not assumed.** If the two models share a bucket,
the cascade routes correctly and saves nothing. `cascade_effective()` reports that,
and the log carries it, so the report cannot claim a saving that did not happen.

Run: python -m pytest -q tests/test_cascade.py  -> 9 passed
"""
from __future__ import annotations

import pytest

from relay.pipeline.cascade import (
    CascadeConfig, model_for, routing_event_fields,
)

SMALL, LARGE = "openai/gpt-oss-20b", "openai/gpt-oss-120b"


def _cfg(**kw) -> CascadeConfig:
    base = dict(enabled=True, large_model=LARGE, small_model=SMALL,
                draft_large_at_l0=True, buckets_separate=True)
    base.update(kw)
    return CascadeConfig(**base)


def test_draft_goes_to_large_at_l0():
    assert model_for("draft", 0, _cfg()) == LARGE


def test_rewrite_and_verify_go_to_small_at_l0():
    """Their output is not what the user reads; the large model buys nothing."""
    cfg = _cfg()
    assert model_for("rewrite", 0, cfg) == SMALL
    assert model_for("verify", 0, cfg) == SMALL


def test_everything_goes_to_small_at_l1_and_above():
    """The ladder must win over the per-step routing, not sit beside it."""
    cfg = _cfg()
    for level in (1, 2, 3):
        for step in ("rewrite", "draft", "verify"):
            assert model_for(step, level, cfg) == SMALL, (step, level)


def test_draft_large_at_l0_can_be_disabled():
    assert model_for("draft", 0, _cfg(draft_large_at_l0=False)) == SMALL


def test_unknown_step_raises_rather_than_defaulting():
    """A typo must not silently get the small model and look like working code."""
    with pytest.raises(ValueError, match="unknown step"):
        model_for("drafft", 0, _cfg())


def test_disabled_cascade_uses_small_for_everything():
    cfg = _cfg(enabled=False)
    for step in ("rewrite", "draft", "verify"):
        assert model_for(step, 0, cfg) == SMALL


def test_cascade_effective_is_false_when_buckets_are_shared():
    """Q-03: with one shared pool, small vs large saves nothing."""
    assert _cfg(buckets_separate=True).cascade_effective() is True
    assert _cfg(buckets_separate=False).cascade_effective() is False
    # unmeasured is treated as separate (matching BudgetBook) but flagged
    unverified = _cfg(buckets_separate=None)
    assert unverified.cascade_effective() is True
    assert unverified.cascade_unverified() is True


def test_routing_is_logged_per_attempt_with_the_saving_claim():
    cfg = _cfg(buckets_separate=False)
    f = routing_event_fields("draft", 0, cfg)
    assert f["cascade_model"] == LARGE
    assert f["cascade_effective"] is False, (
        "the log must record that routing saves nothing when the buckets are "
        "shared, or the report will claim a saving that did not happen")


def test_config_shapes_resolve_from_a_Config_like_object():
    class Cfg:
        vals = {"models.cascade.enabled": True,
                "models.large.id": LARGE,
                "models.small.id": SMALL,
                "models.cascade.draft_large_at_l0": True,
                "models.buckets_separate_per_model": None}

        def get(self, k, d=None):
            return self.vals.get(k, d)

    cfg = CascadeConfig.from_config(Cfg())
    assert cfg.large_model == LARGE and cfg.small_model == SMALL
    assert cfg.cascade_unverified() is True, (
        "buckets_separate_per_model is null, so the cascade's benefit is UNVERIFIED "
        "and must report as such")
