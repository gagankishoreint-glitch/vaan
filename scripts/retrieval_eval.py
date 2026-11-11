"""P3: retrieval-only evaluation. ZERO tokens, zero network.

Measures, per (chunk_size, overlap) setting:
  recall@k      fraction of questions whose gold chunk is in the top k
  mrr           mean reciprocal rank of the first gold chunk
  gate          what the code evidence-gate would decide, and whether that is right

The gate is the cheap stand-in for "strong evidence -> draft": top-1 score above a
threshold. Picking the threshold from data here is what stops the pipeline from
guessing it later (rule 4).

    python -m scripts.retrieval_eval --settings 600/100 900/150 1200/200
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from relay.config import load_config
from relay.retrieval.bm25 import Retriever

SETTINGS = [(600, 100), (900, 150), (1200, 200)]


def load_questions(path: Path) -> list[dict]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def evaluate(retriever: Retriever, questions: list[dict], k: int,
             threshold: float) -> dict:
    rows = []
    for q in questions:
        hits = retriever.search(q["question"], k=k)
        got = [h.chunk.chunk_id for h in hits]
        gold = q["gold"]
        rank = next((i for i, cid in enumerate(got) if cid in gold), None)
        top = hits[0].score if hits else 0.0
        gated_in = top >= threshold
        rows.append({
            "qid": q["qid"], "type": q["type"], "gold": gold, "top": got[:k],
            "rank": rank, "top_score": round(top, 3), "gated_in": gated_in,
        })
    answerable = [r for r in rows if r["gold"]]
    unanswerable = [r for r in rows if not r["gold"]]
    hit = [r for r in answerable if r["rank"] is not None]
    mrr = sum(1 / (r["rank"] + 1) for r in hit) / max(1, len(answerable))
    # false abstain: answerable question the gate would refuse
    fa = [r for r in answerable if not r["gated_in"]]
    # false answer: unanswerable question the gate would accept
    fb = [r for r in unanswerable if r["gated_in"]]
    return {
        "k": k, "threshold": threshold, "rows": rows,
        "recall_at_k": len(hit) / max(1, len(answerable)),
        "mrr": mrr,
        "false_abstain": len(fa) / max(1, len(answerable)),
        "false_answer": len(fb) / max(1, len(unanswerable)),
        "n_answerable": len(answerable), "n_unanswerable": len(unanswerable),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", nargs="*", default=[f"{s}/{o}" for s, o in SETTINGS])
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--chunk-root", default="data/chunks/exp")
    ap.add_argument("--questions", default="data/eval/questions.jsonl")
    ap.add_argument("--out", default="data/eval/retrieval_results.json")
    a = ap.parse_args(argv)

    cfg = load_config()
    k1 = cfg.get("retrieval.bm25_k1", 1.5)
    b = cfg.get("retrieval.bm25_b", 0.75)
    questions = load_questions(Path(a.questions))

    results = []
    print(f"{'setting':>12} {'recall@'+str(a.k):>10} {'mrr':>6} "
          f"{'false_abs':>10} {'false_ans':>10} {'thresh':>7}")
    for s in a.settings:
        size, overlap = (int(x) for x in s.split("/"))
        # Naming: exp{size} matches `scripts.ingest --out data/chunks/exp{size}`
        path = Path(f"{a.chunk_root}{size}") / "chunks.jsonl"
        if not path.is_file():
            print(f"  SKIP {s}: {path} missing. Build it with:\n"
                  f"    python -m scripts.ingest --chunk-size {size} "
                  f"--overlap {overlap} --out data/chunks/exp{size}", file=sys.stderr)
            continue
        r = Retriever.from_jsonl(path, k1=k1, b=b)
        # threshold chosen from the data: the 25th percentile of answerable top-1
        # scores, which admits most real evidence without admitting nothing.
        probe = evaluate(r, questions, a.k, 0.0)
        scores = sorted(x["top_score"] for x in probe["rows"]
                        if x["gold"] and x["top_score"] > 0)
        thr = scores[len(scores) // 4] if scores else 0.0
        res = evaluate(r, questions, a.k, thr)
        res.update(chunk_size=size, overlap=overlap, n_chunks=len(r.chunks))
        results.append(res)
        print(f"{s:>12} {res['recall_at_k']:>10.1%} {res['mrr']:>6.2f} "
              f"{res['false_abstain']:>10.1%} {res['false_answer']:>10.1%} {thr:>7.2f}")

    # per-type recall at the best setting, for the report
    if results:
        best = max(results, key=lambda r: (r["recall_at_k"], -r["false_answer"]))
        by_type: dict[str, list] = {}
        for row in best["rows"]:
            if row["gold"]:
                by_type.setdefault(row["type"], []).append(row["rank"] is not None)
        print(f"\nper-type recall at {best['chunk_size']}/{best['overlap']}:")
        for t, hits in sorted(by_type.items()):
            print(f"  {t:<10} {sum(hits)}/{len(hits)}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
