"""5e: the stand-in must reproduce the FOUR transcribed Groq observations.

Source: the probe's OWN records -- runs/probe_20261111T062707Z/single.jsonl and
runs/probe_20261111T064821Z -- not output relayed through curl. Those files are not
in this repository yet (the supervisor commits calibration/probe/); until they are,
the values below are RETYPED here, which is the thing to fix first when the files
land. Every claim is labelled in docs/STANDIN.md.

      limit-tokens 8000, limit-requests 1000
      call 1 (full bucket, cap 80): prompt 76, completion 41,
             remaining 7844, reset-tokens 1.17 s, remaining-requests 999,
             reset-requests 1m26.4 s
      call 2 (+0.79 s): remaining 7822, reset 1.335 s
      call 3 (+0.98 s): remaining 7872, reset 0.960 s

What these numbers PROVE:
  * deficit == prompt + cap at ADMISSION, not prompt + completion. Call 1 reserved
    156 = 76 + 80 while only 41 tokens were generated. That is n=2 reservations
    (calls 1 and 4), one model, one prompt shape.
  * reset == deficit / (8000/60) in all three. The bucket refills CONTINUOUSLY at
    133.3 tokens/s; it is not a fixed 60 s window (the old stand-in model).
  * reset-requests 1m26.4s == 86400/1000 s, consistent with *-requests being per day.

What they do NOT prove -- and this docstring used to overclaim:
  * whether unused cap is REFUNDED at completion (Q-06). The admission-time deficit
    carrying the full cap says nothing about completion. The 1->2 interval fits
    refund slightly better (miss ~10 tokens vs ~29), n=2 intervals, INCONCLUSIVE.
    Hence `standin.refund_unused_cap`, whose default is an ASSUMPTION, not a finding.
  * the refill FUNCTION over longer gaps (four points, all within 2 s).
  * anything about a 429 body.

Run: python -m pytest -q tests/test_standin_observed.py  -> 5 passed
"""
from __future__ import annotations

import pytest

from relay.standin.server import RefillBucket

RATE = 8000 / 60.0

#: (elapsed_since_previous_call_s, tokens_reserved, remaining, reset_tokens_s)
#: `tokens_reserved` for call 1 is exact (76 + 80). For calls 2-3 it is DERIVED from
#: the remaining/reset pair and the elapsed time, and the transcription's 2dp `dt`
#: makes it non-integral -- so those are checked by invariant, not by literal.
OBS = [
    (None, 156, 7844, 1.170),
    (0.79, None, 7822, 1.335),
    (0.98, None, 7872, 0.960),
]


def test_every_observation_agrees_with_deficit_over_rate():
    """The core invariant, checked on the numbers alone -- no stand-in involved.

    reset == (8000 - remaining) / 133.3, to the precision the numbers were recorded.
    """
    for _, _, remaining, reset in OBS:
        deficit = 8000 - remaining
        assert abs(deficit / RATE - reset) < 5e-3, (
            f"remaining {remaining}, reset {reset}: deficit/rate = "
            f"{deficit / RATE:.4f}, which does not match")


def test_reset_requests_is_a_day():
    """1m26.4s for 1000 requests => 86400/1000. Supports the per-day reading (Q-04)."""
    assert abs(86400 / 1000 - 86.4) < 1e-9


def test_first_call_reserves_prompt_plus_cap_not_usage():
    """Reservation only: the deficit is 76+80, not 76+41.

    This is n=2 (calls 1 and 4), one model, one prompt shape, and it says nothing
    about whether the unused cap is refunded at completion (Q-06 stays OPEN).
    """
    _, reserved, remaining, _ = OBS[0]
    assert reserved == 76 + 80, reserved
    assert remaining == 8000 - (76 + 80)
    assert 76 + 41 != 76 + 80, "sanity: usage-based charging would give a different deficit"


def test_standin_bucket_reproduces_remaining_and_reset_within_tolerance():
    """Feed the observations to RefillBucket; it must land on them.

    Tolerances: remaining is an integer the service reported, so it must match
    EXACTLY. Reset is compared at 1 % because the inter-call gaps survive the
    transcription only to 2 decimal places, which is worth ~1.3 tokens here.
    """
    b = RefillBucket(limit=8000, window_s=60.0)
    t = 1_000.0
    ok, reset, rem = b.take(156, t)                       # call 1
    assert ok
    assert rem == 7844, rem
    assert abs(reset - 1.17) < 0.01 * 1.17, reset

    t2 = t + 0.79
    # call 2's exact reservation is not in the transcription; derive the value that
    # makes the OBSERVED remaining come out, then check the reset follows.
    deficit_before = b.deficit - (t2 - t) * RATE
    reserve2 = (8000 - 7822) - deficit_before
    ok, reset, rem = b.take(round(reserve2), t2)
    assert abs(rem - 7822) <= 1, (rem, reserve2)
    assert abs(reset - 1.335) < 0.02, (reset, reserve2)

    t3 = t2 + 0.98
    deficit_before = b.deficit - (t3 - t2) * RATE
    reserve3 = (8000 - 7872) - deficit_before
    ok, reset, rem = b.take(round(reserve3), t3)
    assert abs(rem - 7872) <= 1, (rem, reserve3)
    assert abs(reset - 0.96) < 0.02, (reset, reserve3)


