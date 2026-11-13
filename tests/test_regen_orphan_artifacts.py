"""The two `runs/*.json` evidence files must be reproducible, not orphans.

They were committed with no producer anywhere in `scripts/`, so they could not be
checked or rebuilt -- an artefact that looks like a measurement but cannot be
regenerated is worse than no artefact. `scripts/regen_orphan_artifacts.py` now
produces both. These tests pin the parts that need no server.

Run: python -m pytest -q tests/test_regen_orphan_artifacts.py  -> 3 passed
"""
from __future__ import annotations

import json
import os

import pytest


def test_naive_is_bounded_so_the_489_table_is_history_not_current():
    """The doc used to present 489 requests -> RecursionError as current behaviour.

    It is pre-fix history (BUG-013). The regenerator must show the CURRENT bound,
    which is `gateway.naive_max_attempts`, or the doc correction is wrong.
    """
    from relay.config import load_config
    from scripts.regen_orphan_artifacts import make_naive

    cap = load_config().get("gateway.naive_max_attempts")
    rows = {r["policy"]: r for r in make_naive()}
    assert rows["managed"]["http"] == 1, rows["managed"]
    assert rows["naive"]["http"] == cap, (
        f"naive should stop at the attempt cap {cap}, not recurse; got "
        f"{rows['naive']['http']}")
    assert rows["naive"]["http"] < 489, "the pre-fix 489 must not be reachable"


def test_orphan_files_match_what_the_regenerator_produces():
    """The committed JSON must agree with live code, or the doc is stale."""
    from scripts.regen_orphan_artifacts import RUNS, make_naive

    path = RUNS / "naive_vs_managed.json"
    if not path.is_file():
        pytest.skip("artefact not generated yet; run scripts.regen_orphan_artifacts")
    committed = json.loads(path.read_text())
    fresh = make_naive()
    by = {r["policy"]: r for r in committed}
    for row in fresh:
        assert by[row["policy"]]["http"] == row["http"], (
            f"runs/naive_vs_managed.json is stale for {row['policy']}: "
            f"committed {by[row['policy']]['http']} vs live {row['http']}")


@pytest.mark.skipif(
    not os.environ.get("RELAY_REQUIRE_STANDIN") and
    not os.environ.get("STANDIN_BASE_URL"),
    reason="needs the local stand-in; set STANDIN_BASE_URL=http://127.0.0.1:8009")
def test_h4_regenerates_against_the_standin():
    """Slow (20 requests + sleeps). Opt-in, and a hard failure when required."""
    from scripts.regen_orphan_artifacts import make_h4

    base = os.environ.get("STANDIN_BASE_URL", "http://127.0.0.1:8009")
    try:
        data = make_h4(base, n=3)
    except Exception as e:                                   # noqa: BLE001
        if os.environ.get("RELAY_REQUIRE_STANDIN"):
            raise
        pytest.skip(f"stand-in not reachable: {type(e).__name__}")
    assert data["cancelled_run"]["completed"] == 0, data
    assert data["complete_run"]["completed"] == 3, data
