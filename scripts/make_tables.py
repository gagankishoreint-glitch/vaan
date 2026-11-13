"""Generate the report's numerical tables from the committed artifacts.

Every number in the report should be traceable to a file. Today they are
transcribed by hand, which is how `12.5%` survived in two documents after the
denominator it came from was fixed. This script reads the artifacts and prints
markdown, so the tables in the report can be pasted rather than remembered.

The rule it enforces: **a table never renders a number it cannot attribute.**
Each figure is tagged

    [artifact]  read from a committed JSON
    [computed]  derived here from artifact rows
    [MISSING]   the artifact is not present -- printed, never silently dropped

so a table regenerated on a clean clone shows holes instead of false confidence.

    python -m scripts.make_tables                     # all tables
    python -m scripts.make_tables --table retrieval   # one
    python -m scripts.make_tables --check             # exit 1 if docs disagree

--check compares the numbers embedded in docs/ against the artifacts and fails
on a mismatch. It is deliberately strict about the false-answer rate, which is
the figure that has already been wrong twice.

Expected: `python -m pytest -q tests/test_make_tables.py` -> 4 passed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"
RUNS = ROOT / "runs"

MISSING = "**[MISSING]**"


# ------------------------------------------------------------------ loading

def _load(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def _pct(x: Optional[float]) -> str:
    return MISSING if x is None else f"{x * 100:.1f}%"


def _num(x: Optional[float], nd: int = 3) -> str:
    return MISSING if x is None else f"{x:.{nd}f}"


# ---------------------------------------------------------------- tables

def retrieval_table() -> str:
    """The false-answer table, with A/U/T kept separate (BUG-027).

    `n_unanswerable` excludes ambiguous questions; when the artifact predates the
    split, the numerator is all we have and the row says so.
    """
    results = _load(EVAL / "retrieval_results.json")
    header = ["chunk/overlap", "threshold", "A refused", "U admitted",
              "T admitted", "false answers", "source"]
    if results is None:
        return (_md_table(header, [[MISSING] * 7]) +
                "\n\n`data/eval/retrieval_results.json` is not present. Run "
                "`python -m scripts.retrieval_eval` with the chunk corpus built.")

    rows = []
    for s in results:
        scored = [r for r in s.get("rows", []) if r.get("gold")]
        refused = sum(1 for r in scored if not r.get("gated_in"))
        # recompute the split rather than trusting a stored summary
        unans = [r for r in s.get("rows", [])
                 if not r.get("gold") and r.get("type") != "ambiguous"]
        amb = [r for r in s.get("rows", [])
               if not r.get("gold") and r.get("type") == "ambiguous"]
        u_adm = sum(1 for r in unans if r.get("gated_in"))
        t_adm = sum(1 for r in amb if r.get("gated_in"))
        stored = s.get("false_answer")
        fresh = (u_adm / len(unans)) if unans else None
        agree = (fresh is None or stored is None
                 or abs(fresh - stored) < 1e-9)
        rows.append([
            f"{s.get('chunk_size')}/{s.get('overlap')}",
            _num(s.get("threshold")),
            f"{refused}/{len(scored)}",
            f"{u_adm}/{len(unans)}",
            f"{t_adm}/{len(amb)}",
            f"**{_pct(fresh)}**" + ("" if agree else " (recomputed)"),
            "artifact" if agree else "recomputed from rows",
        ])
    note = ("\n\n*Rows marked (recomputed) disagree with the stored `false_answer` "
            "field, which is how BUG-027 was found. Trust the recomputed column: "
            "the stored field was written by the buggy denominator.*")
    return _md_table(header, rows) + note


def sweep_table() -> str:
    sweep = _load(EVAL / "retrieval_sweep.json")
    header = ["setting", "threshold", "A", "U", "T", "recall@k", "false answers"]
    if sweep is None:
        return (_md_table(header, [[MISSING] * 7]) +
                "\n\n`data/eval/retrieval_sweep.json` is not present.")
    rows = []
    for name, block in (sweep.items() if isinstance(sweep, dict) else []):
        for pt in block.get("points", []):
            rows.append([
                str(name), _num(pt.get("threshold")),
                str(block.get("n_answerable", "?")),
                str(block.get("n_unanswerable", "?")),
                str(block.get("n_ambiguous", "?")),
                _pct(pt.get("recall_at_k")),
                _pct(pt.get("false_answer")),
            ])
    return _md_table(header, rows)


def h4_table() -> str:
    h4 = _load(RUNS / "h4_tokens.json")
    header = ["setting", "completed", "admitted", "day tokens debited"]
    if h4 is None:
        return (_md_table(header, [[MISSING] * 4]) +
                "\n\n`runs/h4_tokens.json` is not present; regenerate with "
                "`python -m scripts.regen_orphan_artifacts --only h4`.")
    rows = [[k.replace("_run", ""), str(v.get("completed", "?")),
             str(v.get("admitted", "?")), str(v.get("day_tokens", "?"))]
            for k, v in h4.items()]
    return (_md_table(header, rows) +
            "\n\n*The cancelled row shows the same tokens debited because the "
            "stand-in charges the day bucket at admission. This demonstrates the "
            "cancellation path, **not** provider billing.*")


def refusal_table() -> str:
    rows_in = _load(RUNS / "refusal_replies.json")
    header = ["n", "reply", "reason", "tokens spent"]
    if rows_in is None:
        return (_md_table(header, [[MISSING] * 4]) +
                "\n\n`runs/refusal_replies.json` is not present; regenerate with "
                "`python -m scripts.pipeline_overload --out runs/refusal_replies.json`.")
    from collections import Counter
    by = Counter((r.get("kind"), r.get("reason"), r.get("spent", 0) > 0)
                 for r in rows_in)
    rows = [[str(n), str(k), str(reason), "yes" if spent else "**NO**"]
            for (k, reason, spent), n in sorted(by.items(), key=lambda kv: -kv[1])]
    return _md_table(header, rows)


TABLES = {
    "retrieval": retrieval_table,
    "sweep": sweep_table,
    "h4": h4_table,
    "refusal": refusal_table,
}


# ------------------------------------------------------------ doc checking

def check_docs() -> list[str]:
    """Compare each `setting | ... | **N%**` row in the docs with the artifact.

    Parses the doc table row by row rather than scraping every percentage on the
    page: the page legitimately quotes several rates (one per operating point, plus
    historical values in prose), so "every percentage must equal every setting"
    is the wrong test and fails on correct text. What must hold is that the row for
    a given setting agrees with that setting.
    """
    import re

    results = _load(EVAL / "retrieval_results.json")
    if results is None:
        return ["retrieval artifact missing; cannot verify docs/P3_RETRIEVAL.md"]
    doc = ROOT / "docs" / "P3_RETRIEVAL.md"
    if not doc.is_file():
        return ["docs/P3_RETRIEVAL.md missing"]

    fresh: dict[str, float] = {}
    for s in results:
        unans = [r for r in s.get("rows", [])
                 if not r.get("gold") and r.get("type") != "ambiguous"]
        if unans:
            fresh[f"{s.get('chunk_size')}/{s.get('overlap')}"] = (
                100 * sum(1 for r in unans if r.get("gated_in")) / len(unans))

    problems: list[str] = []
    seen: set[str] = set()
    # Anchor on the false-answer table's own header, because several tables on this
    # page start with a `setting` column (recall, MRR, chars). Rows may be
    # blockquoted, hence the optional `>`.
    row = re.compile(
        r"^>?\s*\|\s*(\d+/\d+)\s*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|"
        r"\s*\*\*[^*]*?(\d+\.\d)%\*\*", re.M)
    for setting, quoted in row.findall(doc.read_text(encoding="utf-8")):
        if setting not in fresh:
            continue
        seen.add(setting)
        if abs(float(quoted) - fresh[setting]) > 0.05:
            problems.append(
                f"docs/P3_RETRIEVAL.md row {setting} quotes {quoted}% but the "
                f"artifact computes {fresh[setting]:.1f}%")
    for setting in fresh:
        if setting not in seen:
            problems.append(
                f"docs/P3_RETRIEVAL.md has no row for setting {setting} "
                f"(artifact computes {fresh[setting]:.1f}%)")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table", choices=sorted(TABLES) + ["all"], default="all")
    ap.add_argument("--check", action="store_true",
                    help="verify docs/ against the artifacts; exit 1 on mismatch")
    a = ap.parse_args(argv)

    if a.check:
        problems = check_docs()
        if problems:
            print("documentation disagrees with the artifacts:")
            for p in problems:
                print("  -", p)
            return 1
        print("docs agree with the artifacts")
        return 0

    names = sorted(TABLES) if a.table == "all" else [a.table]
    for i, name in enumerate(names):
        if i:
            print()
        print(f"### {name}\n")
        print(TABLES[name]())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
