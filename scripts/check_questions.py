"""Validate the eval set. Zero tokens, zero network, exits non-zero on any fault.

The failure this exists to catch: a `gold` chunk id that is not in the index. A
typo there does not crash anything -- it silently scores a correct retrieval as a
miss, which is how a retrieval number becomes fiction (BUG-015).

    python -m scripts.check_questions
    python -m scripts.check_questions --questions data/eval/questions.jsonl \
        --chunks data/chunks/exp900/chunks.jsonl

Exit 0 = clean, 1 = faults found (each one printed with its qid).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED = ("qid", "author", "type", "paper", "question", "answer", "gold")
TYPES = {"single", "numeric", "cross", "ambiguous", "unanswerable"}
#: Types for which an empty `gold` is CORRECT rather than a fault. An ambiguous
#: question has several defensible answers, so naming one chunk as "the" gold
#: would score a correct retrieval as a miss. Keeping the list explicit means a
#: missing gold on any other type is always a fault.
NO_GOLD_TYPES = {"ambiguous", "unanswerable"}
PAPERS = {"attention", "moshi", "hnet", None}


def check(questions: list[dict], chunk_ids: set[str]) -> list[str]:
    faults: list[str] = []
    seen: set[str] = set()
    for i, q in enumerate(questions, 1):
        where = f"line {i} qid={q.get('qid', '<missing>')}"
        if q.get("qid") in seen:
            faults.append(f"{where}: duplicate qid")
        seen.add(q.get("qid"))
        missing = [f for f in REQUIRED if f not in q]
        if missing:
            faults.append(f"{where}: missing field(s) {missing}")
            continue
        if q["type"] not in TYPES:
            faults.append(f"{where}: type {q['type']!r} not in {sorted(TYPES)}")
        if q["paper"] not in PAPERS:
            faults.append(f"{where}: paper {q['paper']!r} not in {sorted(p for p in PAPERS if p)}")
        if not isinstance(q["gold"], list):
            faults.append(f"{where}: gold must be a list, got {type(q['gold']).__name__}")
            continue
        # `gold: []` as a "not checked yet" placeholder corrupted the P3
        # false-answer rate (BUG-003), so emptiness is only legal where it means
        # something: an unanswerable question has nothing to find, and an
        # ambiguous one has several right answers and no single gold chunk.
        if q["type"] == "unanswerable" and q["gold"]:
            faults.append(f"{where}: type=unanswerable but gold is non-empty")
        if q["type"] not in NO_GOLD_TYPES and not q["gold"]:
            faults.append(f"{where}: type={q['type']} but gold is empty "
                          f"(only {sorted(NO_GOLD_TYPES)} may have no gold)")
        for cid in q["gold"]:
            if cid not in chunk_ids:
                faults.append(f"{where}: gold id {cid!r} is not in the index")
    return faults


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="data/eval/questions.jsonl")
    ap.add_argument("--chunks", default="data/chunks/exp900/chunks.jsonl")
    a = ap.parse_args(argv)

    questions = [json.loads(l) for l in
                 Path(a.questions).read_text(encoding="utf-8").splitlines() if l.strip()]
    chunks = [json.loads(l) for l in
              Path(a.chunks).read_text(encoding="utf-8").splitlines() if l.strip()]
    ids = {c["chunk_id"] for c in chunks}

    faults = check(questions, ids)
    authors: dict[str, int] = {}
    for q in questions:
        authors[q.get("author", "<none>")] = authors.get(q.get("author", "<none>"), 0) + 1
    types: dict[str, int] = {}
    for q in questions:
        types[q.get("type", "?")] = types.get(q.get("type", "?"), 0) + 1

    print(f"questions {len(questions)}  chunks {len(chunks)}")
    print(f"  authors {authors}")
    print(f"  types   {types}")
    if faults:
        print(f"\nFAIL {len(faults)} fault(s):")
        for f in faults:
            print(f"  {f}")
        return 1
    n_gold = sum(1 for q in questions if q.get("gold"))
    print(f"\nOK: {n_gold} questions carry gold and every id resolves; "
          f"{len(questions) - n_gold} legitimately carry none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
