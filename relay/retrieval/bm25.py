"""P3: BM25 retrieval over the chunk corpus.

Deliberately small: no vectors, no reranker (PRD s12 non-goals). The score is only
used for ordering and for the code gate's evidence test, so an off-the-shelf BM25 is
enough until P10 measures whether it is.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from rank_bm25 import BM25Okapi

from relay.contracts import Chunk
from relay.retrieval.text import normalize, tokenize


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    rank: int


class Retriever:
    """In-memory BM25 index over chunks.jsonl.

    Chunk ids are unique by construction (`test_real_pdfs_have_no_duplicate_chunk_ids`),
    so `by_id` is a plain dict and the mapping is total.
    """

    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        if not chunks:
            raise ValueError("empty corpus")
        self.chunks = chunks
        self.by_id = {c.chunk_id: c for c in chunks}
        self._corpus_tokens = [tokenize(c.text) for c in chunks]
        self._bm25 = BM25Okapi(self._corpus_tokens, k1=k1, b=b)

    @classmethod
    def from_jsonl(cls, path: str | Path, k1: float = 1.5, b: float = 0.75) -> "Retriever":
        chunks = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                chunks.append(Chunk(chunk_id=row["chunk_id"], paper=row["paper"],
                                    section=row["section"], page=row["page"],
                                    text=row["text"]))
        return cls(chunks, k1=k1, b=b)

    def search(self, query: str, k: int = 4,
               paper: Optional[str] = None) -> list[Hit]:
        """Top-k by BM25. `paper` restricts to one paper (used by the eval grader)."""
        if k <= 0:
            return []
        q = tokenize(query)
        if not q:
            return []
        scores = self._bm25.get_scores(q)
        order = sorted(range(len(self.chunks)), key=lambda i: -scores[i])
        hits: list[Hit] = []
        for i in order:
            c = self.chunks[i]
            if paper is not None and c.paper != paper:
                continue
            if scores[i] <= 0.0 and hits:
                break                      # scores are sorted; nothing after this scores
            hits.append(Hit(chunk=c, score=float(scores[i]), rank=len(hits)))
            if len(hits) >= k:
                break
        return hits

    def top_score(self, query: str) -> float:
        hits = self.search(query, k=1)
        return hits[0].score if hits else 0.0


def build_queries(chunks: Iterable[Chunk]) -> dict[str, list[str]]:
    """Guard helper: no chunk should be its own best query, but if it is, the eval
    set is measuring the wrong thing."""
    r = Retriever(list(chunks))
    out = {}
    for c in chunks:
        hits = r.search(normalize(c.text)[:200], k=1)
        if hits and hits[0].chunk.chunk_id != c.chunk_id:
            out[c.chunk_id] = [h.chunk.chunk_id for h in hits]
    return out
