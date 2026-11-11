"""Probe tests. No network: every test either dry-runs or uses httpx.MockTransport."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from relay.config import load_config
from scripts.probe import (
    CeilingReached,
    Ledger,
    Probe,
    Recorder,
    TokenCeiling,
    est_tokens,
    main,
    resolve_modes,
    scrub,
    truncate,
)

SECRET = "gsk_testkey_do_not_leak_0123456789"


def make_probe(tmp_path, handler, *, cap=100_000, day_remaining=10**6, dry_run=False,
               models=None):
    client = httpx.Client(transport=httpx.MockTransport(handler),
                          base_url="https://mock.local/openai/v1", timeout=5.0)
    rec = Recorder(tmp_path / "run", SECRET, dry_run)
    probe = Probe(
        cfg=load_config("config/relay.yaml"),
        base_url="https://mock.local/openai/v1",
        api_key=SECRET,
        ceiling=TokenCeiling(cap=cap, day_remaining=day_remaining),
        recorder=rec,
        dry_run=dry_run,
        timeout=5.0,
        models=models or {"small": "m-small", "large": "m-large"},
        sleeper=lambda s: None,
        client=client,
    )
    return probe


# --------------------------------------------------------------- dry run is inert

def test_dry_run_never_touches_the_network(tmp_path):
    calls = []

    def handler(request):                      # would raise if reached
        calls.append(request)
        raise AssertionError("network reached during dry run")

    probe = make_probe(tmp_path, handler, dry_run=True)
    for mode in ("models", "single", "stream", "reasoning", "bigctx", "cache",
                 "burst", "buckets", "rpd"):
        if mode == "models":
            probe.mode_models()
        elif mode == "single":
            probe.mode_single(2)
        elif mode == "stream":
            probe.mode_stream()
        elif mode == "reasoning":
            probe.mode_reasoning("reasoning_effort", ["low"])
        elif mode == "bigctx":
            probe.mode_bigctx(2)
        elif mode == "cache":
            probe.mode_cache()
        elif mode == "burst":
            probe.mode_burst(4, 3)
        elif mode == "buckets":
            probe.mode_buckets(4, 3)
        elif mode == "rpd":
            probe.mode_rpd(3, 30, 10)
    assert calls == []
    assert probe.ceiling.spent > 0, "dry run must still account for planned spend"
    assert probe.plan_lines, "dry run must print a plan"


def test_dry_run_refuses_when_plan_exceeds_cap(tmp_path):
    probe = make_probe(tmp_path, lambda r: None, cap=10, dry_run=True)
    r = probe.chat(mode="single", label="x", model="m", messages=[{"role": "user",
                   "content": "x" * 300}], max_tokens=100)
    assert r.refused and "cap" in r.reason
    assert probe.ceiling.spent == 0


# ----------------------------------------------------------------------- the ceiling

def test_ceiling_blocks_before_exceeding():
    c = TokenCeiling(cap=100, day_remaining=1000)
    c.reserve(60)
    with pytest.raises(CeilingReached):
        c.reserve(60)
    c.settle(60, 50)
    assert c.spent == 50
    with pytest.raises(CeilingReached):
        c.reserve(60)          # 50 + 60 > 100


def test_ceiling_respects_day_plan():
    c = TokenCeiling(cap=10_000, day_remaining=40)
    assert c.effective_cap == 40
    with pytest.raises(CeilingReached):
        c.reserve(50)


def test_ceiling_settles_actual_when_known():
    c = TokenCeiling(cap=1000, day_remaining=1000)
    c.reserve(100)
    assert c.settle(100, 12) == 12
    assert c.spent == 12


def test_ceiling_settles_estimate_when_usage_missing():
    c = TokenCeiling(cap=1000, day_remaining=1000)
    c.reserve(100)
    assert c.settle(100, None) == 100


def test_probe_aborts_on_ceiling_and_does_not_send(tmp_path):
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json={"usage": {"total_tokens": 5}})

    probe = make_probe(tmp_path, handler, cap=1)
    with pytest.raises(CeilingReached):
        probe.chat(mode="single", label="x", model="m",
                   messages=[{"role": "user", "content": "hello there"}], max_tokens=50)
    assert sent == [], "must refuse before sending, not after"


# ------------------------------------------------------------------------ no retries

def test_429_is_not_retried(tmp_path):
    n = []

    def handler(request):
        n.append(1)
        return httpx.Response(429, text='{"error":"rate limited"}',
                              headers={"retry-after": "2",
                                       "x-ratelimit-remaining-tokens": "0"})

    probe = make_probe(tmp_path, handler)
    r = probe.chat(mode="single", label="x", model="m",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=5)
    assert len(n) == 1, f"probe retried: {len(n)} requests"
    assert r.status == 429
    assert r.rl["retry_after_s"] == pytest.approx(2.0)


def test_5xx_is_not_retried(tmp_path):
    n = []

    def handler(request):
        n.append(1)
        return httpx.Response(500, text="boom")

    probe = make_probe(tmp_path, handler)
    r = probe.chat(mode="single", label="x", model="m",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=5)
    assert len(n) == 1 and r.status == 500


def test_timeout_is_recorded_not_retried(tmp_path):
    n = []

    def handler(request):
        n.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    probe = make_probe(tmp_path, handler)
    r = probe.chat(mode="single", label="x", model="m",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=5)
    assert len(n) == 1
    assert r.status is None and "ReadTimeout" in (r.error or "")


# ------------------------------------------------------------------- secrets & logging

def test_api_key_never_written_to_disk(tmp_path):
    def handler(request):
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        return httpx.Response(200, json={"usage": {"total_tokens": 3}},
                              headers={"x-ratelimit-remaining-tokens": "10"})

    probe = make_probe(tmp_path, handler)
    probe.chat(mode="single", label="x", model="m",
               messages=[{"role": "user", "content": "hi"}], max_tokens=5)
    probe.rec.raw("blob.txt", f"leak attempt {SECRET}")
    files = list((tmp_path / "run").rglob("*"))
    assert files
    for f in files:
        if f.is_file():
            assert SECRET not in f.read_text(errors="ignore"), f"key leaked into {f}"
    blob = (tmp_path / "run" / "raw" / "blob.txt").read_text()
    assert "<redacted>" in blob


def test_all_headers_are_logged_not_just_ratelimit(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"usage": {"total_tokens": 3}},
                              headers={"x-ratelimit-remaining-tokens": "10",
                                       "x-custom-trace": "abc123",
                                       "content-type": "application/json"})

    probe = make_probe(tmp_path, handler)
    r = probe.chat(mode="single", label="x", model="m",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=5)
    assert r.headers.get("x-custom-trace") == "abc123"
    rec = json.loads((tmp_path / "run" / "single.jsonl").read_text().splitlines()[0])
    assert rec["headers"]["x-custom-trace"] == "abc123"


def test_non_200_body_is_preserved_verbatim(tmp_path):
    body = '{"error":{"message":"max_tokens too large","code":"invalid"}}'

    def handler(request):
        return httpx.Response(400, text=body)

    probe = make_probe(tmp_path, handler)
    r = probe.chat(mode="bigctx", label="x", model="m",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=5)
    assert r.body == body


def test_huge_body_is_truncated(tmp_path):
    big = "x" * 200_000

    def handler(request):
        return httpx.Response(200, text=big, json=None) if False else \
            httpx.Response(200, content=big.encode())

    probe = make_probe(tmp_path, handler)
    r = probe.chat(mode="bigctx", label="x", model="m",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=5)
    assert len(r.body) < 200_000
    assert "truncated" in r.body


# ------------------------------------------------------------------------ sse parsing

def test_stream_ttft_gaps_and_usage(tmp_path):
    sse = (
        'data: {"choices":[{"delta":{"content":"1"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"2"}}]}\n\n'
        'data: {"choices":[],"usage":{"total_tokens":7,"prompt_tokens":2}}\n\n'
        'data: [DONE]\n\n'
    )

    def handler(request):
        return httpx.Response(200, text=sse, headers={"x-ratelimit-remaining-tokens": "5"})

    probe = make_probe(tmp_path, handler)
    r = probe.chat(mode="stream", label="x", model="m",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=10,
                   stream=True)
    assert r.status == 200
    assert r.t_first_token is not None and r.ttft_s is not None
    assert len(r.gaps) == 3, r.gaps          # 3 non-DONE data lines
    assert r.usage["total_tokens"] == 7
    assert any("[DONE]" in ln for ln in r.raw_lines)


def test_stream_records_unparseable_line_as_error(tmp_path):
    def handler(request):
        return httpx.Response(200, text='data: {not json}\n\ndata: [DONE]\n\n')

    probe = make_probe(tmp_path, handler)
    r = probe.chat(mode="stream", label="x", model="m",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=10,
                   stream=True)
    assert r.error == "unparseable SSE data line"


def test_stream_survives_midstream_disconnect(tmp_path):
    class Boom(httpx.SyncByteStream):
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
            raise httpx.ReadError("connection reset")

    def handler(request):
        return httpx.Response(200, stream=Boom())

    probe = make_probe(tmp_path, handler)
    r = probe.chat(mode="stream", label="x", model="m",
                   messages=[{"role": "user", "content": "hi"}], max_tokens=10,
                   stream=True)
    assert "ReadError" in (r.error or "")
    assert r.t_end is not None


# --------------------------------------------------------------------------- ledger

def test_ledger_roundtrip_and_plan(tmp_path):
    p = tmp_path / "TOKEN_LEDGER.md"
    p.write_text("# TOKEN LEDGER\n\nprose stays.\n")
    led = Ledger(p)
    day = led.today(plan=1000, cap=200_000)
    assert day.remaining == 1000
    led.spend(120, row={"utc": "t", "modes": ["single"], "tokens": 120})
    led.save()

    again = Ledger(p)
    day2 = again.today()
    assert day2.plan == 1000 and day2.spent == 120 and day2.remaining == 880
    assert again.rows[0]["tokens"] == 120
    text = p.read_text()
    assert "prose stays." in text, "human prose must survive the rewrite"
    assert text.count("LEDGER:DATA") == 2


def test_ledger_is_idempotent_on_repeated_save(tmp_path):
    p = tmp_path / "l.md"
    led = Ledger(p)
    led.today(plan=10)
    led.spend(3)
    led.save()
    first = p.read_text()
    led.save()
    assert p.read_text() == first


def test_ledger_survives_threads(tmp_path):
    import threading

    p = tmp_path / "l.md"
    led = Ledger(p)
    led.today(plan=10_000)

    def go():
        for _ in range(50):
            led.spend(2)

    ts = [threading.Thread(target=go) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert led.today().spent == 400


# ---------------------------------------------------------------------- cli guards

def test_go_without_ceiling_exits_2(capsys):
    assert main(["--go", "--timeout", "5"]) == 2
    assert "hard ceiling" in capsys.readouterr().err


def test_go_without_timeout_exits_2(capsys):
    assert main(["--go", "--max-tokens-total", "100"]) == 2
    assert "timeout" in capsys.readouterr().err


def test_go_without_key_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert main(["--go", "--max-tokens-total", "100", "--timeout", "5"]) == 2
    assert "GROQ_API_KEY" in capsys.readouterr().err


def test_dry_run_main_returns_0_and_prints_plan(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GROQ_BASE_URL", "https://example.invalid/openai/v1")
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    tmp_ledger = tmp_path / "ledger.md"
    monkeypatch.setattr("scripts.probe.LEDGER_PATH", tmp_ledger)
    rc = main(["--mode", "single", "--n-single", "2",
               "--run-dir", str(tmp_path / "run"), "--plan-today", "50000"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out and "single-0" in out
    assert SECRET not in out
    assert not tmp_ledger.exists(), "dry run must not write the ledger"


def test_mode_order_is_canonical_and_rpd_excluded():
    assert resolve_modes(None) == ["models", "single", "stream", "reasoning",
                                   "bigctx", "cache", "burst", "buckets"]
    assert resolve_modes(["rpd", "models"]) == ["models", "rpd"]
    assert resolve_modes(["all"]) == resolve_modes(None)
    assert "rpd" not in resolve_modes(["all"])


# ------------------------------------------------------------------------ helpers

@pytest.mark.parametrize("bad", ["nan", "inf", "-5", "1e5", "1m30", "Infinity", "-inf"])
def test_parse_duration_rejects_hostile_values(bad):
    from relay.ratelimit_headers import parse_duration
    assert parse_duration(bad) is None


def test_parse_duration_still_accepts_plain_seconds():
    from relay.ratelimit_headers import parse_duration
    assert parse_duration("2") == pytest.approx(2.0)
    assert parse_duration("0.5") == pytest.approx(0.5)


def test_scrub_and_truncate():
    assert scrub(f"a {SECRET} b", SECRET) == "a <redacted> b"
    assert scrub("nothing", None) == "nothing"
    assert truncate("abc", 10) == "abc"
    assert "truncated" in truncate("x" * 50, 10)


def test_est_tokens_overestimates_english():
    """The ceiling must over-estimate; 4 chars/token is the usual average."""
    text = "a" * 400
    assert est_tokens(text) >= 400 / 4
    assert est_tokens("") == 1
