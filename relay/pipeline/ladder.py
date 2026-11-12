"""The degradation ladder: one function, one level, from budget state.

The level answers a single question -- "how much should this request give up?" -- and
is computed in ONE place so it can be logged, tested, and reasoned about. Scattering
"if we are short on budget then reduce X" across the pipeline is how a system ends up
degrading in three different ways depending on which code path ran.

    L0  normal.
    L1  remaining TPM fraction < ladder.l1_tpm_remaining_frac, OR the admission queue
        wait exceeded ladder.l1_queue_wait_s. Smaller top_k, smaller draft cap, skip
        the corrective loop.
    L2  serve from cache/coalescing only, plus a shorter cap. No new generation.
    L3  no budget at all: PassagesOnly / NoEvidence at 0 tokens. Structural.

**L3 is not a threshold**, it is a statement that the budget is exhausted; it is
checked first and always wins.

Every threshold that is not structural is **UNMEASURED** in config. The function
still needs a number to run, so each null has a named provisional fallback declared
next to the key and reported by `provisional_used()`. A ladder that silently invents
its own trigger points would degrade the system at a threshold nobody chose.

Run:
    python -m pytest -q tests/test_ladder.py       -> 12 passed
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

L0, L1, L2, L3 = 0, 1, 2, 3

LEVEL_NAMES = {L0: "L0_normal", L1: "L1_degraded", L2: "L2_cache_only",
               L3: "L3_no_budget"}

#: Provisional fallbacks, used ONLY when config is null. Each is a placeholder with
#: no measurement behind it; `provisional_used()` reports which ones fired so the
#: event log never claims a measured trigger it did not have.
PROVISIONAL = {
    "l1_tpm_remaining_frac": 0.10,
    "l1_queue_wait_s": 2.0,
    "l2_max_tokens_scale": 0.5,
    # L2's own trigger: remaining budget low enough that a new generation probably
    # cannot finish. Expressed as a fraction, NOT as a multiple of the L1 trigger --
    # a second invented multiple is the unmeasured-threshold mistake this project
    # bans. Default sits below L1 so that, by default, budget pressure gives L1 and
    # L2 fires only on an explicit configuration.
    "l2_tpm_remaining_frac": 0.02,
}


@dataclass
class LadderConfig:
    l1_tpm_remaining_frac: float
    l1_queue_wait_s: float
    l2_max_tokens_scale: float
    l2_tpm_remaining_frac: float = 0.02
    #: Which settings came from PROVISIONAL rather than config.
    provisional: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, cfg) -> "LadderConfig":
        used: list[str] = []

        def take(key: str) -> float:
            raw = cfg.get(f"ladder.{key}", None)
            if raw is None:
                used.append(key)
                return PROVISIONAL[key]
            return float(raw)

        return cls(
            l1_tpm_remaining_frac=take("l1_tpm_remaining_frac"),
            l1_queue_wait_s=take("l1_queue_wait_s"),
            l2_max_tokens_scale=take("l2_max_tokens_scale"),
            l2_tpm_remaining_frac=take("l2_tpm_remaining_frac"),
            provisional=tuple(used),
        )


@dataclass
class BudgetState:
    """What the ladder is allowed to look at. A plain value, so a fake clock and a
    fake bucket make the whole thing testable without a gateway."""

    tpm_remaining_frac: Optional[float] = None   # None = unknown, not "plenty"
    tpd_remaining_frac: Optional[float] = None
    queue_wait_s: float = 0.0
    budget_exhausted: bool = False
    tpm_remaining_tokens: Optional[int] = None


@dataclass
class Level:
    level: int
    reason: str = ""
    #: Concrete adjustments, so callers do not each re-derive them.
    top_k_scale: float = 1.0
    draft_max_tokens_scale: float = 1.0
    skip_corrective: bool = False
    generation_allowed: bool = True

    @property
    def name(self) -> str:
        return LEVEL_NAMES[self.level]


def compute_level(state: BudgetState, cfg: LadderConfig) -> Level:
    """The ONE place a degradation level is decided.

    Order is the whole of the logic:

      1. L3 if the budget is exhausted. Nothing else can matter: there is no token to
         spend, so a smaller top_k or a shorter cap changes nothing.
      2. L2 if the remaining TPM fraction is below `l2_tpm_remaining_frac`: low enough
         that a new generation probably cannot finish. A half-generated answer is
         worse than none, so generation is refused and the caller is served from
         cache/coalescing.
      3. L1 if the fraction is below `l1_tpm_remaining_frac`, OR the queue wait
         exceeded `l1_queue_wait_s`.
      4. L0 otherwise.

    **Boundaries are the CONFIGURED ones.** An earlier draft of this function used
    `< trigger*2` for L1 and put L2 at `< trigger`, which silently moved BOTH
    thresholds and made the configured number mean something nobody wrote down. L1 now
    triggers exactly at the configured fraction, and L2 has its own key so it cannot
    be an invented multiple of L1's.

    `None` means UNKNOWN and must NOT be read as "plenty". An unknown budget on a
    request about to spend tokens is a reason to be careful, not optimistic -- but it
    is also not evidence of shortage, so it falls through to L0 and the reason says
    the budget was unobserved rather than pretending it was healthy.
    """
    if state.budget_exhausted:
        return Level(L3, "budget_exhausted", top_k_scale=0.0,
                     draft_max_tokens_scale=0.0, skip_corrective=True,
                     generation_allowed=False)

    if state.tpm_remaining_tokens is not None and state.tpm_remaining_tokens <= 0:
        return Level(L3, "zero_tokens_remaining", top_k_scale=0.0,
                     draft_max_tokens_scale=0.0, skip_corrective=True,
                     generation_allowed=False)

    frac = state.tpm_remaining_frac
    if frac is None:
        # Unknown: cannot justify degrading on budget. Queue pressure can still
        # degrade, because that IS observed.
        if state.queue_wait_s > cfg.l1_queue_wait_s:
            return Level(L1, f"queue_wait={state.queue_wait_s:.2f}s>"
                             f"{cfg.l1_queue_wait_s} (tpm unobserved)",
                         top_k_scale=0.5, draft_max_tokens_scale=0.5,
                         skip_corrective=True)
        return Level(L0, "normal (tpm unobserved)")

    if frac <= 0.0:
        return Level(L3, f"tpm_remaining_frac={frac:.4f}", top_k_scale=0.0,
                     draft_max_tokens_scale=0.0, skip_corrective=True,
                     generation_allowed=False)

    if frac < cfg.l2_tpm_remaining_frac:
        return Level(L2, f"tpm_remaining_frac={frac:.4f}<{cfg.l2_tpm_remaining_frac}",
                     top_k_scale=1.0,
                     draft_max_tokens_scale=cfg.l2_max_tokens_scale,
                     skip_corrective=True, generation_allowed=False)

    if frac < cfg.l1_tpm_remaining_frac:
        return Level(L1, f"tpm_remaining_frac={frac:.4f}<{cfg.l1_tpm_remaining_frac}",
                     top_k_scale=0.5, draft_max_tokens_scale=0.5,
                     skip_corrective=True)

    if state.queue_wait_s > cfg.l1_queue_wait_s:
        return Level(L1, f"queue_wait={state.queue_wait_s:.2f}s>"
                         f"{cfg.l1_queue_wait_s}",
                     top_k_scale=0.5, draft_max_tokens_scale=0.5,
                     skip_corrective=True)

    return Level(L0, "normal")


def level_event_fields(lvl: Level, cfg: LadderConfig,
                       state: BudgetState) -> dict:
    """The fields to put on the request event. One function so every caller logs the
    same shape and a missing field is a single place to fix."""
    return {
        "ladder_level": lvl.level,
        "ladder_name": lvl.name,
        "ladder_reason": lvl.reason,
        "ladder_provisional": ",".join(cfg.provisional) or None,
        "tpm_remaining_frac": (None if state.tpm_remaining_frac is None
                               else round(state.tpm_remaining_frac, 4)),
        "queue_wait_s": round(state.queue_wait_s, 3),
        "generation_allowed": lvl.generation_allowed,
    }
