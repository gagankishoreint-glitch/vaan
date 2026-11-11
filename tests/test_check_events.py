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


# ------------------------------------------- I7/I8 backend declaration (D-011)

def _run(declared="standin", attempts=("standin",), with_run_end=True,
         run_end_counts=None):
    """Build a one-request run with a declared backend and given attempt backends."""
    evs = [{"type": "run.start", "backend": declared, "t_mono": 0.0}]
    evs += [{"type": "request.start", "req_id": "q1", "backend": declared, "t_mono": 0.01}]
    n = len(attempts)
    step = 0.5 / max(1, n)
    for i, ab in enumerate(attempts):
        t0 = 0.1 + i * step
        evs.append({"type": "attempt.start", "req_id": "q1", "t_mono": t0,
                    "backend": declared, "attempt_backend": ab})
        evs.append({"type": "attempt.end", "req_id": "q1", "t_mono": t0 + step / 2,
                    "backend": declared, "attempt_backend": ab, "tokens_out": 1})
    evs.append({"type": "request.end", "req_id": "q1", "t_mono": 0.9,
                "total_elapsed_s": 0.89, "waiting_s": 0.09, "working_s": 0.8,
                "retrying_s": 0.0, "backend": declared})
    evs.append({"type": "terminal", "req_id": "q1", "terminal": "answered",
                "t_mono": 0.95, "reply_type": "verified_answer", "backend": declared})
    if with_run_end:
        counts = run_end_counts if run_end_counts is not None else {
            b: attempts.count(b) for b in set(attempts)}
        evs.append({"type": "run.end", "backend": declared, "t_mono": 1.0,
                    "attempt_backend_counts": counts})
    return evs


def test_consistent_declared_run_passes():
    assert check(_run("standin", ("standin",))).ok


def test_declared_groq_served_by_standin_is_caught():
    """The contradiction a computed label could never detect: the run CLAIMS groq
    but every attempt was served by the stand-in."""
    rep = check(_run("groq", ("standin",)))
    assert "I7_backend_scope" in {v.invariant for v in rep.violations}
    assert "I8_run_end" in {v.invariant for v in rep.violations}


def test_declared_mixed_allows_any_attempt_backends():
    assert check(_run("mixed", ("groq", "standin"))).ok


def test_deliberate_failover_is_allowed_not_flagged_as_mixed_escape():
    """A failover inside a `standin` run is a real contradiction and must be
    flagged -- the old 'mixed escape hatch' computed from the attempts hid this."""
    rep = check(_run("standin", ("groq", "standin")))
    assert any(v.invariant == "I7_backend_scope" for v in rep.violations)


def test_invalid_declaration_is_caught():
    rep = check(_run("Groq", ("groq",)))
    assert any(v.invariant == "I7_backend_scope" for v in rep.violations)


def test_missing_attempt_backend_fails():
    evs = _run()
    del evs[2]["attempt_backend"]
    assert "I7_backend_scope" in {v.invariant for v in check(evs).violations}


def test_run_end_counts_mismatch_fails():
    """Lost attempt events show up as a count mismatch rather than silently."""
    rep = check(_run("standin", ("standin",), run_end_counts={"standin": 5}))
    assert "I8_run_end" in {v.invariant for v in rep.violations}


def test_double_run_end_fails():
    evs = _run()
    evs.append({"type": "run.end", "backend": "standin", "t_mono": 1.1,
                "attempt_backend_counts": {"standin": 1}})
    assert "I8_run_end" in {v.invariant for v in check(evs).violations}


def test_no_run_end_is_not_a_violation():
    """A crashed run has no run.end; that is reported elsewhere, not as a violation."""
    assert check(_run(with_run_end=False)).ok


# ------------------------------------------------ legacy P0 artefacts

def test_artifact_without_attempt_backend_is_flagged():
    evs = ok_request()
    for e in evs:
        e.pop("attempt_backend", None)
    assert "I7_backend_scope" in {v.invariant for v in check(evs).violations}