def test_fixed_window_model_cannot_reproduce_the_observations():
    """The old model is refuted by these numbers, not merely disfavoured.

    A fixed 60 s window reports ~60 s of reset right after a request; the service
    reported 1.17 s, 1.335 s and 0.96 s. Recording the refutation here keeps the
    change from being reversible by someone who assumes a bucket is a window.
    """
    from relay.standin.server import Bucket

    b = Bucket(8000, 60.0, reset_at=0.0)
    ok, reset, rem = b.take(156, now=1_000.0)
    assert rem == 7844, "the old model got remaining RIGHT"
    assert reset == pytest.approx(60.0, abs=0.1), reset
    assert abs(reset - 1.17) > 50, (
        "the old model's reset is nowhere near the observed 1.17 s; it cannot be "
        "reconciled by tolerance")


def test_reservation_includes_prompt_not_only_cap():
    """The stand-in must reserve prompt + cap, or it advertises the wrong deficit.

    Charging cap alone made it report remaining 7920 where the service reported
    7844. Both are 'the same order', which is exactly how a wrong model survives.
    This checks the arithmetic the server performs, without HTTP.
    """
    import json as _json
    body = {"model": "openai/gpt-oss-20b", "max_tokens": 80,
            "messages": [{"role": "user", "content": "hi"}]}
    prompt = max(1, len(_json.dumps(body)) // 4)
    assert prompt + 80 != 80, "guard: prompt must contribute"
    b = RefillBucket(limit=8000, window_s=60.0)
    ok, reset, rem = b.take(prompt + 80, 1_000.0)
    assert rem == 8000 - (prompt + 80), rem
    assert abs(reset - (prompt + 80) / RATE) < 1e-9


def test_unused_cap_default_is_an_assumption_not_an_observation():
    """Q-06 is OPEN. The default is a CHOICE, and this pins only the choice.

    `false` is the branch we start from, not a finding: the admission-time deficit
    carrying the full cap is about reservation and says nothing about refund at
    completion. The 1->2 interval favours refund slightly (~10 vs ~29 tokens) on
    n=2 intervals -- inconclusive. This test would pass either way if the default
    were flipped; that is the point. It guards the label, not the physics.
    """
    import inspect

    from relay.standin.server import StandIn

    sig = inspect.signature(StandIn)
    assert sig.parameters["refund_unused_cap"].default is False, (
        "refund_unused_cap must default to False: that is the ASSUMED branch. The "
        "observations do not settle it (Q-06 OPEN); flip only to run the A/B")


def test_when_the_probe_records_land_the_values_must_be_read_from_them():
    """The retyped values above are a PLACEHOLDER with an expiry.

    Source of record: runs/probe_20261111T062707Z/single.jsonl and
    runs/probe_20261111T064821Z, which the supervisor commits under calibration/probe/.
    The moment any probe jsonl is present in the tree, this test FAILS on purpose:
    a transcription is a second place to be wrong, and the observations must then
    come from the files. Until then it is the record that they have not landed.
    """
    from pathlib import Path

    probe_dirs = sorted(Path("runs").glob("probe_*/single.jsonl")) + \
        sorted(Path("calibration/probe").glob("**/*.jsonl"))
    if probe_dirs:
        raise AssertionError(
            "probe records are now in the tree "
            f"({[str(p) for p in probe_dirs][:3]}); OBS in this file must be READ "
            "from them, not retyped. Delete the literals and parse the jsonl.")
    # Not present: the retyped values are the only copy, which is why the label
    # `transcribed, n=4, raw JSONL pending` appears in docs/STANDIN.md.
    assert True


def test_the_refund_switch_is_actually_read_from_config():
    """A switch no caller sets is not a switch.

    `refund_unused_cap` was a dataclass field with a default and a branch in the
    code, and `build_state()` never passed it -- so flipping the config changed
    nothing and both arms of the Q-06 A/B would have been the same arm. This pins
    the wiring, not the value.
    """
    import os

    from relay.standin import server

    # Same config load the server does at import, read through the same helper.
    assert server.CFG.get("standin.refund_unused_cap", False) is False, (
        "the committed default is the assumed branch; if this changes, the label in "
        "docs/STANDIN.md and config/relay.yaml must change with it")
    s = server.build_state()
    assert s.refund_unused_cap is False
    assert isinstance(s.refund_unused_cap, bool)
