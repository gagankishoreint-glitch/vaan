"""Regenerate the two `runs/*.json` files that no script produced.

`runs/h4_tokens.json` and `runs/naive_vs_managed.json` were committed as evidence
but nothing in `scripts/` wrote them, so they could not be checked or rebuilt -- an
orphan artefact that looks like a measurement. This script recreates both from live
code, using the same mechanisms the docs describe.

Neither run needs the network beyond the local stand-in, and neither costs a token.

    python -m scripts.regen_orphan_artifacts            # both
    python -m scripts.regen_orphan_artifacts --only h4  # one
    python -m scripts.regen_orphan_artifacts --dry-run  # print, write nothing

h4_tokens.json      10 identical calls at two patience settings; counts completed /
                    admitted / tokens debited by the stand-in's day bucket. The
                    debited figure is a STAND-IN ACCOUNTING property (it charges at
                    admission), NOT a Groq finding -- see docs/P7_ABANDON.md.
naive_vs_managed.json   one logical call that always 429s with retry-after: 5 s,
                    under each policy, isolated with httpx.MockTransport because a
                    live gateway refuses on local budget before the retry decision.
                    Current code is bounded, so both policies send few requests; the
                    historical 489-request RecursionError is pre-fix (docs/P8_LOAD.md).

Expected: `python -m pytest -q tests/test_regen_orphan_artifacts.py` -> 3 passed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import httpx

RUNS = Path("runs")


# ---------------------------------------------------------------- (1) H4 tokens

def h4_tokens(base_url: str, n: int = 10) -> dict:
    """Count what the stand-in debits for identical cancelled vs completed calls."""
    cfg = httpx.get(f"{base_url}/__stats", timeout=10).json()
    return cfg


async def _h4(base_url: str, patience: Optional[float], n: int) -> dict:
    """`n` trivial calls at one patience setting, against the local stand-in."""
    async with httpx.AsyncClient(base_url=f"{base_url}/openai/v1",
                                 timeout=30.0) as c:
        async with httpx.AsyncClient(timeout=30.0) as admin:
            await admin.post(f"{base_url}/__reset")
            before = (await admin.get(f"{base_url}/__stats")).json()
        completed = 0
        for _ in range(n):
            try:
                r = await asyncio.wait_for(
                    c.post("/chat/completions",
                           json={"model": "openai/gpt-oss-20b", "max_tokens": 200,
                                 "messages": [{"role": "user", "content": "ok"}]}),
                    timeout=patience if patience else None)
                if r.status_code == 200:
                    completed += 1
            except asyncio.TimeoutError:
                pass
        async with httpx.AsyncClient(timeout=30.0) as admin:
            after = (await admin.get(f"{base_url}/__stats")).json()
    return {"completed": completed,
            "admitted": after["calls"] - before["calls"],
            "day_tokens": after["day_used"] - before["day_used"]}


def make_h4(base_url: str, n: int) -> dict:
    return {"complete_run": asyncio.run(_h4(base_url, 5.0, n)),
            "cancelled_run": asyncio.run(_h4(base_url, 0.05, n))}


# ------------------------------------------------------ (2) naive vs managed

def _always_429() -> httpx.Response:
    return httpx.Response(429, headers={"retry-after": "5"},
                          json={"error": {"message": "rate limited"}})


async def _policy_http_calls(policy: str, deadline_s: float) -> dict:
    """HTTP calls one logical request makes under `policy`, against a 429 wall."""
    from relay.clock import RealClock
    from relay.config import load_config
    from relay.contracts import Attempt
    from relay.events import EventLog
    from relay.gateway.gateway import Gateway

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return _always_429()

    cfg = load_config()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        log = EventLog(td, run_id="regen", backend="standin")
        clock = RealClock()
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="https://x.test/openai/v1") as client:
            gw = Gateway.from_config(cfg, clock, log, base_url="https://x.test/openai/v1",
                                     api_key="k", client=client, policy=policy)
            scope = log.request("regen-1")
            outcome = "ok"
            t0 = clock.now()
            try:
                await gw.call(scope=scope, step="d", model="m",
                              messages=[{"role": "user", "content": "hi"}],
                              max_tokens=10, deadline_s=deadline_s)
            except Exception as e:                     # noqa: BLE001 -- recorded
                outcome = type(e).__name__
            wall = clock.now() - t0
        log.close()
    return {"policy": policy, "deadline_s": deadline_s, "http": calls["n"],
            "429s": calls["n"], "outcome": outcome, "wall_s": round(wall, 3)}


def make_naive() -> list:
    return [asyncio.run(_policy_http_calls("managed", 3.0)),
            asyncio.run(_policy_http_calls("naive", 3.0))]


# ---------------------------------------------------------------------- cli

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8009")
    ap.add_argument("--only", choices=["h4", "naive"], default=None)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if a.only in (None, "h4"):
        data = make_h4(a.base_url, a.n)
        print("h4_tokens.json ->", json.dumps(data))
        if not a.dry_run:
            (RUNS / "h4_tokens.json").write_text(json.dumps(data, indent=2) + "\n",
                                                 encoding="utf-8")
    if a.only in (None, "naive"):
        data = make_naive()
        print("naive_vs_managed.json ->", json.dumps(data))
        if not a.dry_run:
            (RUNS / "naive_vs_managed.json").write_text(json.dumps(data, indent=2) + "\n",
                                                        encoding="utf-8")
    if a.dry_run:
        print("\ndry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
