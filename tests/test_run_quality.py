"""5b: run_quality grades only what the artifact can decide.

Run: /tmp/auditenv/bin/python -m pytest -q tests/test_run_quality.py

The failure mode this guards against is a script that produces a full PRD-shaped
table by guessing. `correct` and `partly` need a reader; if this script ever scores
them, the report gains a number nobody measured.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_quality import classify, summarise  # noqa: E402


def row(**kw):
    base = {"qid": "Q1", "type": "single", "terminal": "answered",
            "reason": "", "cites": 2, "gold_hit": True}
    base.update(kw)
    return base


# ---------------------------------------------------------------- the classes

def test_an_answerable_question_refused_is_wrongly_abstained():
    assert classify(row(terminal="no_evidence", cites=0, gold_hit=False)) == \
        "wrongly_abstained"
    assert classify(row(terminal="passages_only", cites=0, gold_hit=False)) == \
        "wrongly_abstained"


def test_an_unanswerable_question_refused_is_correctly_abstained():
    assert classify(row(type="unanswerable", terminal="no_evidence",
                        cites=0, gold_hit=None)) == "correctly_abstained"
    assert classify(row(type="unanswerable", terminal="passages_only",
                        cites=0, gold_hit=None)) == "correctly_abstained"


def test_answering_an_unanswerable_question_is_not_called_correct():
    """It is a WRONG answer by H3, but deciding that needs a reader."""
    assert classify(row(type="unanswerable", terminal="answered",
                        cites=1, gold_hit=None)) == "needs_judgement"


def test_an_answer_citing_no_gold_chunk_is_wrong():
    """Decidable: H2 requires every claim to cite the paper, and none of the gold
    evidence was cited."""
    assert classify(row(terminal="answered", gold_hit=False)) == "wrong"


def test_an_answer_citing_a_gold_chunk_is_NOT_scored_correct():
    """The central restraint: a gold citation is necessary, not sufficient."""
    assert classify(row(terminal="answered", gold_hit=True)) == "needs_judgement"


def test_abandonment_is_not_an_abstention():
    """Otherwise quality improves by having impatient users."""
    assert classify(row(terminal="abandoned", cites=0, gold_hit=None)) == "abandoned"
    res = summarise([row(terminal="abandoned")])
    assert "correctly_abstained" not in res["classes"]


def test_error_is_its_own_class():
    assert classify(row(terminal="error")) == "error"


# ---------------------------------------------------------------- the summary

def test_the_summary_never_invents_correct_or_partly():
    res = summarise([row(), row(gold_hit=False), row(type="unanswerable",
                                                    terminal="no_evidence", gold_hit=None)])
    assert "correct" not in res["classes"]
    assert "partly" not in res["classes"]
    assert "correct" in res["not_decided"] and "partly" in res["not_decided"]


def test_every_row_lands_in_exactly_one_class():
    rows = [row(), row(gold_hit=False), row(terminal="no_evidence"),
            row(type="unanswerable", terminal="no_evidence", gold_hit=None),
            row(terminal="abandoned"), row(terminal="error")]
    res = summarise(rows)
    assert sum(res["classes"].values()) == len(rows), res["classes"]


def test_zero_citation_answers_are_counted():
    res = summarise([row(cites=0), row(cites=3)])
    assert res["citations"]["answered_with_zero_citations"] == 1


# ---------------------------------------------------------------- cli

def test_cli_accepts_a_run_directory_and_writes_json(tmp_path):
    (tmp_path / "summary.json").write_text(json.dumps([row(), row(gold_hit=False)]))
    out = tmp_path / "quality.json"
    rc = subprocess.call([sys.executable, "-m", "scripts.run_quality",
                          str(tmp_path), "--json", "--out", str(out)],
                         cwd=Path(__file__).resolve().parents[1])
    assert rc == 0
    written = json.loads(out.read_text())
    assert written["n"] == 2
    assert "correct" not in written["classes"]


def test_cli_refuses_an_empty_summary(tmp_path):
    (tmp_path / "summary.json").write_text("[]")
    p = subprocess.run([sys.executable, "-m", "scripts.run_quality", str(tmp_path)],
                       cwd=Path(__file__).resolve().parents[1],
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert "empty" in (p.stdout + p.stderr).lower()


def test_abandonment_cannot_be_smuggled_into_the_abstain_set():
    """The `abandoned` check must be a GUARD, not a membership test.

    A mutation adding "abandoned" to ABSTAIN_TERMINALS passed every test, because
    `classify` checks `terminal == "abandoned"` before it ever consults the set --
    so the set could be widened harmlessly. That is fine, but it means the ORDER is
    the protection, and the order must be pinned: if the abandoned check were moved
    below the abstain check, every abandoned row would become a correct abstention
    and quality would rise with user impatience.
    """
    from scripts import run_quality

    res = run_quality.summarise([
        {"qid": "Q1", "type": "single", "terminal": "abandoned",
         "cites": 0, "gold_hit": None},
    ])
    assert res["classes"] == {"abandoned": 1}, res["classes"]
    # And the set itself must NOT contain it, so the intent is readable.
    assert "abandoned" not in run_quality.ABSTAIN_TERMINALS
    assert "abandoned" not in run_quality.ANSWER_TERMINALS


def test_an_outage_is_not_a_correct_abstention():
    """We abstained because WE failed, so the papers' silence was never established.

    `passages_only` on an unanswerable question reads as a correct abstention, but
    with `reason=upstream_error` it means the provider failed first. Banking that as
    correct would let an outage improve the quality table -- the same trap as
    counting abandonment as abstention.
    """
    for reason in ("upstream_error", "budget_gone", "breaker_open", "queue_full"):
        assert classify(row(type="unanswerable", terminal="passages_only",
                            reason=reason, cites=0, gold_hit=None)) == "infra_abstention"
        # And on an answerable question it must NOT be called wrongly abstained
        # either: we never got the chance to answer.
        assert classify(row(terminal="passages_only", reason=reason,
                            cites=0, gold_hit=False)) == "infra_abstention"


def test_a_genuine_no_evidence_abstention_is_still_correct():
    assert classify(row(type="unanswerable", terminal="no_evidence",
                        reason="model_not_found", cites=0,
                        gold_hit=None)) == "correctly_abstained"
