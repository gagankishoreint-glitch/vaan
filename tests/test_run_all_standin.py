"""5d: the harness must not report a scenario it did not exercise as a pass.

Run: /tmp/auditenv/bin/python -m pytest -q tests/test_run_all_standin.py

These are structural tests on the script, not a run of it (the run is done by hand and
its output is in runs/standin/index.txt). They guard the two ways a harness lies:
a SKIP counted as a pass, and a scenario that "passes" without exercising anything.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_all_standin.sh"


def test_the_script_exists_and_is_executable():
    assert SCRIPT.is_file(), "5d deliverable is scripts/run_all_standin.sh"
    assert SCRIPT.stat().st_mode & 0o111, "must be executable"


def test_it_parses():
    """`bash -n` — a syntax error in the harness would be found only at run time."""
    p = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_skipped_is_a_third_state_and_is_counted():
    s = SCRIPT.read_text()
    assert "SKIPPED" in s, "no SKIPPED state"
    assert "SKIPPED=$((SKIPPED+1))" in s, "skips are not counted"
    assert "A skip is not a pass" in s, "the output must say so out loud"


def test_strict_mode_fails_on_a_skip():
    s = SCRIPT.read_text()
    assert "--strict" in s
    assert "exit 3" in s, "strict mode must exit non-zero when anything was skipped"


def test_it_refuses_to_spend_real_tokens():
    s = SCRIPT.read_text()
    assert "unset GROQ_API_KEY" in s, (
        "a stray key could turn a stand-in pass into a paid run")
    assert "openai/v1" in s and "8009" in s


def test_it_records_the_assumptions_the_pass_ran_under():
    """Q-06 is OPEN: two runs differing only in refund_unused_cap must be tellable apart."""
    s = SCRIPT.read_text()
    assert "_assumptions.json" in s
    assert "__stats" in s


def test_the_streamed_error_scenario_requires_a_real_failure():
    """The first version of this script reported a PASS with outcomes ["ok"].

    A healthy stand-in produces no server_error, so the scenario must FAIL rather
    than pass -- otherwise the harness's green line means nothing.
    """
    probe = (ROOT / "scripts" / "_stream_error_probe.py").read_text()
    assert "server_error" in probe
    assert "stand-in did not fail" in probe
    s = SCRIPT.read_text()
    assert "error_rate" in s, "the scenario must inject a 5xx"
