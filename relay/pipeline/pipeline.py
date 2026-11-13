"""P6: minimal pipeline. Retrieve -> gate -> draft -> verify -> reply.

Hard rule H1 lives at the only exit, `send_reply`, which accepts nothing but the
three permitted reply types.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Optional

from relay.config import Config
from relay.contracts import Citation, NoEvidence, PassagesOnly, Reply, is_reply
from relay.gateway.gateway import (
    BreakerOpen, DeadlineExceeded, Gateway, UpstreamError,
)
from relay.gateway.stream import StreamProtocolError
from relay.pipeline.verify import check_citations, check_numbers_present, mint

from relay.pipeline.cascade import CascadeConfig, model_for, routing_event_fields
from relay.retrieval.bm25 import Hit, Retriever
from relay.retrieval.text import contains_quote

DRAFT_PROMPT = """Answer the question using ONLY the numbered passages.
Cite with [chunk_id]. If the passages do not contain the answer, reply exactly:
NOT_FOUND

Passages:
{passages}

Question: {question}
"""


#: The reason sent for each cause. `budget_gone` is ONLY a refused budget.
REASON_NAMES: dict[type, str] = {
    DeadlineExceeded: "budget_gone",    # a budget was actually refused
    UpstreamError: "upstream_error",    # the provider failed / the deadline passed
    # 5c pinned this to PROPAGATE as StreamProtocolError rather than be wrapped.
    # Left as it is -- but the pipeline must still catch it, or the request ends
    # with NO terminal event at all, which is the one outcome this project forbids.
    # Same cause, same reason: unusable bytes from upstream.
    StreamProtocolError: "upstream_error",
    BreakerOpen: "breaker_open",        # we refused to call at all
}

#: What the user is told. It must never contradict the reason: an upstream failure
#: that reads as "out of budget" is the defect this table exists to prevent.
REASON_MESSAGES: dict[type, str] = {
    DeadlineExceeded: (
        "I could not spend the budget to answer; here are the passages that would."),
    UpstreamError: (
        "The model did not answer this time; here are the passages that would."),
    StreamProtocolError: (
        "The model did not answer this time; here are the passages that would."),
    BreakerOpen: (
        "The model is unavailable right now; here are the passages that would "
        "answer this."),
}


def reason_for(exc: BaseException) -> tuple[str, str]:
    """(reason, message) for an exception that ended the request.

    Matched by `isinstance`, not by `type(e)`: a subclass (or a test double) must
    not raise KeyError from the error path, which would turn a handled failure into
    an unhandled one.
    """
    for cls in (DeadlineExceeded, StreamProtocolError, UpstreamError, BreakerOpen):
        if isinstance(exc, cls):
            return REASON_NAMES[cls], REASON_MESSAGES[cls]
    raise TypeError(f"no reason mapping for {type(exc).__name__}")


@dataclass
class Outcome_:
    reply: Reply
    terminal: str
    reason: str = ""


def format_passages(hits: list[Hit]) -> str:
    return "\n\n".join(f"[{h.chunk.chunk_id}] {h.chunk.text}" for h in hits)


def parse_draft(text: str, valid_ids: set[str]) -> tuple[str, list[Citation]]:
    """Extract the answer prose and the [chunk_id] citations the model used."""
    ids = re.findall(r"\[([a-z0-9\-]+:s[^\]]+:c\d{4})\]", text)
    citations = []
    for cid in dict.fromkeys(ids):
        if cid in valid_ids:
            citations.append(cid)
    prose = re.sub(r"\[[a-z0-9\-]+:s[^\]]+:c\d{4}\]", "", text).strip()
    return prose, [Citation(chunk_id=c, quote="") for c in citations]


def gate(hits: list[Hit], threshold: float) -> bool:
    return bool(hits) and hits[0].score >= threshold


def send_reply(reply: Optional[Reply], *, abandoned: bool = False) -> Optional[Reply]:
    """The single exit. H1 enforced here and nowhere else.

    `abandoned=True` is the one case where the correct reply is NO reply: the user
    has left, so there is nobody to send to. That satisfies H1 trivially (nothing
    unverified is transmitted) and it is checked rather than assumed -- an
    abandonment that still carries a payload is a bug, not a courtesy.
    """
    if abandoned:
        if reply is not None:
            raise TypeError(
                "abandoned request must send nothing, "
                f"got {type(reply).__name__}")
        return None
    if not is_reply(reply):
        raise TypeError(f"H1 violation: refusing to send {type(reply).__name__}")
    return reply


class Pipeline:
    def __init__(self, cfg: Config, retriever: Retriever, gateway: Gateway,
                 scope, embed_quote_from: Optional[callable] = None,
                 patience_s: Optional[float] = None, stream: bool = False,
                 ladder_level: int = 0, tpm_remaining_frac: Optional[float] = None,
                 queue_wait_s: float = 0.0):
        self.cfg = cfg
        #: The degradation level for THIS request, computed by
        #: `relay.pipeline.ladder.compute_level` from budget state. Passed in rather
        #: than recomputed here: the same level routes the model (item F), scales
        #: top_k and decides whether generation is allowed, and three independent
        #: computations of it would eventually disagree.
        self.ladder_level = ladder_level
        self.tpm_remaining_frac = tpm_remaining_frac
        self.queue_wait_s = queue_wait_s
        self.r = retriever
        self.gw = gateway
        self.scope = scope
        self.k = cfg.get("pipeline.top_k", 4)
        # MEASURED, so it must not have a fallback. The old `cfg.get(..., 15.0)` sat
        # one keystroke away from silently substituting 15.0 for the committed 15.86
        # -- a threshold nobody measured, in a project whose rule 4 is "no magic
        # numbers". A missing key is a configuration error and has to say so.
        self.threshold = cfg.require("retrieval.gate_threshold")
        # Two keys on purpose: the stand-in deadline is provisional (a documented
        # stand-in value), the real one is measured and still null until P1/L5.
        # Preferring the measured key when present keeps that ordering explicit
        # instead of hiding it behind `or`.
        measured = cfg.get("gateway.request_deadline_s", None)
        self.deadline_source = ("measured" if measured is not None else "standin")
        self.deadline = (measured if measured is not None
                         else cfg.get("gateway.request_deadline_standin_s", 30.0))
        # H4: how long a user waits before leaving. PASSED IN, never guessed --
        # expiry here cancels the in-flight call and stops token spend.
        # `None` here means "no abandonment timer", which is the correct behaviour
        # before the value is measured. Defaulting the KEY to None (rather than
        # omitting it) keeps an absent key distinguishable from a null one.
        self.patience_s = (patience_s if patience_s is not None
                           else cfg.get("user.patience_s", None))
        #: Stream the draft so model_ttft is observable. Off by default: the
        #: pipeline parses the whole draft before verifying, so streaming the
        #: draft to itself buys no user-visible latency yet -- it buys the
        #: MEASUREMENT of when the model actually started answering.
        self.stream = stream or bool(cfg.get("pipeline.stream", False))

    #: Set by the gateway on the Attempt it just finished, so the pipeline can
    #: compute user_ttft without re-deriving when the request was sent.
    _last_attempt = None

    async def _draft(self, hits, question: str, stream: bool = False):
        self._t_request_sent = self.gw.clock.now()
        # ROUTING IS ONE FUNCTION (item F). The draft is the only step whose output
        # the user reads, so it is the only one that goes to the large model -- and
        # only at L0. At L1 and above everything collapses to small, because sending
        # the draft to the large model would undo the level just chosen.
        cascade = CascadeConfig.from_config(self.cfg)
        model_id = model_for("draft", self.ladder_level, cascade)
        self.scope.emit("cascade.route", **routing_event_fields(
            "draft", self.ladder_level, cascade))
        body = await self.gw.call(
            scope=self.scope, step="draft",
            model=model_id,
            messages=[{"role": "user", "content": DRAFT_PROMPT.format(
                passages=format_passages(hits), question=question)}],
            max_tokens=self.cfg.get("pipeline.max_tokens.draft", 400),
            deadline_s=self.deadline,
            reasoning_effort=self.cfg.get("models.reasoning_effort"),
            stream=stream or self.stream)
        return body

    def _stamp_user_ttft(self, reply) -> None:
        """user_ttft = when the VERIFIED answer first became available to the user.

        This cannot ride on `attempt.end`: that event is emitted by the gateway
        before verification runs, so anything written to the Attempt afterwards
        never reaches the log (the log is append-only by design). It is therefore
        its own event, emitted here, carrying the same attempt id so the three
        stamps can be joined back together.

        If it is absent, the answer was never verified and there is no user_ttft.
        That absence is correct; a zero would be a lie.
        """
        att = getattr(self.gw, "_last_attempt", None)
        if att is None:
            return
        now = self.gw.clock.now()
        att.t_user_ttft = now
        # The gap first_token->user_ttft is TWO phases, not one. `gen_end` is when
        # the model stopped producing; after that we verify. Reporting a single
        # "verification" number would have charged the model's own generation time
        # to our verifier (BUG-020).
        gen_end = att.t_generation_end
        try:
            self.scope.emit(
                "reply.ready", attempt_id=att.attempt_id, t_sent=att.t_sent,
                first_delta_s=(None if att.t_first_delta is None
                               else round(att.t_first_delta - att.t_sent, 4)),
                model_ttft_s=(None if att.t_first_token is None
                              else round(att.t_first_token - att.t_sent, 4)),
                generation_end_s=(None if gen_end is None
                                  else round(gen_end - att.t_sent, 4)),
                generating_s=(None if (att.t_first_token is None or gen_end is None)
                              else round(gen_end - att.t_first_token, 4)),
                verifying_s=(None if gen_end is None
                             else round(now - gen_end, 4)),
                user_ttft_s=round(now - att.t_sent, 4),
                post_ttft_s=(None if gen_end is None
                             else round(now - att.t_first_token, 4)),
                reply=type(reply).__name__)
        except Exception:
            # Never let instrumentation break an answer that is ready to send.
            pass

    async def answer(self, question: str) -> Outcome_:
        hits = self.r.search(question, k=self.k)
        if not hits:
            return Outcome_(send_reply(NoEvidence("The papers do not say.",
                                                 nearest=())), "no_evidence", "no_hits")
        if not gate(hits, self.threshold):
            return Outcome_(send_reply(PassagesOnly(
                "Not enough evidence to answer; here are the closest passages.",
                tuple(h.chunk for h in hits), "verify_failed")), "passages_only",
                "verify_failed")

        try:
            if self.patience_s:
                # The wait_for is the abandonment mechanism: when it fires it
                # CANCELS the draft, which cancels the HTTP request, which stops
                # the provider generating. Tokens already generated are spent;
                # nothing after this point is.
                body = await asyncio.wait_for(self._draft(hits, question),
                                              timeout=self.patience_s)
            else:
                body = await self._draft(hits, question)
        except asyncio.TimeoutError:
            # The reason carries the VALUE. "patience" alone is unreadable a week
            # later: it does not say whether the user waited 50 ms or 20 s, and
            # that number is the whole content of an abandonment measurement.
            self.scope.abandon(f"patience_{self.patience_s}s")
            return Outcome_(send_reply(None, abandoned=True), "abandoned",
                            f"patience_{self.patience_s}s")
        except (DeadlineExceeded, UpstreamError, StreamProtocolError,
                BreakerOpen) as e:
            # The reason names the CAUSE, and the text must not contradict it.
            # Previously every DeadlineExceeded became `budget_gone` -- so a 500
            # storm told the user "the model is busy" and told the log that a budget
            # was spent, while the budget was untouched (BUG-042).
            #
            # Each of these costs 0 tokens and still returns the passages; only the
            # sentence differs. Both live in module-level tables so a test can
            # assert that no non-budget sentence mentions budget or tokens.
            reason, message = reason_for(e)
            return Outcome_(send_reply(PassagesOnly(
                message, tuple(h.chunk for h in hits), reason)),
                "passages_only", str(e))

        text = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if "NOT_FOUND" in text:
            return Outcome_(send_reply(NoEvidence("The papers do not say.",
                                                 nearest=tuple(h.chunk for h in hits))),
                            "no_evidence", "model_not_found")

        # Quote-first: the model's citation must actually occur in that chunk.
        prose, cited = parse_draft(text, set(self.r.by_id))
        by_id = self.r.by_id
        citations = []
        for c in cited:
            chunk = by_id[c.chunk_id]
            # Take the longest sentence of the draft that appears verbatim.
            #
            # The comparison MUST go through the same normalisation the verifier
            # uses (NFKC + de-hyphenation + whitespace collapse). A raw
            # `s in chunk.text` here fails whenever the draft's whitespace differs
            # from the chunk's -- and a streamed draft differs by construction,
            # because SSE deltas are word-shaped and the newline between two PDF
            # lines is not part of any delta (BUG-018). Buffered drafts happened to
            # preserve the newline, so the fault only appeared once streaming was
            # added; it would have appeared for any model that wrapped differently.
            best = ""
            for sent in re.split(r"(?<=[.!?])\s+", prose):
                cand = sent.strip()
                if len(cand) > 25 and contains_quote(chunk.text, cand) \
                        and len(cand) > len(best):
                    best = cand
            if best:
                citations.append(Citation(chunk_id=c.chunk_id, quote=best))
        # Verification is done from here on; the verified answer exists.
        check = check_citations(prose, citations, by_id)
        if not check:
            return Outcome_(send_reply(PassagesOnly(
                "Could not verify this answer against the sources.",
                tuple(h.chunk for h in hits), "verify_failed")), "passages_only",
                check.reason)
        nums = check_numbers_present(prose, [by_id[c.chunk_id].text for c in citations])
        if not nums:
            return Outcome_(send_reply(PassagesOnly(
                "An unverified number appeared in the answer.",
                tuple(h.chunk for h in hits), "verify_failed")), "passages_only",
                nums.reason)
        reply = mint(prose, tuple(citations))
        self._stamp_user_ttft(reply)     # first byte of the VERIFIED answer
        return Outcome_(send_reply(reply), "answered", "ok")
