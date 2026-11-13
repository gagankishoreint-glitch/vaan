"""P6: verification. The ONLY place mint_verified() may be called.

A test greps the codebase to enforce that (tests/test_lint_rules.py), because
Python cannot make it airtight.

Order (PRD s4): code checks first -- chunk ids exist, quotes are verbatim --
and only then an optional LLM groundedness check, and only if budget allows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from relay.contracts import Citation, VerifiedAnswer, mint_verified
from relay.retrieval.text import contains_quote


@dataclass
class CheckResult:
    ok: bool
    reason: str
    citations: tuple[Citation, ...] = ()

    def __bool__(self) -> bool:
        return self.ok


_NUM = re.compile(r"\d+(?:\.\d+)?")


def check_citations(text: str, citations: list[Citation],
                    chunks_by_id: dict) -> CheckResult:
    """Every chunk id must exist and every quote must be a verbatim substring.

    Both sides are normalised through the same function retrieval uses
    (`relay.retrieval.text.normalize`), so NFKC ligatures and hyphens carried
    across a line break cannot make a correct quote fail.
    """
    if not citations:
        return CheckResult(False, "verify_failed")
    for c in citations:
        chunk = chunks_by_id.get(c.chunk_id)
        if chunk is None:
            return CheckResult(False, f"unknown chunk_id {c.chunk_id}")
        if not contains_quote(chunk.text, c.quote):
            return CheckResult(False, f"quote not verbatim in {c.chunk_id}")
    if not text.strip():
        return CheckResult(False, "empty answer text")
    return CheckResult(True, "ok", tuple(citations))


def numbers_in(text: str) -> set[str]:
    return set(_NUM.findall(text))


def check_numbers_present(text: str, cited_texts: list[str]) -> CheckResult:
    """Any number in the answer must appear in at least one cited chunk.

    Catches the classic failure: the model quotes correctly but puts a number in
    the prose that no source contains.
    """
    src = " ".join(cited_texts)
    allowed = numbers_in(src)
    for n in numbers_in(text):
        if n not in allowed:
            return CheckResult(False, f"number {n!r} not present in any cited chunk")
    return CheckResult(True, "ok")


def mint(text: str, citations: tuple[Citation, ...]) -> VerifiedAnswer:
    """The single construction site of VerifiedAnswer."""
    return mint_verified(text, citations)
