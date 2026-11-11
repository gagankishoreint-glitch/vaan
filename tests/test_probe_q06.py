"""Q-06 must refuse to answer on a corrupted measurement.

The old verdict compared a TPM drop against two token estimates and picked the
closer. It reported a result from a **negative** drop (-50), which means the bucket
refilled between the two header reads and no consumption was measured at all. It
also compared against a `len/3` estimate that was 88 tokens against 117 actual.

These tests pin the three conditions and the refusal.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.probe import Probe, Result


def _probe(token_param="max_completion_tokens"):
    p = Probe.__new__(Probe)                 # no network, no client, no config
    p.token_param = token_param
    p.dry_run = True
    p.notes = []
    p._prompt_overhead = 117
    return p


def _res(*, remaining, usage, t_sent, t_end, cap=300):
    return Result(mode="single", label="x", model="m", usage=usage,
                  rl={"remaining_tpm": remaining}, t_sent=t_sent, t_end=t_end,
                  max_tokens_sent=cap, token_param="max_completion_tokens")


def _run(probe, results):
    """Capture what _analyse_tpm_reserve notes instead of writing to disk."""
    captured = {}

    def note(q, line, artifact):
        captured[q] = line
    probe.note = note
    probe._analyse_tpm_reserve(results)
    return captured.get("Q-06", "")


def test_negative_drop_is_inconclusive_not_a_verdict():
    """The exact failure that invalidated the original answer."""
    p = _probe()
    a = _res(remaining=8000, usage={"total_tokens": 100, "prompt_tokens": 90,
                                   "completion_tokens": 10}, t_sent=1.0, t_end=2.0)
    b = _res(remaining=8050, usage={"total_tokens": 120, "prompt_tokens": 100,
                                   "completion_tokens": 20}, t_sent=2.1, t_end=3.0)
    line = _run(p, [a, b])
    assert "INCONCLUSIVE" in line, line
    assert "refill confound" in line, line
    assert "looks like" not in line, "must not emit a verdict"


def test_gap_over_one_second_is_inconclusive():
    p = _probe()
    a = _res(remaining=8000, usage={"total_tokens": 100, "prompt_tokens": 90,
                                   "completion_tokens": 10}, t_sent=1.0, t_end=2.0)
    b = _res(remaining=7600, usage={"total_tokens": 140, "prompt_tokens": 117,
                                    "completion_tokens": 23}, t_sent=9.0, t_end=10.0)
    line = _run(p, [a, b])
    assert "INCONCLUSIVE" in line and "read gap" in line, line


def test_missing_remaining_header_is_inconclusive_not_assumed():
    p = _probe()
    line = _run(p, [Result(mode="single", label="x", model="m"),
                    Result(mode="single", label="x", model="m")])
    assert "INCONCLUSIVE" in line, line


def test_positive_drop_within_gap_can_answer():
    """A clean measurement: drop 417 over a 0.05 s gap. Overhead 117 + cap 300 = 417
    exactly, so reservation is the closer candidate."""
    p = _probe()
    a = _res(remaining=8000, usage={"total_tokens": 100, "prompt_tokens": 117,
                                   "completion_tokens": 10}, t_sent=1.0, t_end=2.0)
    b = _res(remaining=7583, usage={"total_tokens": 140, "prompt_tokens": 117,
                                    "completion_tokens": 23}, t_sent=2.05, t_end=3.0)
    line = _run(p, [a, b])
    assert "ANSWERED" in line, line
    assert "cap-reserve" in line, line


def test_answer_uses_measured_overhead_not_the_len_div_3_estimate():
    p = _probe()
    p._prompt_overhead = None            # nothing measured -> must refuse
    a = _res(remaining=8000, usage={"total_tokens": 100}, t_sent=1.0, t_end=2.0)
    b = _res(remaining=7583, usage={"total_tokens": 140}, t_sent=2.05, t_end=3.0)
    line = _run(p, [a, b])
    assert "INCONCLUSIVE" in line and "overhead" in line, line


def test_token_param_is_recorded_on_every_result():
    """Q-06 must describe the same request shape the gateway sends."""
    from scripts.probe import Probe as P
    r = Result(mode="single", label="x", model="m", max_tokens_sent=300,
               token_param="max_completion_tokens")
    assert r.token_param == "max_completion_tokens"
    assert r.max_tokens_sent == 300
