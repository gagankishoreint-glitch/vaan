"""P8: managed vs naive under the SAME arrival schedule, against the stand-in.

This is the harm demonstration. Both policies run the same open-loop schedule
(same seed, same rps, same max_completion_tokens), and we count what each one does
to the provider and to the user.

    python -m scripts.load_compare --rps 40 --duration 6 --max-tokens 40 --seed 7

WHAT THIS IS NOT: a measurement of Groq. The stand-in is UNCALIBRATED -- its TTFT,
token rate and limits are provisional values announced at import. Every figure
this prints is a property of relay/standin/server.py, not of the service.

Reports, per policy:
  provider calls/s   HTTP requests actually sent (the load we impose)
  goodput            user requests that got a 200 (the useful work)
  p95 total          p95 of per-request wall time, including retries
  gave up            user requests that ended without a 200
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from relay.clock import RealClock
from relay.config import load_config
from relay.gateway.gateway import BreakerOpen, DeadlineExceeded, Gateway

BASE = "http://127.0.0.1:8009/openai/v1"


class _Scope:
    """Minimal scope: this harness measures the gateway, not the event log."""

    req_id = "load"

    def attempt_start(self, a):
        pass

    def attempt_end(self, a):
        pass

    def emit(self, *a, **k):
        pass


def p95(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, int(len(s) * 0.95))]


async def run_policy(policy: str, offsets: list[float], max_tokens: int,
                     deadline: float) -> dict:
    cfg = load_config()
    clock = RealClock()
    http_calls = {"n": 0}
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as c:

        real_post = c.post

        async def counted(*a, **kw):
            http_calls["n"] += 1
            return await real_post(*a, **kw)

        c.post = counted
        gw = Gateway.from_config(cfg, clock, None, base_url=BASE, api_key="x",
                                 client=c, policy=policy)
        t0 = clock.now()
        latencies: list[float] = []
        ok = gave_up = 0

        async def one(at: float):
            nonlocal ok, gave_up
            now = clock.now() - t0
            if at > now:
                await asyncio.sleep(at - now)
            t = clock.now()
            try:
                await gw.call(scope=_Scope(), step="draft",
                              model=cfg.get("models.small.id"),
                              messages=[{"role": "user", "content": "ok"}],
                              max_tokens=max_tokens, deadline_s=deadline)
                ok += 1
            except (DeadlineExceeded, BreakerOpen):
                gave_up += 1
            except Exception:
                gave_up += 1
            latencies.append(clock.now() - t)

        await asyncio.gather(*(one(at) for at in offsets))
        wall = clock.now() - t0

    n = len(offsets)
    return {
        "policy": policy,
        "users": n,
        "wall_s": round(wall, 2),
        "provider_calls": http_calls["n"],
        "provider_calls_per_s": round(http_calls["n"] / wall, 2) if wall else 0.0,
        "goodput": ok,
        "goodput_per_s": round(ok / wall, 2) if wall else 0.0,
        "gave_up": gave_up,
        "p95_total_s": round(p95(latencies), 3),
        "p50_total_s": round(statistics.median(latencies), 3) if latencies else 0.0,
        "amplification": round(http_calls["n"] / n, 2) if n else 0.0,
    }


async def async_main(a) -> int:
    # Same schedule for both policies: deterministic, independent of the outcome.
    offsets = [i / a.rps for i in range(int(a.rps * a.duration))]
    run_dir = Path(a.out) if a.out else Path(
        f"runs/load_compare_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    run_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for policy in ("managed", "naive"):
        async with httpx.AsyncClient() as c:
            await c.post("http://127.0.0.1:8009/__reset")
            before = (await c.get("http://127.0.0.1:8009/__stats")).json()
        row = await run_policy(policy, offsets, a.max_tokens, a.deadline)
        async with httpx.AsyncClient() as c:
            after = (await c.get("http://127.0.0.1:8009/__stats")).json()
        row["standin_before"] = before
        row["standin_after"] = after
        rows.append(row)

    hdr = (f"{'policy':>8} {'users':>6} {'calls/s':>8} {'goodput':>8} "
           f"{'good/s':>7} {'gave up':>8} {'p50':>7} {'p95':>7} {'amplif':>7}")
    print("UNCALIBRATED: every figure below is a property of the stand-in, not Groq.")
    print(f"schedule: {len(offsets)} arrivals at {a.rps} rps, seed {a.seed}, "
          f"max_completion_tokens={a.max_tokens}, deadline={a.deadline}s\n")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['policy']:>8} {r['users']:>6} {r['provider_calls_per_s']:>8.2f} "
              f"{r['goodput']:>8} {r['goodput_per_s']:>7.2f} {r['gave_up']:>8} "
              f"{r['p50_total_s']:>7.3f} {r['p95_total_s']:>7.3f} {r['amplification']:>7.2f}")

    (run_dir / "compare.json").write_text(json.dumps(
        {"calibrated": False, "standin": "provisional",
         "schedule": {"rps": a.rps, "duration": a.duration, "seed": a.seed,
                      "max_completion_tokens": a.max_tokens,
                      "deadline_s": a.deadline},
         "rows": rows}, indent=2), encoding="utf-8")
    print(f"\nwrote {run_dir}/compare.json")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rps", type=float, default=40.0)
    ap.add_argument("--duration", type=float, default=6.0)
    ap.add_argument("--max-tokens", type=int, default=40)
    ap.add_argument("--deadline", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    return asyncio.run(async_main(a))


if __name__ == "__main__":
    raise SystemExit(main())
