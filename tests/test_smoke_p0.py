"""Smoke test for the P0 loop: emit -> file -> checker -> verdict."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_smoke_run_round_trips_through_checker(tmp_path, monkeypatch):
    """Run the smoke script in a temp run dir and check the checker's verdict."""
    import scripts.smoke_p0 as smoke

    run_dir = tmp_path / "p0_smoke"
    monkeypatch.setattr(smoke, "RUN_DIR", run_dir)
    monkeypatch.setattr(smoke, "RUN_ID", "p0_smoke_test")
    assert smoke.main() == 0

    events = [json.loads(ln) for ln in (run_dir / "events.jsonl").read_text().splitlines()]
    assert any(e["type"] == "terminal" and e.get("reply_type") == "verified_answer" for e in events)
    assert any(e["type"] == "attempt.end" and e["outcome"] == "ok" for e in events)

    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_events.py"),
         str(run_dir / "events.jsonl"), "--json"],
        capture_output=True, text=True, cwd=ROOT,
    )
    report = json.loads(r.stdout)
    assert r.returncode == 1, "the deliberately broken request must be caught"
    got = {v["invariant"] for v in report["violations"]}
    assert "I1_one_terminal" in got
    assert "I2_no_attempt_after_terminal" in got
    # the healthy request must not be implicated
    assert {v["req_id"] for v in report["violations"]} == {"q-broken"}


def test_healthy_only_run_passes(tmp_path, monkeypatch):
    import scripts.smoke_p0 as smoke
    from relay.clock import FakeClock
    from relay.events import EventLog

    run_dir = tmp_path / "only_good"
    monkeypatch.setattr(smoke, "RUN_DIR", run_dir)
    log = EventLog(str(run_dir), run_id="r", backend="standin")
    try:
        smoke.healthy_request(log, FakeClock(start=0.0), "q-good")
    finally:
        log.close()
    log.flush()

    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_events.py"), str(log.path)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0, r.stdout
    assert "violations=0" in r.stdout


def test_minted_answer_recorded_is_sendable():
    """H1 end to end: only a mintable reply can appear with reply_type=verified_answer."""
    from relay.contracts import Citation, mint_verified, is_reply

    v = mint_verified("Scaled dot-product attention is ...",
                      (Citation("attn-v7:s3.2:c04", "Scaled Dot-Product Attention"),))
    assert is_reply(v)
    with pytest.raises(TypeError):
        type(v)(text="x", citations=())      # type: ignore[call-arg]
