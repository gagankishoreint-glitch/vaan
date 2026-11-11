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


def sweep(retriever: Retriever, questions: list[dict], k: int,
          n_points: int = 40) -> dict:
    """Every achievable decision, not one threshold.

    A single operating point invites the claim "the gate cannot separate the
    classes". That claim is only true if it holds across the WHOLE threshold range,
    so the sweep is what turns an impression into a statement. Each row is one
    threshold with the actual counts, because a percentage without an n is not
    evidence.
    """
    rows = []
    for q in questions:
        hits = retriever.search(q["question"], k=k)
        top = hits[0].score if hits else 0.0
        rows.append({"answerable": bool(q["gold"]), "score": top})

    ans = [r["score"] for r in rows if r["answerable"]]
    una = [r["score"] for r in rows if not r["answerable"]]
    n_a, n_u = len(ans), len(una)

    # Candidate thresholds: every distinct score, so no operating point is missed.
    cands = sorted({round(s, 6) for s in ans + una})
    if not cands:
        return {"points": [], "n_answerable": n_a, "n_unanswerable": n_u}
    # Keep the cost bounded while still covering the whole range uniformly.
    if len(cands) > n_points:
        step = (len(cands) - 1) / (n_points - 1)
        cands = [cands[round(i * step)] for i in range(n_points)]

    points = []
    for t in cands:
        fa = sum(1 for s in ans if s < t)       # answerable refused
        fb = sum(1 for s in una if s >= t)      # unanswerable admitted
        points.append({
            "threshold": round(t, 3),
            "false_abstain": fa, "n_answerable": n_a,
            "false_abstain_frac": fa / n_a if n_a else 0.0,
            "false_answer": fb, "n_unanswerable": n_u,
            "false_answer_frac": fb / n_u if n_u else 0.0,
            "total_errors": fa + fb,
        })
    return {"points": points, "n_answerable": n_a, "n_unanswerable": n_u,
            "answerable_scores": sorted(round(x, 3) for x in ans),
            "unanswerable_scores": sorted(round(x, 3) for x in una)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", nargs="*", default=[f"{s}/{o}" for s, o in SETTINGS])
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--chunk-root", default="data/chunks/exp")
    ap.add_argument("--questions", default="data/eval/questions.jsonl")
    ap.add_argument("--out", default="data/eval/retrieval_results.json")
    ap.add_argument("--sweep-setting", default=None,
                    help="setting to sweep, e.g. 900/150 (default: best)")
    ap.add_argument("--no-sweep", action="store_true")
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

    # ------------------------------------------------------------ the sweep
    if results and not a.no_sweep:
        target = a.sweep_setting or f"{best['chunk_size']}/{best['overlap']}"
        sel = next((r for r in results
                    if f"{r['chunk_size']}/{r['overlap']}" == target), best)
        path = Path(f"{a.chunk_root}{sel['chunk_size']}") / "chunks.jsonl"
        r = Retriever.from_jsonl(path, k1=k1, b=b)
        sw = sweep(r, questions, a.k)
        print(f"\nthreshold sweep at {target}  "
              f"(n_answerable={sw['n_answerable']}, "
              f"n_unanswerable={sw['n_unanswerable']}, k={a.k})")
        print(f"{'thresh':>8} {'false_abs':>10} {'false_ans':>10} {'errors':>7}")
        print("-" * 39)
        for p in sw["points"]:
            print(f"{p['threshold']:>8.2f} "
                  f"{p['false_abstain']:>4}/{p['n_answerable']:<5} "
                  f"{p['false_answer']:>4}/{p['n_unanswerable']:<5} "
                  f"{p['total_errors']:>7}")
        best_pt = min(sw["points"], key=lambda p: p["total_errors"])
        print(f"\nlowest total errors at thresh={best_pt['threshold']}: "
              f"{best_pt['false_abstain']}/{best_pt['n_answerable']} abstained, "
              f"{best_pt['false_answer']}/{best_pt['n_unanswerable']} admitted")
        zero_both = [p for p in sw["points"]
                     if p["false_abstain"] == 0 and p["false_answer"] == 0]
        print(f"thresholds with BOTH zero: {len(zero_both)}")
        if zero_both:
            print(f"  range {zero_both[0]['threshold']} .. {zero_both[-1]['threshold']}")
        else:
            print("  none: no threshold admits every answerable question while "
                  "refusing every unanswerable one")
        # Overlap diagnostic: how far the two score distributions interpenetrate.
        top_a = max(sw["answerable_scores"]) if sw["answerable_scores"] else 0
        top_u = max(sw["unanswerable_scores"]) if sw["unanswerable_scores"] else 0
        print(f"highest answerable top-1 = {top_a:.2f}; "
              f"highest unanswerable top-1 = {top_u:.2f}")
        if top_u:
            beaten = sum(1 for s in sw["answerable_scores"] if s < top_u)
            print(f"  -> the best unanswerable question outscores "
                  f"{beaten}/{sw['n_answerable']} answerable ones")
        Path(a.out).with_name("retrieval_sweep.json").write_text(
            json.dumps({"setting": target, **sw}, indent=2), encoding="utf-8")
        print(f"\nwrote {Path(a.out).with_name('retrieval_sweep.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
