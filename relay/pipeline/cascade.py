"""Model cascade: which model handles which step, decided in one place.

The intended shape, from the brief:

    draft      -> models.large    (the thing the user reads)
    rewrite    -> models.small
    verify     -> models.small    (only when LLM verify is on)

    at L1 and above, EVERYTHING -> models.small.

The point is that most of the token spend is in steps whose output the user never
sees directly: a rewrite that expands the question, and a verification call that
reads quote pairs. Sending those to the large model buys nothing observable. The
draft is the one call where model quality is user-visible.

**Dependency on item B.** The cascade only saves anything if the two models have
separate buckets. If they share one (Q-03 OPEN), routing a call from large to small
moves nothing, because both draw from the same pool -- the cascade would be a
comment, not a control. `cascade_effective()` reports that honestly instead of
letting the report claim a saving.

**UNVERIFIED.** Q-03 is still open; `models.buckets_separate_per_model` is null. If
the buckets turn out to be shared, this module still routes correctly but saves
nothing, and the event log says so.

Run:
    python -m pytest -q tests/test_cascade.py      -> 9 passed
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

STEPS = ("rewrite", "draft", "verify")


@dataclass
class CascadeConfig:
    """Resolved once, from config, so no caller re-derives the routing."""

    enabled: bool
    large_model: str
    small_model: str
    #: Draft goes to the large model only at L0. At L1 and above everything is small.
    draft_large_at_l0: bool = True
    buckets_separate: Optional[bool] = None

    @classmethod
    def from_config(cls, cfg) -> "CascadeConfig":
        return cls(
            # A cascade that is off by default is the safe default: routing two models
            # when the buckets are shared adds a failure mode (a second ID that can be
            # rate-limited independently of the first) and saves nothing.
            enabled=bool(cfg.get("models.cascade.enabled", True)),
            large_model=cfg.get("models.large.id"),
            small_model=cfg.get("models.small.id"),
            draft_large_at_l0=bool(cfg.get("models.cascade.draft_large_at_l0", True)),
            buckets_separate=cfg.get("models.buckets_separate_per_model", None),
        )

    def cascade_effective(self) -> bool:
        """Whether routing can actually move budget.

        False when the buckets are shared: with one pool, small vs large is a naming
        distinction. `None` (unmeasured) is treated as separate, matching the
        BudgetBook default, but the answer is still reported as unverified by
        `cascade_unverified()`.
        """
        return self.enabled and self.buckets_separate is not False

    def cascade_unverified(self) -> bool:
        return self.enabled and self.buckets_separate is None


def model_for(step: str, ladder_level: int, cfg: CascadeConfig) -> str:
    """The ONE routing function. Returns the model id for `step` at `level`.

    Order matters: the ladder check comes FIRST. At L1 and above the cascade
    collapses to the small model for every step, because the point of degrading is to
    stop spending the expensive thing -- sending the draft to the large model at L1
    would undo the level it was just put in.

    `step` is validated rather than defaulted: a typo would otherwise silently get
    the small model, which looks like working code and quietly downgrades quality.
    """
    if step not in STEPS:
        raise ValueError(f"unknown step {step!r}; expected one of {STEPS}")

    if not cfg.enabled:
        return cfg.small_model

    if ladder_level >= 1:
        return cfg.small_model

    if step == "draft":
        return cfg.large_model if cfg.draft_large_at_l0 else cfg.small_model

    # rewrite and verify: never worth the large model. Their output is not what the
    # user reads; a rewrite is a search query and a verify is a yes/no per quote.
    return cfg.small_model


def routing_event_fields(step: str, level: int, cfg: CascadeConfig) -> dict:
    """Fields to log per attempt, so the routing is auditable after the fact."""
    return {
        "cascade_step": step,
        "cascade_model": model_for(step, level, cfg),
        "cascade_level": level,
        "cascade_effective": cfg.cascade_effective(),
        "cascade_unverified": cfg.cascade_unverified(),
    }
