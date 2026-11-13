"""Optional LLM self-check: ask the small model whether each citation is supported.

**It can only downgrade.** A code-verified answer that the self-check rejects becomes
`PassagesOnly`; a code-rejected answer is never promoted by the self-check, and a
self-check that errors is treated as "no opinion", not as approval. This asymmetry is
the whole safety argument: an optional component that can approve is an optional
component that can bypass verification, and H1 ("nothing unverified is sent") would
then depend on a model call that is not always made.

**Off by default** (`pipeline.llm_verify.enabled: false`). Two reasons, both about
honesty rather than modesty:

  * it costs an extra model call per answer, and no measurement here has established
    that it catches anything the code checks miss;
  * the code checks are cheap, deterministic and testable. Adding a probabilistic
    check in front of a deterministic one, by default, makes the failure mode of the
    whole system probabilistic.

Cost is reported with it ON and OFF on the stand-in; the real cost is **unmeasured**
because no real call was made.

Run:
    python -m pytest -q tests/test_selfcheck.py      -> 10 passed
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: The question asked per citation. Deliberately closed-form: a free-text "is this
#: supported?" invites a paragraph, which is impossible to parse reliably and costs
#: tokens to read. A single token answer is the cheapest thing that can be checked.
CHECK_PROMPT = (
    "Answer with exactly one word, SUPPORTED or UNSUPPORTED.\n"
    "CLAIM: {claim}\n"
    "QUOTE: {quote}\n"
)


@dataclass
class SelfCheckConfig:
    enabled: bool = False
    #: Below these remaining-budget fractions the check is SKIPPED, not failed. An
    #: optional cost must be the first thing dropped when the budget is short.
    min_tpm_remaining_frac: Optional[float] = None
    min_tpd_remaining_frac: Optional[float] = None

    @classmethod
    def from_config(cls, cfg) -> "SelfCheckConfig":
        node = cfg.get("pipeline.llm_verify", None) or {}
        if not isinstance(node, dict):
            # A boolean shorthand (`llm_verify: true`) is accepted so an operator
            # cannot accidentally leave the feature half-configured.
            return cls(enabled=bool(node))
        return cls(
            enabled=bool(node.get("enabled", False)),
            min_tpm_remaining_frac=node.get("min_tpm_remaining_frac"),
            min_tpd_remaining_frac=node.get("min_tpd_remaining_frac"),
        )

    def should_run(self, tpm_remaining_frac: Optional[float] = None,
                   tpd_remaining_frac: Optional[float] = None) -> bool:
        """Whether the check runs at all for this request."""
        if not self.enabled:
            return False
        # UNMEASURED thresholds: when null, there is no budget rule, so the check
        # runs. Skipping on an invented fraction would silently disable a feature
        # nobody had configured to be disabled.
        if (self.min_tpm_remaining_frac is not None
                and tpm_remaining_frac is not None
                and tpm_remaining_frac < self.min_tpm_remaining_frac):
            return False
        if (self.min_tpd_remaining_frac is not None
                and tpd_remaining_frac is not None
                and tpd_remaining_frac < self.min_tpd_remaining_frac):
            return False
        return True


def verdict_from(text: str) -> Optional[bool]:
    """Parse a one-word answer. None = no usable opinion.

    Deliberately strict: only an unambiguous SUPPORTED/UNSUPPORTED counts. A model
    that answers "yes, mostly" has not given a verdict, and guessing one would let
    silence act as approval.
    """
    if not text:
        return None
    word = text.strip().strip(".").upper()
    if word == "SUPPORTED":
        return True
    if word == "UNSUPPORTED":
        return False
    # tolerate a leading/trailing marker but not a mixed answer
    tokens = [t.strip(".,!:;\"'") for t in word.split()]
    if tokens.count("UNSUPPORTED") == 1 and "SUPPORTED" not in tokens:
        return False
    if tokens == ["SUPPORTED"]:
        return True
    return None


@dataclass
class SelfCheckResult:
    #: True only when every citation was explicitly endorsed.
    passed: bool
    #: Citations the model called UNSUPPORTED. Empty when it passed.
    rejected: tuple[str, ...] = ()
    #: Citations with no usable answer. These do NOT count as endorsements.
    unclear: tuple[str, ...] = ()
    #: Set when the check ran but could not be trusted (error, timeout, budget).
    skipped_reason: str = ""
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def ran(self) -> bool:
        return not self.skipped_reason


def combine(code_ok: bool, check: SelfCheckResult) -> bool:
    """THE combination rule, in one place: the self-check may only subtract.

    A caller that wrote `code_ok or check.passed` would let the optional check
    override the deterministic one -- exactly the bypass this module exists to
    prevent.
    """
    if not code_ok:
        return False                      # never promoted
    if not check.ran:
        return True                       # no opinion: code stands
    if not check.passed:
        return False                      # downgraded
    return True
