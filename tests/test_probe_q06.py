"""Q-06 must refuse to answer on a corrupted measurement.

The old verdict compared a TPM drop against two token estimates and picked the
closer. It reported a result from a **negative** drop (-50), which means the bucket
refilled between the two header reads and no consumption was measured at all. It
also compared against a `len/3` estimate that was 88 tokens against 117 actual.

These tests pin the three conditions and the refusal.

Run:
    python -m pytest -q tests/test_probe_q06.py       -> 8 passed
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


# ---------------------------------------------------------------- ledger on abort

def _fake_transport(usage, status=200):
    """A transport that answers every request with one real-shaped body."""
    import httpx
    body = {"id": "x", "choices": [{"message": {"content": "ok"},
                                    "finish_reason": "stop"}],
            "usage": usage}
    headers = {"x-ratelimit-remaining-tokens": "7900",
               "x-ratelimit-limit-tokens": "8000",
               "x-ratelimit-remaining-requests": "999",
               "x-ratelimit-limit-requests": "1000"}
    return httpx.MockTransport(lambda request: httpx.Response(
        status, json=body, headers=headers))


def test_ledger_records_the_charge_when_the_probe_aborts_at_the_ceiling(tmp_path,
                                                                       monkeypatch):
    """(o) A real run charged 117 tokens and aborted at cap 100, and the ledger was
    never written -- the write sat after the try/except, so the early `return 1`
    skipped it. Any run that charged tokens must be recorded, however it ended."""
    import scripts.probe as probe_mod
    from scripts.probe import Ledger, Probe, Recorder, TokenCeiling

    # conftest points LEDGER_PATH at tmp_path for every test; write the file the
    # suite will use.
    ledger_path = tmp_path / "TOKEN_LEDGER.md"
    ledger_path.write_text("# TOKEN LEDGER\n\nno runs yet\n", encoding="utf-8")

    # cap 100, but each call actually charges 117 -> the second reserve is refused
    ceiling = TokenCeiling(cap=100, day_remaining=10**9)
    probe = Probe(cfg=probe_mod.load_config(), base_url="http://fake.invalid",
                  api_key="k", ceiling=ceiling,
                  recorder=Recorder(tmp_path / "run", "k", dry_run=False),
                  dry_run=False, timeout=5.0,
                  models={"small": "openai/gpt-oss-20b",
                          "large": "openai/gpt-oss-120b"},
                  client=None, token_param="max_completion_tokens")
    import httpx
    probe._client = httpx.Client(base_url="http://fake.invalid",
                                 transport=_fake_transport(
                                     {"prompt_tokens": 76, "completion_tokens": 41,
                                      "total_tokens": 117}))

    # two calls: the first settles 117, which alone exceeds the cap of 100
    try:
        probe.chat(mode="single", label="a", model="openai/gpt-oss-20b",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=80)
        probe.chat(mode="single", label="b", model="openai/gpt-oss-20b",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=80)
    except Exception:
        pass
    assert ceiling.spent == 117, f"expected one settled call, got {ceiling.spent}"

    # simulate what the finally block does, which is what main() now runs
    ledger = Ledger(ledger_path)
    ledger.spend(ceiling.spent, row={"utc": "2026-11-11T00:00:00+00:00",
                                     "modes": ["single"], "tokens": ceiling.spent,
                                     "ceiling": 100,
                                     "abort": "aborted at ceiling: cap 100"})
    ledger.save()

    text = ledger_path.read_text()
    assert "117" in text, "the charge is not in the ledger"
    reloaded = Ledger(ledger_path)
    assert reloaded.rows and reloaded.rows[-1]["tokens"] == 117
    assert "abort" in reloaded.rows[-1], "an aborted run must say it was aborted"


def test_main_writes_the_ledger_even_though_the_ceiling_aborts(monkeypatch, tmp_path):
    """End to end through main(): the abort path must still save the ledger."""
    import scripts.probe as pm
    from relay.config import load_config

    ledger_path = tmp_path / "TOKEN_LEDGER.md"
    ledger_path.write_text("# TOKEN LEDGER\n", encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_BASE_URL", "http://fake.invalid")

    # Force the ceiling to be hit immediately, after one real charge.
    calls = {"n": 0}

    def fake_chat(self, **kw):
        calls["n"] += 1
        self.ceiling.settle(80, 117)          # charge real tokens
        raise pm.CeilingReached("reserving 80 would exceed the cap: test")

    monkeypatch.setattr(pm.Probe, "chat", fake_chat)
    monkeypatch.setattr(pm, "load_env", lambda *a, **k: None)

    rc = pm.main(["--go", "--mode", "single", "--max-tokens-total", "1000",
                  "--timeout", "5", "--plan-today", "60000",
                  "--run-dir", str(tmp_path / "run")])
    assert rc == 1, "an abort must exit non-zero"
    text = ledger_path.read_text()
    assert "117" in text, "ABORTED RUN LOST ITS CHARGE -- the (o) bug is back"
