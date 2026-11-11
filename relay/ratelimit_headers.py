"""Parse Groq rate-limit headers. Raw strings are always kept by the caller.

UNVERIFIED (from memory, to be confirmed in P1 probe -- PRD s13):
  * `x-ratelimit-limit-requests` / `remaining-requests` / `reset-requests` are PER DAY.
  * `x-ratelimit-limit-tokens`   / `remaining-tokens`   / `reset-tokens`   are PER MINUTE.
  * There is no per-minute *request* header.
  * Duration strings look like '7.66s', '2m59.56s', '150ms'; plain integer seconds
    appear in `retry-after`.
Any of these being wrong only affects classification, never safety: an unclassified
429 stays RATE_LIMITED_UNKNOWN with the raw headers attached.
"""
from __future__ import annotations

import re
from typing import Mapping, Optional

_TOKEN = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s|d)")
_FULL = re.compile(r"(?:\d+(?:\.\d+)?(?:ms|h|m|s|d))+")
_UNIT = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}


def parse_duration(raw: Optional[str]) -> Optional[float]:
    """'7.66s'->7.66, '2m59.56s'->179.56, '150ms'->0.15, '1h2m3s'->3723, '2'->2.0.

    Returns None if unparseable (caller keeps the raw string).
    """
    if raw is None:
        return None
    s = raw.strip().lower()
    if not s:
        return None
    try:
        return float(s)                  # plain seconds, e.g. retry-after
    except ValueError:
        pass
    if not _FULL.fullmatch(s):
        return None
    return sum(float(n) * _UNIT[u] for n, u in _TOKEN.findall(s))


def _int(raw: Optional[str]) -> Optional[int]:
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def _items(headers: object) -> list[tuple[str, str]]:
    """Normalise dict / httpx.Headers / list-of-tuples to a lower-cased pair list.

    We do not rely on .get() so this works for a plain dict with mixed case too.
    """
    if hasattr(headers, "items"):
        pairs = list(headers.items())          # type: ignore[union-attr]
    else:
        pairs = list(headers)                  # type: ignore[arg-type]
    return [(str(k).lower(), v) for k, v in pairs]


_KEYS = (
    "retry-after",
    "x-ratelimit-limit-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
)


def parse_rl_headers(headers: Mapping | object) -> dict:
    """Case-insensitive parse. Semantics per Groq docs (see module docstring).

    *-requests are PER DAY, *-tokens are PER MINUTE.
    """
    d: dict[str, Optional[str]] = {}
    for k, v in _items(headers):
        if k in _KEYS and k not in d:
            d[k] = v
    g = d.get
    return {
        "retry_after_s": parse_duration(g("retry-after")),
        "limit_rpd": _int(g("x-ratelimit-limit-requests")),
        "limit_tpm": _int(g("x-ratelimit-limit-tokens")),
        "remaining_rpd": _int(g("x-ratelimit-remaining-requests")),
        "remaining_tpm": _int(g("x-ratelimit-remaining-tokens")),
        "reset_rpd_s": parse_duration(g("x-ratelimit-reset-requests")),
        "reset_tpm_s": parse_duration(g("x-ratelimit-reset-tokens")),
        "raw": {k: v for k, v in _items(headers)
                if k.startswith("x-ratelimit") or k == "retry-after"},
    }
