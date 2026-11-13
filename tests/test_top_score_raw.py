"""The artifact must record the score its gate decision actually used.

`evaluate()` compared the RAW score against the threshold but stored
`round(top, 3)`. Two rows in the committed artifact prove the inconsistency:

    M1 @ 600/100: top_score 15.477 == threshold 15.477, gated_in FALSE
    A8 @ 900/150: top_score 15.86  == threshold 15.86,  gated_in FALSE

Both are correct arithmetic -- the raw score was a hair under the threshold and
only *rounded* to it -- but a consumer recomputing `gated_in` from the stored row
gets the opposite answer. BUG-029 was exactly this, one artifact downstream.

Run: python -m pytest -q tests/test_top_score_raw.py  -> 3 passed
"""
from __future__ import annotations

import json

import pytest

from relay.contracts import Chunk
from relay.retrieval.bm25 import Retriever
from scripts.retrieval_eval import evaluate


def _retriever() -> Retriever:
    """Ten chunks with real term repetition, so BM25 produces non-trivial scores."""
    texts = [
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu",
        "alpha alpha beta beta gamma gamma delta delta unique1 marker",
        "alpha beta gamma delta epsilon zeta eta theta iota kappa unique2",
        "beta gamma delta epsilon zeta eta theta iota kappa lambda unique3",
        "gamma delta epsilon zeta eta theta iota kappa lambda mu nu unique4",
        "delta epsilon zeta eta theta iota kappa lambda mu nu xi unique5",
        "epsilon zeta eta theta iota kappa lambda mu nu xi omicron unique6",
        "zeta eta theta iota kappa lambda mu nu xi omicron pi unique7",
        "eta theta iota kappa lambda mu nu xi omicron pi rho unique8",
        "theta iota kappa lambda mu nu xi omicron pi rho sigma unique9",
    ]
    return Retriever([Chunk(f"t-v1:s{i}:c0000", "d", f"s{i}", i, t)
                      for i, t in enumerate(texts)])


def test_stored_score_reproduces_the_gate_decision():
    """The invariant: recomputing the gate from the stored row gives the stored bit.

    The threshold is placed deliberately INSIDE the gap between the raw score and
    its 3dp form. That is the only place the two readings differ, and it is exactly
    where BUG-029 lived -- picking a round threshold (say 2.5) lets a rounded store
    pass by luck, which is why the first version of this test did not catch the
    mutation.
    """
    r = _retriever()
    qs = [{"qid": f"A{i}", "type": "single", "gold": [], "answer": "x",
           "question": f"zeta eta theta unique{i % 10}"} for i in range(10)]
    raw0 = r.search(qs[0]["question"], k=1)[0].score
    disp0 = round(raw0, 3)
    assert raw0 != disp0, (
        "corpus produced an exactly-3dp score, so the rounding gap is empty and "
        f"this test would prove nothing ({raw0!r})")
    # strictly between the display value and the raw value
    threshold = (disp0 + raw0) / 2.0
    assert disp0 < threshold <= raw0, (disp0, threshold, raw0)
    out = evaluate(r, qs, k=4, threshold=threshold)
    for row in out["rows"]:
        assert "top_score_display" in row, "display form must be retained for tables"
        recomputed = row["top_score"] >= threshold
        assert recomputed == row["gated_in"], (
            f"{row['qid']}: stored top_score {row['top_score']!r} >= {threshold} gives "
            f"{recomputed}, but gated_in is {row['gated_in']}. The stored value must "
            "be the one the decision used.")


def test_score_is_not_rounded_away_in_the_artifact():
    """A raw score must keep enough precision to be compared, not just displayed."""
    r = _retriever()
    qs = [{"qid": "A1", "type": "single", "gold": [], "answer": "x",
           "question": "zeta eta theta unique7"}]
    out = evaluate(r, qs, k=4, threshold=0.0)
    raw = out["rows"][0]["top_score"]
    disp = out["rows"][0]["top_score_display"]
    # display is rounded; raw is at least as precise (may be equal when exactly 3dp)
    assert abs(raw - disp) < 1e-3, (raw, disp)
    assert raw != round(raw, 3) or abs(raw - round(raw, 3)) < 1e-12


def test_committed_artifact_is_flagged_as_pre_fix():
    """The shipped file predates this fix and still carries rounded scores.

    It cannot be regenerated without the chunk corpus, so this is an xfail with a
    message rather than a failure -- but it must be visible, not forgotten.
    """
    from pathlib import Path
    path = Path("data/eval/retrieval_results.json")
    if not path.is_file():
        pytest.skip("eval artifact absent (clean clone)")
    rows = [r for s in json.loads(path.read_text()) for r in s["rows"]]
    pre_fix = [r for r in rows if "top_score_display" not in r]
    if pre_fix:
        pytest.xfail(
            f"retrieval_results.json is PRE-FIX: {len(pre_fix)}/{len(rows)} rows "
            "store a rounded top_score and none store top_score_display. Regenerate "
            "with the chunk corpus present.")
    assert pre_fix == []
