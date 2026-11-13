"""5b: grade a finished run into the PRD's five outcome classes.

    python -m scripts.run_quality runs/p6_standin/summary.json
    python -m scripts.run_quality runs/p6_standin/ --json

PRD §11 asks for: correct / partly / wrong / correctly-abstained /
wrongly-abstained, plus citation valid y/n.

**What this script can and cannot decide is the whole design.** Of those six, exactly
two are decidable from the run artifact alone:

  * *wrongly abstained* -- the question was answerable and we sent nothing answerable.
    That is `gold_hit is False` on a question whose gold set is non-empty.
  * *correctly abstained* -- the question was unanswerable and we abstained (or
    returned passages rather than inventing an answer).

`correct` and `partly` are **not decidable here**: they need a human or a model
reading the answer against the reference, and a script that guessed would put a
fabricated quality number in the report. So they are reported as
`needs_judgement` with the candidate row attached, not silently scored.

This is the same rule the rest of the project follows: a number either comes from a
measurement or it is labelled as something else. A quality table where the grading
was done by a regex is worse than no table, because it looks like evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

#: Terminals that carry no answer. `abandoned` is the user leaving, not an abstention.
ABSTAIN_TERMINALS = frozenset({"no_evidence", "passages_only"})

#: Reasons that are OUR fault, not evidence about the papers.
#:
#: This distinction decides whether an abstention can be called correct. A
#: `passages_only` on an unanswerable question looks like a correct abstention, but if
#: the reason is `upstream_error` we abstained because the provider failed -- we never
#: established that the papers are silent. Scoring that as correct would let an outage
#: improve the quality table, which is the same trap as counting abandonment.
INFRA_REASONS = frozenset({"upstream_error", "budget_gone", "breaker_open", "queue_full"})

#: Terminals where the user got an answer (verified or not).
ANSWER_TERMINALS = frozenset({"answered"})


def load_summary(path: Path) -> list[dict]:
    """Accept either a summary.json or a run directory containing one."""
    if path.is_dir():
        path = path / "summary.json"
    if not path.is_file():
        raise SystemExit(f"no summary.json at {path}")
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise SystemExit(f"{path}: expected a list of per-question rows")
    return rows


def classify(row: dict) -> str:
    """One of the PRD classes, or `needs_judgement` where evidence is insufficient.

    The `type` field on a question says whether it is answerable:
      * `unanswerable` -- the papers do not say, so abstaining is CORRECT
      * anything else   -- there is a reference answer, so abstaining is WRONG
    """
    terminal = row.get("terminal")
    qtype = row.get("type")

    if terminal == "abandoned":
        # Not a quality outcome at all: the user left. Counting it as an abstention
        # would improve every quality metric by simply having impatient users.
        return "abandoned"
    if terminal == "error":
        return "error"

    abstained = terminal in ABSTAIN_TERMINALS

    if abstained and row.get("reason") in INFRA_REASONS:
        # We did not answer because WE failed, not because the evidence was absent.
        # Whether the abstention was right is therefore undecided -- and for an
        # unanswerable question it must not be banked as correct.
        return "infra_abstention"

    if qtype == "unanswerable":
        return "correctly_abstained" if abstained else "needs_judgement"

    # Answerable question.
    if abstained:
        return "wrongly_abstained"
    if terminal in ANSWER_TERMINALS:
        if row.get("gold_hit") is True:
            # We cited a gold chunk. That is necessary for "correct", not sufficient:
            # the prose could still be wrong. Correctness needs a reader.
            return "needs_judgement"
        if row.get("gold_hit") is False:
            # We answered, cited something, and cited none of the gold evidence.
            # That is the definition of a wrong answer this project can decide:
            # H2 says every claim cites the paper, and no gold chunk was cited.
            return "wrong"
        return "needs_judgement"
    return "needs_judgement"


def citation_stats(rows: list[dict]) -> dict:
    """Citation validity, as far as the artifact can tell.

    `gold_hit` is "cited at least one gold chunk". That is a weaker claim than
    "every citation resolves", and it is labelled as such: resolving every citation
    needs the chunk index, which is not in the summary.
    """
    with_gold = [r for r in rows if r.get("gold_hit") is not None]
    answered = [r for r in rows if r.get("terminal") in ANSWER_TERMINALS]
    return {
        "answered_rows": len(answered),
        "rows_with_a_gold_set": len(with_gold),
        "cited_a_gold_chunk": sum(1 for r in with_gold if r["gold_hit"] is True),
        "answered_with_zero_citations": sum(
            1 for r in answered if (r.get("cites") or 0) == 0),
        "note": "gold_hit is 'cited >=1 gold chunk', NOT 'every citation resolves'",
    }


def summarise(rows: list[dict]) -> dict:
    classes = [classify(r) for r in rows]
    counts = Counter(classes)
    by_type: dict[str, Counter] = defaultdict(Counter)
    for r, c in zip(rows, classes):
        by_type[r.get("type", "?")][c] += 1

    decided = [c for c in classes
               if c not in ("needs_judgement", "abandoned", "error",
                            "infra_abstention")]
    return {
        "n": len(rows),
        "classes": dict(counts),
        "by_question_type": {k: dict(v) for k, v in sorted(by_type.items())},
        "decided_here": len(decided),
        "needs_judgement": counts.get("needs_judgement", 0),
        "citations": citation_stats(rows),
        "not_decided": [
            "correct", "partly",
            "both need a reader comparing prose to the reference answer",
        ],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("summary", help="summary.json, or a run directory containing one")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--out", default=None, help="write the summary here")
    a = ap.parse_args(argv)

    rows = load_summary(Path(a.summary))
    if not rows:
        raise SystemExit("summary is empty; nothing to grade")

    res = summarise(rows)

    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2))

    if a.json:
        print(json.dumps(res, indent=2))
        return 0

    print(f"graded {res['n']} rows")
    for k, v in sorted(res["classes"].items()):
        print(f"  {k:<20} {v}")
    print(f"\ndecidable from the artifact : {res['decided_here']}")
    print(f"needs a reader              : {res['needs_judgement']}")
    print("\nby question type:")
    for qtype, counts in res["by_question_type"].items():
        line = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  {qtype:<14} {line}")
    c = res["citations"]
    print(f"\ncitations: {c['cited_a_gold_chunk']}/{c['rows_with_a_gold_set']} rows with "
          f"a gold set cited one; {c['answered_with_zero_citations']} answered rows "
          f"had no citation at all")
    print(f"  ({c['note']})")
    print("\nNOT decided here: correct, partly -- both need a reader. "
          "A script that guessed would put a fabricated quality number in the report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
