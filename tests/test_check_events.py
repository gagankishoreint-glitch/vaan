"""The checker must FAIL on bad logs, not just pass on good ones.

Each test hand-builds a small events list, because a checker that only ever
sees EventLog output would be blind to exactly the bugs it exists to catch.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_events import check

ROOT = Path(__file__).resolve().parents[1]


def ok_request(req="q1", reply="verified_answer", **extra):
    """A healthy request: start, one attempt, end, one terminal."""
    return [
        {"type": "request.start", "req_id": req, "t_mono": 0.0},
        {"type": "attempt.start", "req_id": req, "t_mono": 0.1,
         "backend": "standin", "attempt_backend": "standin"},
        {"type": "attempt.end", "req_id": req, "t_mono": 0.5, "tokens_out": 12,
         "backend": "standin", "attempt_backend": "standin"},
        {"type": "request.end", "req_id": req, "t_mono": 0.6,
         "total_elapsed_s": 0.6, "waiting_s": 0.1, "working_s": 0.5, "retrying_s": 0.0},
        {"type": "terminal", "req_id": req, "terminal": reply, "t_mono": 0.7, **extra},
    ]


def test_healthy_log_passes():
    rep = check(ok_request())
    assert rep.ok, rep.violations
    assert rep.n_requests == 1


def test_missing_terminal_fails():
    rep = check(ok_request()[:-1])
    assert not rep.ok
    assert [v.invariant for v in rep.violations] == ["I1_one_terminal"]


def test_double_terminal_fails():
    evs = ok_request()
    evs.append({"type": "terminal", "req_id": "q1", "terminal": "no_evidence", "t_mono": 0.7})
    rep = check(evs)
    assert not rep.ok
    assert "I1_one_terminal" in {v.invariant for v in rep.violations}


def test_attempt_after_terminal_fails():
    evs = ok_request()
    evs.append({"type": "attempt.start", "req_id": "q1", "t_mono": 9.0})
    rep = check(evs)
    assert "I2_no_attempt_after_terminal" in {v.invariant for v in rep.violations}


def test_attempt_after_terminal_caught_by_order_without_timestamps():
    """A terminal with no t_mono must not blind the checker."""
    evs = [e for e in ok_request() if e["type"] != "attempt.end"]
    evs = [dict(e) for e in evs]
    for e in evs:
        if e["type"] == "terminal":
            e.pop("t_mono", None)
    evs.append({"type": "attempt.start", "req_id": "q1"})
    assert "I2_no_attempt_after_terminal" in {v.invariant for v in check(evs).violations}


def test_unpermitted_reply_fails():
    evs = ok_request(reply="guess")
    rep = check(evs)
    assert "I5_permitted_reply_only" in {v.invariant for v in rep.violations}


def test_negative_bucket_fails():
    evs = ok_request() + [
        {"type": "budget.update", "req_id": "q1", "bucket": "tpm",
         "t_mono": 0.3, "remaining_after": -1},
    ]
    rep = check(evs)
    assert "I3_no_negative_bucket" in {v.invariant for v in rep.violations}


def test_tokens_after_abandon_fail():
    evs = [
        {"type": "request.abandoned", "req_id": "q1", "t_mono": 0.2},
        {"type": "attempt.end", "req_id": "q1", "t_mono": 0.9, "tokens_out": 40},
        {"type": "terminal", "req_id": "q1", "terminal": "abandoned", "t_mono": 1.0},
    ]
    rep = check(evs)
    assert "I6_no_tokens_after_abandon" in {v.invariant for v in rep.violations}


def test_latency_sum_mismatch_fails_and_within_tolerance_passes():
    bad = ok_request()
    bad[3]["working_s"] = 0.2        # 0.1 + 0.2 != 0.6
    assert "I4_latency_sum" in {v.invariant for v in check(bad).violations}

    good = ok_request()
    good[3]["working_s"] = 0.5 + 0.01   # inside 0.05 tolerance
    assert check(good).ok


def test_retry_sleep_without_totals_fails():
    evs = [
        {"type": "retry.sleep", "req_id": "q1", "t_mono": 0.3, "sleep_s": 1.0},
        {"type": "terminal", "req_id": "q1", "terminal": "busy", "t_mono": 2.0},
    ]
    assert "I4_latency_sum" in {v.invariant for v in check(evs).violations}


def test_cli_exit_codes(tmp_path):
    good = tmp_path / "good.jsonl"
    good.write_text("\n".join(json.dumps(e) for e in ok_request()) + "\n")
    bad = tmp_path / "bad.jsonl"
    bad.write_text("\n".join(json.dumps(e) for e in ok_request()[:-1]) + "\n")

    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_events.py"), str(good)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "violations=0" in r.stdout

    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_events.py"), str(bad)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 1
    assert "I1_one_terminal" in r.stdout


def test_corrupt_json_line_raises(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"type": "ok"}\nnot json\n')
    from scripts.check_events import _load
    with pytest.raises(ValueError, match="corrupt JSON"):
        _load(p)


# ------------------------------------------------ I7 backend scope (BUG-005 / D-008)

def test_missing_attempt_backend_fails():
    evs = ok_request()
    evs[1]["attempt_backend"] = "standin"
    evs[1]["backend"] = "standin"
    del evs[1]["attempt_backend"]
    rep = check(evs)
    assert "I7_backend_scope" in {v.invariant for v in rep.violations}


def test_envelope_backend_swallowing_attempt_backend_fails():
    """The exact BUG-005 shape: envelope says standin, attempt says groq."""
    evs = ok_request()
    evs[1]["backend"] = "standin"
    evs[1]["attempt_backend"] = "groq"
    evs[2]["backend"] = "standin"
    evs[2]["attempt_backend"] = "groq"
    evs[4]["backend"] = "standin"
    rep = check(evs)
    assert "I7_backend_scope" in {v.invariant for v in rep.violations}


def test_matched_backends_pass():
    evs = ok_request()
    for e in evs:
        e["backend"] = "standin"
    evs[1]["attempt_backend"] = "standin"
    evs[2]["attempt_backend"] = "standin"
    assert check(evs).ok


def test_mixed_backends_within_request_are_allowed():
    """A request that fails over carries two attempt_backends; envelope stays `mixed`."""
    evs = [
        {"type": "request.start", "req_id": "q1", "t_mono": 0.0, "backend": "mixed"},
        {"type": "attempt.start", "req_id": "q1", "t_mono": 0.1,
         "backend": "mixed", "attempt_backend": "groq"},
        {"type": "attempt.end", "req_id": "q1", "t_mono": 0.2, "tokens_out": 3,
         "backend": "mixed", "attempt_backend": "groq"},
        {"type": "attempt.start", "req_id": "q1", "t_mono": 0.3,
         "backend": "mixed", "attempt_backend": "standin"},
        {"type": "attempt.end", "req_id": "q1", "t_mono": 0.4, "tokens_out": 5,
         "backend": "mixed", "attempt_backend": "standin"},
        {"type": "request.end", "req_id": "q1", "t_mono": 0.5, "total_elapsed_s": 0.5,
         "waiting_s": 0.1, "working_s": 0.4, "retrying_s": 0.0, "backend": "mixed"},
        {"type": "terminal", "req_id": "q1", "terminal": "answered", "t_mono": 0.5,
         "reply_type": "verified_answer", "backend": "mixed",
         "primary_backend": "groq"},
    ]
    rep = check(evs)
    assert "I7_backend_scope" not in {v.invariant for v in rep.violations}, rep.violations
    assert rep.ok, rep.violations


def test_missing_file_is_a_clean_error_not_a_traceback(tmp_path):
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_events.py"),
         str(tmp_path / "nope.jsonl")],
        capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 2
    assert "no such events file" in r.stderr
    assert "Traceback" not in r.stderr


def test_old_artifact_without_attempt_backend_is_flagged(tmp_path):
    """Backwards compatibility is not free: P0 artefacts predate I7 and must be
    reported, not silently accepted."""
    evs = ok_request()
    for e in evs:
        e.pop("attempt_backend", None)
    rep = check(evs)
    assert any(v.invariant == "I7_backend_scope" for v in rep.violations)
