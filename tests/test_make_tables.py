"""Tables must attribute every number, and must not launder a rounding artefact.

`docs/P3_RETRIEVAL.md` carried "5/20 refused" for a threshold whose stored rows say
6/20. Neither number was wrong arithmetic -- the sweep compared against a raw
candidate that *prints* as 15.86 while the committed threshold *is* 15.86, and the
rounding erased the difference. These tests hold both halves of that line.

Run: python -m pytest -q tests/test_make_tables.py  -> 4 passed
"""
from __future__ import annotations

import json

import pytest


def test_missing_artifact_is_printed_not_dropped(tmp_path, monkeypatch):
    """A clean clone has no `data/eval`. The table must show a hole, not skip it."""
    from scripts import make_tables

    monkeypatch.setattr(make_tables, "EVAL", tmp_path)
    text = make_tables.retrieval_table()
    assert make_tables.MISSING in text
    assert "retrieval_results.json" in text


def test_retrieval_table_reports_three_kinds_separately():
    """BUG-027: A/U/T must never be collapsed into one denominator."""
    from scripts import make_tables

    if not (make_tables.EVAL / "retrieval_results.json").is_file():
        pytest.skip("eval artifact absent (clean clone); run retrieval_eval")
    text = make_tables.retrieval_table()
    for col in ("A refused", "U admitted", "T admitted"):
        assert col in text


def test_sweep_records_full_precision_threshold():
    """The fix for the 5-vs-6 discrepancy: record the value actually compared.

    Asserts the CODE, not the committed artifact -- `retrieval_sweep.json` predates
    this fix and cannot be regenerated without the chunk corpus. The invariant that
    matters is that a future sweep cannot reproduce the ambiguity.
    """
    from scripts.retrieval_eval import sweep
    from tests.test_p4_p6 import bug027_corpus

    retriever, questions = bug027_corpus()
    out = sweep(retriever, questions, k=4, n_points=5)
    assert out["points"], "sweep produced no points"
    for p in out["points"]:
        assert "exact" in p, (
            "sweep rows must carry `exact`; without it two different thresholds "
            f"can both print as one value. Row: {p}")
        # `exact` is what the comparison used, so it must agree with the display
        assert abs(round(p["exact"], 3) - p["threshold"]) < 1e-9, (
            f"exact {p['exact']} does not round to displayed {p['threshold']}")


def test_ambiguous_never_counted_as_false_answer():
    """T admitted is reported, but it must not enter the false-answer numerator.

    This asserts the INVARIANT in live code, not the committed JSON. The committed
    `retrieval_results.json` still holds the pre-BUG-027 value (0.1429) because the
    chunk corpus is absent and the artifact cannot be regenerated; freezing the file
    here would pin a number already proven wrong. `--check` reports that divergence
    until the corpus is rebuilt.

    The corpus builder is shared with the BUG-027 test rather than re-derived, so
    there is one definition of "a corpus BM25 can actually rank".
    """
    from tests.test_p4_p6 import bug027_corpus
    from scripts.retrieval_eval import evaluate

    retriever, questions = bug027_corpus()
    out = evaluate(retriever, questions, k=4, threshold=0.0)  # admit everything
    assert out["n_unanswerable"] == 1, out
    assert out["n_ambiguous"] == 1, out
    assert out["false_answer"] == 1.0, (
        "with threshold 0.0 the single U is admitted, so the rate is 1.0. A value "
        "of 0.5 means the ambiguous question leaked into the denominator. Got "
        f"{out['false_answer']}")


def test_committed_sweep_artifact_is_flagged_as_stale():
    """The committed sweep lacks `exact` because it predates the fix.

    It cannot be regenerated without the chunk corpus, so it is not an error --
    but it must be visible, not forgotten. When the corpus is rebuilt and the
    artifact regenerated, this test flips to asserting the fix is present.
    """
    from scripts import make_tables

    path = make_tables.EVAL / "retrieval_sweep.json"
    if not path.is_file():
        pytest.skip("sweep artifact absent (clean clone)")
    sweep = json.loads(path.read_text())
    missing = [p["threshold"] for p in sweep["points"] if "exact" not in p]
    if missing:
        pytest.xfail(
            f"retrieval_sweep.json is PRE-FIX ({len(missing)}/{len(sweep['points'])} "
            "rows lack `exact`); regenerate with the chunk corpus present. The 5-vs-6 "
            "refusal discrepancy in docs/P3_RETRIEVAL.md is this staleness.")
    assert missing == []
