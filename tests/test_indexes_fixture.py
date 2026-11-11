"""The fixture must fail loudly, never skip, when the corpus is absent.

This is the meta-test for tests/indexes.py: the helper that builds chunk indexes
could itself degrade into a skip, and then every test using it would silently test
nothing while the suite reported success. Pin the behaviour.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests import indexes


def test_missing_pdfs_fail_loudly_not_skip(monkeypatch, tmp_path):
    monkeypatch.setattr(indexes, "PDF_DIR", tmp_path)   # empty dir: no PDFs
    with pytest.raises(BaseException) as exc:
        indexes._require_pdfs()
    # pytest.fail raises Failed, which must NOT be a Skipped
    assert not isinstance(exc.value, pytest.skip.Exception), "it skipped"
    msg = str(exc.value)
    assert "PDFs missing" in msg
    assert "sha256sum -c SHA256SUMS" in msg, "must name the recovery command"
    assert "do NOT skip" in msg


def test_build_produces_the_documented_chunk_counts(tmp_path):
    """The 900/150 index this fixture builds must match what scripts.ingest
    documents (500 chunks), or the retrieval numbers cannot be reproduced."""
    rows = indexes._build(900, 150)
    assert len(rows) == 500, f"expected 500 chunks at 900/150, got {len(rows)}"
    assert {r["paper"] for r in rows} == {"attention", "moshi", "hnet"}


def test_build_ids_match_the_committed_gold_ids(tmp_path):
    """A gold id is only meaningful against the index it was verified on. If the
    fixture's ingest drifted, every gold id would be a miss."""
    import json
    rows = indexes._build(900, 150)
    ids = {r["chunk_id"] for r in rows}
    gold = [json.loads(l) for l in open("data/eval/questions.jsonl") if l.strip()]
    missing = [c for q in gold for c in q["gold"] if c not in ids]
    assert not missing, f"gold ids not produced by a fresh ingest: {missing[:5]}"


def test_write_index_creates_a_retrievable_file(tmp_path):
    from relay.retrieval.bm25 import Retriever
    path = indexes.write_index(tmp_path, 600, 100)
    assert Path(path).is_file()
    r = Retriever.from_jsonl(path)
    assert len(r.chunks) > 0
    assert r.search("attention", k=1), "empty search on a built index"
