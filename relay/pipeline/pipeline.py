"""P6: minimal pipeline. Retrieve -> gate -> draft -> verify -> reply.

Hard rule H1 lives at the only exit, `send_reply`, which accepts nothing but the
three permitted reply types.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from relay.config import Config
from relay.contracts import Citation, NoEvidence, PassagesOnly, Reply, is_reply
from relay.gateway.gateway import DeadlineExceeded, BreakerOpen, Gateway
from relay.pipeline.verify import check_citations, check_numbers_present, mint
from relay.retrieval.bm25 import Hit, Retriever

DRAFT_PROMPT = """Answer the question using ONLY the numbered passages.
Cite with [chunk_id]. If the passages do not contain the answer, reply exactly:
NOT_FOUND

Passages:
{passages}

Question: {question}
"""


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


def send_reply(reply: Reply) -> Reply:
    """The single exit. H1 enforced here and nowhere else."""
    if not is_reply(reply):
        raise TypeError(f"H1 violation: refusing to send {type(reply).__name__}")
    return reply


class Pipeline:
    def __init__(self, cfg: Config, retriever: Retriever, gateway: Gateway,
                 scope, embed_quote_from: Optional[callable] = None):
        self.cfg = cfg
        self.r = retriever
        self.gw = gateway
        self.scope = scope
        self.k = cfg.get("pipeline.top_k", 4)
        self.threshold = cfg.get("retrieval.gate_threshold", 15.0)
        self.deadline = (cfg.get("gateway.request_deadline_s")
                         or cfg.get("gateway.request_deadline_standin_s", 30.0))

    async def answer(self, question: str) -> Outcome_:
        hits = self.r.search(question, k=self.k)
        if not hits:
            return Outcome_(send_reply(NoEvidence("The papers do not say.",
                                                 nearest=())), "no_evidence", "no_hits")
        if not gate(hits, self.threshold):
            return Outcome_(send_reply(PassagesOnly(
                "Not enough evidence to answer; here are the closest passages.",
                tuple(h.chunk for h in hits), "verify_failed")), "passages_only",
                "gate_low_score")

        try:
            body = await self.gw.call(
                scope=self.scope, step="draft",
                model=self.cfg.get("models.small.id"),
                messages=[{"role": "user", "content": DRAFT_PROMPT.format(
                    passages=format_passages(hits), question=question)}],
                max_tokens=self.cfg.get("pipeline.max_tokens.draft", 400),
                deadline_s=self.deadline)
        except (DeadlineExceeded, BreakerOpen) as e:
            return Outcome_(send_reply(PassagesOnly(
                "The model is busy; here are the passages that would answer this.",
                tuple(h.chunk for h in hits), "budget_gone" if isinstance(
                    e, DeadlineExceeded) else "breaker_open")), "passages_only", str(e))

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
            best = ""
            for sent in re.split(r"(?<=[.!?])\s+", prose):
                s = sent.strip()
                if len(s) > 25 and s in chunk.text and len(s) > len(best):
                    best = s
            if best:
                citations.append(Citation(chunk_id=c.chunk_id, quote=best))
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
        return Outcome_(send_reply(mint(prose, tuple(citations))), "answered", "ok")
