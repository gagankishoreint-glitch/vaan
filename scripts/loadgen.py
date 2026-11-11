"""P8: open-loop load generator. Separate process, precomputed schedule.

Open loop = arrivals follow the schedule regardless of whether the system is
keeping up. That is the whole point: a closed loop (N workers looping) silently
slows down under overload and hides the very queueing it is meant to measure.

    python -m scripts.loadgen --shape steady --rps 2 --duration 20
    python -m scripts.loadgen --shape burst --rps 1 --burst 40
    python -m scripts.loadgen --shape overload --rps 30 --duration 20

Writes runs/loadgen_<shape>_<utc>/arrivals.jsonl with planned vs actual send time,
so send-time drift is measured and reported rather than assumed to be zero.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from relay.clock import RealClock


def schedule(shape: str, rps: float, duration: float, burst: int,
             seed: int) -> list[float]:
    """Precomputed arrival offsets in seconds. Deterministic for a given seed."""
    rng = random.Random(seed)
    t: list[float] = []
    if shape == "steady":
        n = int(rps * duration)
        t = [i / rps for i in range(n)]
    elif shape == "burst":
        t = [i / rps for i in range(int(rps * duration))]
        t += [duration for _ in range(burst)]
    elif shape == "overload":
        n = int(rps * duration)
        t = [i / rps for i in range(n)]
        rng.shuffle(t)
    else:
        raise ValueError(shape)
    return sorted(t)


async def run(args) -> int:
    offsets = schedule(args.shape, args.rps, args.duration, args.burst, args.seed)
    run_dir = Path(args.out) if args.out else Path(
        f"runs/loadgen_{args.shape}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    run_dir.mkdir(parents=True, exist_ok=True)
    clock = RealClock()
    t0 = clock.now()
    drift: list[float] = []
    results = []

    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout) as c:
        async def one(i: int, at: float) -> None:
            now = clock.now() - t0
            if at > now:
                await asyncio.sleep(at - now)
            sent = clock.now() - t0
            drift.append(sent - at)
            body = {"model": args.model, "max_tokens": args.max_tokens,
                    "messages": [{"role": "user", "content": args.prompt}]}
            t_sent = clock.now()
            try:
                r = await c.post("/chat/completions", json=body)
                status = r.status_code
            except httpx.HTTPError as e:
                status = f"error:{type(e).__name__}"
            results.append({"i": i, "planned": round(at, 4),
                            "sent": round(sent, 4), "status": status,
                            "elapsed": round(clock.now() - t_sent, 4)})

        await asyncio.gather(*(one(i, at) for i, at in enumerate(offsets)))

    results.sort(key=lambda r: r["i"])
    with open(run_dir / "arrivals.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    from collections import Counter
    counts = Counter(str(r["status"]) for r in results)
    drift_sorted = sorted(abs(d) for d in drift)
    p95 = drift_sorted[int(len(drift_sorted) * 0.95)] if drift_sorted else 0.0
    print(f"shape={args.shape} rps={args.rps} n={len(results)}")
    print(f"  statuses      {dict(counts)}")
    print(f"  drift p95     {p95:.3f}s  (planned vs actual send time)")
    print(f"  first 429 at  "
          f"{next((r['i'] for r in results if r['status'] == 429), 'none')}")
    print(f"  wrote         {run_dir}/arrivals.jsonl")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shape", choices=["steady", "burst", "overload"], default="steady")
    ap.add_argument("--rps", type=float, default=2.0)
    ap.add_argument("--duration", type=float, default=10.0)
    ap.add_argument("--burst", type=int, default=40)
    ap.add_argument("--base-url", default="http://127.0.0.1:8009/openai/v1")
    ap.add_argument("--model", default="openai/gpt-oss-20b")
    ap.add_argument("--max-tokens", type=int, default=8)
    ap.add_argument("--prompt", default="ok")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    return asyncio.run(run(ap.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
