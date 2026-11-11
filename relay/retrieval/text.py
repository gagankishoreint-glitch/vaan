"""Text normalisation shared by retrieval and verification.

The single most important rule here: **the same function must normalise a chunk and
a quote**, otherwise a correct answer fails the citation check for a reason nobody
can debug later (NFKC ligatures, hyphenation across line breaks, unicode dashes).

Kept in its own module so retrieval, verify, and the eval grader cannot drift apart.
"""
from __future__ import annotations

import re
import unicodedata

#: Unicode dashes that PDF extraction produces instead of ASCII hyphen.
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"), "-")
#: Ligatures and typographic quotes.
_EXTRA = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u00a0": " ", "\u2009": " ", "\u202f": " ",
}
_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*(\w)")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """NFKC + de-hyphenate + collapse whitespace. Idempotent."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.translate(_DASHES)
    for bad, good in _EXTRA.items():
        t = t.replace(bad, good)
    t = _HYPHEN_BREAK.sub(r"\1\2", t)      # "transfor-\nmation" -> "transformation"
    t = _WS.sub(" ", t)
    return t.strip()


def tokenize(text: str) -> list[str]:
    """Lower-case word tokens. Used by BM25 and by the quote matcher."""
    return re.findall(r"[a-z0-9]+", normalize(text).lower())


def contains_quote(chunk_text: str, quote: str) -> bool:
    """Is `quote` a verbatim substring of `chunk_text`, after normalisation?

    Normalising BOTH sides is the point: the PDF may hold 'transfor-\nmation' and
    the model may quote 'transformation'.
    """
    q = normalize(quote)
    return bool(q) and q in normalize(chunk_text)
