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
from relay.retrieval.text import contains_quote

SETTINGS = [(600, 100), (900, 150), (1200, 200)]


def load_questions(path: Path) -> list[dict]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def search_within_budget(retriever: Retriever, question: str, k: int,
                         char_budget: int | None) -> list:
    """Top-k hits, truncated to a character budget. Always returns at least one.

    The confound this exists to remove: at a fixed k, a larger chunk size also means
    a larger CONTEXT. k=4 retrieves ~2280 chars at 600/100, ~3380 at 900/150 and
    ~4440 at 1200/200, so a chunking that "wins" may simply be feeding the model
    more text. Comparing recall at equal k is not comparing chunkings, it is
    comparing chunkings *and* context sizes at once.

    With a budget, every setting sees the same number of characters and the only
    thing that varies is how those characters are cut. One chunk is always kept,
    even if it alone exceeds the budget: returning nothing would score an
    impossible comparison, and the overshoot is reported instead of hidden.
    """
    hits = retriever.search(question, k=k)
    if not char_budget:
        return hits
    kept, used = [], 0
    for h in hits:
        n = len(h.chunk.text)
        if kept and used + n > char_budget:
            break
        kept.append(h)
        used += n
    return kept


def evaluate(retriever: Retriever, questions: list[dict], k: int,
             threshold: float, quotes: dict | None = None,
             char_budget: int | None = None) -> dict:
    """Score one setting.

    A HIT is: some retrieved chunk contains one of the gold quotes for this
    question. Chunk ids are NOT comparable across chunkings -- the same passage has
    a different id at 600/100 and 1200/200, and two 900-index gold ids do not exist
    in the 1200 index at all, which silently scored those questions as misses by
    construction. The quote is the evidence, so the quote decides the hit.

    `id_rank` is still computed, purely so the difference between the two
    definitions stays visible in the output.
    """
    rows = []
    for q in questions:
        hits = search_within_budget(retriever, q["question"], k, char_budget)
        got = [h.chunk.chunk_id for h in hits]
        chars = sum(len(h.chunk.text) for h in hits)
        gold = q["gold"]
        id_rank = next((i for i, cid in enumerate(got) if cid in gold), None)

        gq = (quotes or {}).get(q["qid"], {}).get("quotes", [])
        wanted = [x["quote"] for x in gq if x.get("quote")]
        rank = None
        if wanted:
            for i, h in enumerate(hits):
                if any(contains_quote(h.chunk.text, wq) for wq in wanted):
                    rank = i
                    break
        top = hits[0].score if hits else 0.0
        gated_in = top >= threshold
        rows.append({
            "qid": q["qid"], "type": q["type"], "gold": gold, "top": got[:k],
            "rank": rank, "id_rank": id_rank,
            # RAW, not rounded. `gated_in` below is computed from `top`, so storing
            # round(top, 3) made the artifact internally inconsistent: a row could
            # read `top_score: 15.86, gated_in: false` against a threshold of 15.86,
            # and any consumer recomputing the gate from the stored value got the
            # opposite answer (BUG-029). The value a decision used must be the value
            # recorded; `top_score_display` is the rounded form for tables.
            "top_score": top,
            "top_score_display": round(top, 3),
            "gated_in": gated_in, "chars": chars,
        })
    answerable = [r for r in rows if r["gold"]]
    # The no-gold pool is NOT homogeneous (same split as sweep()). `ambiguous` means
    # several defensible answers exist, so the gate admitting one is CORRECT
    # behaviour. Counting it as a false answer scored the system wrong for being
    # right, understated the rate by 75% (1/7 instead of 1/4), and contradicted
    # docs/P3_RETRIEVAL.md -- which had already made this exact correction while
    # this function was left behind. Keep all three counts.
    unanswerable = [r for r in rows if not r["gold"] and r["type"] != "ambiguous"]
    ambiguous = [r for r in rows if not r["gold"] and r["type"] == "ambiguous"]
    hit = [r for r in answerable if r["rank"] is not None]
    id_hit = [r for r in answerable if r["id_rank"] is not None]
    mrr = sum(1 / (r["rank"] + 1) for r in hit) / max(1, len(answerable))
    # false abstain: answerable question the gate would refuse
    fa = [r for r in answerable if not r["gated_in"]]
    # false answer: genuinely unanswerable question the gate would accept.
    # Ambiguous questions are reported separately and NEVER counted here.
    fb = [r for r in unanswerable if r["gated_in"]]
    amb_in = [r for r in ambiguous if r["gated_in"]]
    return {
        "k": k, "threshold": threshold, "rows": rows,
        "recall_at_k": len(hit) / max(1, len(answerable)),
        "recall_at_k_by_id": len(id_hit) / max(1, len(answerable)),
        "mrr": mrr,
        "false_abstain": len(fa) / max(1, len(answerable)),
        "false_answer": len(fb) / max(1, len(unanswerable)),
        "n_answerable": len(answerable), "n_unanswerable": len(unanswerable),
        # Reported, not scored: a high score on an ambiguous question is correct.
        "ambiguous_admitted": len(amb_in), "n_ambiguous": len(ambiguous),
        "char_budget": char_budget,
        "chars_per_answer_mean": (sum(r["chars"] for r in rows) / len(rows)
                                  if rows else 0.0),
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
        rows.append({"answerable": bool(q["gold"]), "score": top,
                     "type": q["type"], "qid": q["qid"]})

    ans = [r["score"] for r in rows if r["answerable"]]
    # The no-gold pool is NOT homogeneous and must not be reported as one number.
    #   ambiguous (T): several defensible answers exist. A high score is CORRECT.
    #   unanswerable (U): nothing in the corpus answers it. A high score is a fault.
    # Folding T into "false answers" scores correct behaviour as a retrieval error.
    amb = [r["score"] for r in rows if not r["answerable"] and r["type"] == "ambiguous"]
    una = [r["score"] for r in rows if not r["answerable"] and r["type"] != "ambiguous"]
    n_a, n_u, n_amb = len(ans), len(una), len(amb)

    # Candidate thresholds: every distinct score, so no operating point is missed.
    # Ambiguous scores are included as candidates because a threshold can fall
    # between them too; they just never count toward `total_errors`.
    cands = sorted({round(s, 6) for s in ans + una + amb})
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
        amb_in = sum(1 for s in amb if s >= t)  # ambiguous admitted (not an error)
        points.append({
            # Full precision on purpose. Rounding this to 3dp made two DIFFERENT
            # thresholds print as "15.86" while giving different counts (5 vs 6
            # answerable refused at the committed setting) -- an audit could not
            # tell which decision the row described. `exact` is the value the
            # comparison above actually used; `threshold` is for display only.
            "exact": t,
            "threshold": round(t, 3),
            "false_abstain": fa, "n_answerable": n_a,
            "false_abstain_frac": fa / n_a if n_a else 0.0,
            "false_answer": fb, "n_unanswerable": n_u,
            "false_answer_frac": fb / n_u if n_u else 0.0,
            "ambiguous_admitted": amb_in, "n_ambiguous": n_amb,
            "total_errors": fa + fb,
        })
    return {"points": points, "n_answerable": n_a, "n_unanswerable": n_u,
            "n_ambiguous": n_amb,
            "answerable_scores": sorted(round(x, 3) for x in ans),
            "unanswerable_scores": sorted(round(x, 3) for x in una),
            "ambiguous_scores": sorted(round(x, 3) for x in amb)}


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
    ap.add_argument("--char-budget", type=int, default=3600,
                    help="cap retrieved characters per question so settings are "
                         "compared at equal context size. Default 3600 = the "
                         "900/150 fixed-k mean, i.e. what the committed setting "
                         "already retrieves, so no setting is advantaged. Pass 0 "
                         "to use fixed k with no cap.")
    ap.add_argument("--gold-quotes", default="data/eval/gold_quotes.json",
                    help="quote-based evidence, comparable across chunkings")
    a = ap.parse_args(argv)

    cfg = load_config()
    k1 = cfg.get("retrieval.bm25_k1", 1.5)
    b = cfg.get("retrieval.bm25_b", 0.75)
    questions = load_questions(Path(a.questions))
    quotes = (json.loads(Path(a.gold_quotes).read_text(encoding="utf-8"))
              if Path(a.gold_quotes).is_file() else {})
    if not quotes:
        print(f"WARNING: no gold quotes at {a.gold_quotes}; falling back to id "
              f"matching, which is NOT comparable across settings", file=sys.stderr)

    results = []
    print(f"{'setting':>12} {'recall@'+str(a.k):>10} {'(by id)':>9} {'mrr':>6} "
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
        probe = evaluate(r, questions, a.k, 0.0, quotes)
        scores = sorted(x["top_score"] for x in probe["rows"]
                        if x["gold"] and x["top_score"] > 0)
        thr = scores[len(scores) // 4] if scores else 0.0
        res = evaluate(r, questions, a.k, thr, quotes)
        res.update(chunk_size=size, overlap=overlap, n_chunks=len(r.chunks))
        # Equal-character variant: same budget for every setting, so a difference
        # cannot be explained by context size.
        res["equal_budget"] = evaluate(r, questions, a.k, thr, quotes,
                                       char_budget=(a.char_budget or None))
        results.append(res)
        print(f"{s:>12} {res['recall_at_k']:>10.1%} {res['recall_at_k_by_id']:>9.1%} "
              f"{res['mrr']:>6.2f} {res['false_abstain']:>10.1%} "
              f"{res['false_answer']:>10.1%} {thr:>7.2f}")

    # --- equal-character comparison: the chunking effect with context held fixed
    if results and any(r.get("equal_budget") for r in results):
        budget = a.char_budget
        print(f"\nAt an EQUAL character budget ({budget} chars/question, k={a.k}):")
        print(f"{'setting':>10} {'recall':>8} {'mrr':>6} {'thresh':>7} "
              f"{'chars/ans (fixed k)':>20} {'chars/ans (budget)':>19}")
        print("-" * 76)
        for r in results:
            eb = r["equal_budget"]
            print(f"{r['chunk_size']:>4}/{r['overlap']:<5} "
                  f"{eb['recall_at_k']:>8.1%} {eb['mrr']:>6.2f} "
                  f"{eb['threshold']:>7.2f} "
                  f"{r['chars_per_answer_mean']:>20.0f} "
                  f"{eb['chars_per_answer_mean']:>19.0f}")
        print("\nrecall/mrr at fixed k confounds chunk size with context size; "
              "the budget columns\nshow what survives when every setting sees the "
              "same number of characters.")

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
              f"n_unanswerable={sw['n_unanswerable']}, "
              f"n_ambiguous={sw['n_ambiguous']}, k={a.k})")
        print("A=answerable (want admitted)  U=unanswerable (want refused)  "
              "T=ambiguous (not an error either way)")
        print(f"{'thresh':>8} {'A refused':>12} {'U admitted':>12} "
              f"{'T admitted':>12} {'errors':>7}")
        print("-" * 55)
        for p in sw["points"]:
            print(f"{p['threshold']:>8.2f} "
                  f"{p['false_abstain']:>5}/{p['n_answerable']:<6} "
                  f"{p['false_answer']:>5}/{p['n_unanswerable']:<6} "
                  f"{p['ambiguous_admitted']:>5}/{p['n_ambiguous']:<6} "
                  f"{p['total_errors']:>7}")
        best_pt = min(sw["points"], key=lambda p: p["total_errors"])
        print(f"\nlowest total errors at thresh={best_pt['threshold']}: "
              f"{best_pt['false_abstain']}/{best_pt['n_answerable']} answerable "
              f"refused, {best_pt['false_answer']}/{best_pt['n_unanswerable']} "
              f"unanswerable admitted, "
              f"{best_pt['ambiguous_admitted']}/{best_pt['n_ambiguous']} ambiguous "
              f"admitted (neither counted as an error)")
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
