"""Shared types. Every layer agrees on these before anything else is written.

Frozen exactly as agreed in the P0 spec. Changes here are contract changes:
announce them, then list every affected file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Outcome(str, Enum):
    OK = "ok"
    RATE_LIMITED_MIN = "rate_limited_min"
    RATE_LIMITED_DAY = "rate_limited_day"
    RATE_LIMITED_UNKNOWN = "rate_limited_unknown"   # 429 we could not classify; keep raw
    TOO_LARGE = "too_large"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BREAKER_OPEN = "breaker_open"


class Terminal(str, Enum):
    ANSWERED = "answered"                  # VerifiedAnswer
    NO_EVIDENCE = "no_evidence"            # "the papers don't say"
    PASSAGES_ONLY = "passages_only"        # 0-token or unverified fallback
    BUSY = "busy"                          # honest delay message with retry hint
    ABANDONED = "abandoned"
    ERROR = "error"


class RetryPolicy(str, Enum):
    """Policy switch (PRD s5). 'naive' exists only to demonstrate harm on the stand-in."""
    MANAGED = "managed"
    NAIVE = "naive"


# ---------------------------------------------------------------- attempts

@dataclass
class Attempt:
    attempt_id: str
    req_id: str
    step: str                  # rewrite | draft | verify | probe
    backend: str               # groq | standin -- the backend for THIS attempt.
                               # Logged as `attempt_backend`; `backend` on an event
                               # is run scope (DECISIONS D-008).
    model: str
    t_sent: float
    t_first_byte: Optional[float] = None
    t_first_token: Optional[float] = None      # == model_ttft (first CONTENT delta)
    t_end: Optional[float] = None
    #: First SSE frame of any kind, including a role-only frame with no content.
    #: Always <= t_first_token. Their gap is connection + model warm-up.
    t_first_delta: Optional[float] = None
    #: First byte of the VERIFIED answer reaching the user, i.e. after verification.
    #: Always >= t_first_token.
    t_user_ttft: Optional[float] = None
    #: The model finished generating. t_first_token -> t_generation_end is the time
    #: spent GENERATING; t_generation_end -> t_user_ttft is the time spent
    #: VERIFYING. Without this stamp the two were indistinguishable, and the whole
    #: model_ttft->user_ttft gap was attributed to verification -- which is wrong,
    #: because H1 means we cannot show anything until the draft is complete, so
    #: generation is fully inside that gap (BUG-020).
    t_generation_end: Optional[float] = None
    status: Optional[int] = None
    outcome: Optional[Outcome] = None
    retry_after_s: Optional[float] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    tokens_cached: Optional[int] = None
    rl_headers_raw: dict = field(default_factory=dict)   # unmodified strings
    #: Every SSE line received, verbatim, with its parse outcome. Empty for
    #: non-streamed attempts. This exists so a failed stream can be diagnosed from
    #: the event log alone: the previous parser discarded unparseable lines, which
    #: made "provider sent garbage" and "provider sent nothing" the same observation.
    sse_raw: list = field(default_factory=list)
    n_sse_lines: int = 0
    n_sse_malformed: int = 0
    sse_saw_done: Optional[bool] = None
    #: A protocol fault, distinct from a timeout. Retryable, but logged as its own
    #: outcome so the two never get averaged together.
    protocol_error: Optional[str] = None
    #: True when THIS attempt was cut by `gateway.attempt_timeout_s` rather than by
    #: the outer request deadline. A per-attempt expiry is retryable; the outer
    #: deadline ends the request. Without the flag the two are indistinguishable in
    #: the log and a retry storm looks like normal traffic.
    attempt_timed_out: Optional[bool] = None
    timeout_limit: Optional[str] = None    # "attempt_timeout" | "deadline"
    error_body: Optional[str] = None

    def finished(self) -> bool:
        return self.t_end is not None


# ---------------------------------------------------------------- corpora

@dataclass(frozen=True)
class Chunk:
    chunk_id: str              # e.g. "attn-v7:s3.2:c04"
    paper: str                 # "attention" | "moshi" | "hnet"
    section: str
    page: int
    text: str


@dataclass(frozen=True)
class Citation:
    chunk_id: str
    quote: str                 # must appear verbatim in the chunk text


# ---------------------------------------------------------------- replies

@dataclass(frozen=True)
class VerifiedAnswer:
    """Constructed ONLY via mint_verified(), called ONLY from pipeline/verify.py.

    A test (tests/test_mint_guard.py) greps the codebase to enforce that. Python
    cannot make this airtight: anyone can import mint_verified. The enforcement is
    social + CI, which the PRD accepts.
    """
    text: str
    citations: tuple[Citation, ...]
    _minted: bool = field(default=False, repr=False)

    def __post_init__(self):
        if not self._minted:
            raise TypeError("VerifiedAnswer must be created via mint_verified()")


def mint_verified(text: str, citations: tuple[Citation, ...]) -> VerifiedAnswer:
    return VerifiedAnswer(text=text, citations=citations, _minted=True)


@dataclass(frozen=True)
class NoEvidence:
    message: str
    nearest: tuple[Chunk, ...] = ()


@dataclass(frozen=True)
class PassagesOnly:
    message: str
    passages: tuple[Chunk, ...]
    reason: str                # budget_gone | verify_failed | breaker_open | queue_full


Reply = VerifiedAnswer | NoEvidence | PassagesOnly

REPLY_TYPES: tuple[type, ...] = (VerifiedAnswer, NoEvidence, PassagesOnly)


def is_reply(obj: object) -> bool:
    """The single runtime test of H1: is this object sendable?"""
    return isinstance(obj, REPLY_TYPES)
