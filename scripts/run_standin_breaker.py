"""Item H stand-in: drive the breaker through closed -> open -> half-open -> closed.

Run: /tmp/auditenv/bin/python scripts/run_standin_breaker.py

The stand-in runs with error_rate=1.0 so every attempt 500s, then with 0.0 so the
probe can succeed. Both phases are real HTTP against the stand-in; no Groq call is
made. `open_s` is 2 seconds so the half-open window is reachable in a test run
without faking the clock.

What this shows: the breaker opens after the configured failures, refuses traffic
while open, admits EXACTLY ONE probe when the window expires, and closes when that
probe succeeds. What it does NOT show: that the thresholds suit Groq. Both are
UNMEASURED and chosen only to be reachable here.
"""
import asyncio, json, os, signal, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from relay.clock import RealClock
from relay.config import load_config
from relay.events import EventLog
from relay.gateway.gateway import Breaker, BreakerOpen, Gateway

PORT = 8009
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAIL_THRESHOLD = 3
OPEN_S = 2.0


def start_standin(error_rate: float) -> subprocess.Popen:
    """Start the stand-in with standin.error_rate overridden.

    The stand-in reads its knobs from CONFIG ONLY -- it does not read an env var
    per knob -- so the override goes through RELAY_CONFIG and a temporary copy of
    config/relay.yaml. A first version of this script set STANDIN_ERROR_RATE and
    the stand-in silently ignored it, which would have produced a "breaker works"
    table in which the provider never failed.
    """
    cfg = load_config()
    raw = cfg.raw if hasattr(cfg, "raw") else None
    import yaml
    with open(os.path.join(ROOT, "config/relay.yaml"), encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    doc.setdefault("standin", {})["error_rate"] = float(error_rate)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    yaml.safe_dump(doc, tmp)
    tmp.close()

    env = dict(os.environ, RELAY_CONFIG=tmp.name)
    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "relay.standin.server:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(150):
        if p.poll() is not None:
            err = p.stderr.read().decode()[-500:]
            raise SystemExit(f"stand-in exited: {err}")
        try:
            # /__stats, not /health: the stand-in has no /health route, and a
            # readiness probe against a missing route would wait forever.
            httpx.get(f"http://127.0.0.1:{PORT}/__stats", timeout=0.25)
            return p
        except Exception:
            time.sleep(0.05)
    p.kill()
    raise SystemExit("stand-in did not start")


def stop(p):
    p.send_signal(signal.SIGTERM)
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()


async def call(gw, n=0):
    from relay.events import RequestScope
    scope = RequestScope(gw.log, f"brk-{n}")
    try:
        await gw.call(scope=scope, step="draft",
                      model=gw.cfg.get("models.small.id"),
                      messages=[{"role": "user", "content": "hi"}],
                      max_tokens=8, deadline_s=10.0)
        return "ok"
    except BreakerOpen:
        return "breaker_open"
    except Exception as e:
        return f"error:{type(e).__name__}: {e}"[:110]


async def main():
    cfg = load_config()
    log = EventLog(tempfile.mkdtemp(prefix="breaker_"), run_id="breaker",
                   backend="standin")
    breaker = Breaker(fail_threshold=FAIL_THRESHOLD, open_s=OPEN_S)

    # The gateway posts to a RELATIVE "/chat/completions" and relies on the
    # client's base_url. An AsyncClient without one fails every call with
    # UnsupportedProtocol -- which looks like an upstream failure but is a
    # configuration mistake in the caller.
    base = f"http://127.0.0.1:{PORT}/openai/v1"
    async with httpx.AsyncClient(base_url=base) as client:
        gw = Gateway.from_config(
            cfg, clock=RealClock(), log=log,
            base_url=base, api_key="standin", client=client)
        # Set on the instance, not via config: the config values are UNMEASURED and
        # a 10s window is not reachable in a test run.
        gw.breaker = breaker
        gw.max_attempts = 1        # one HTTP attempt per logical call, so the
                                   # failure count in the table is readable

        phase1 = []
        standin = start_standin(1.0)
        try:
            for i in range(6):
                outcome = await call(gw, i)
                phase1.append([i, outcome, breaker.state(time.monotonic())])
        finally:
            stop(standin)

        phase2 = []
        standin = start_standin(0.0)
        try:
            await asyncio.sleep(OPEN_S + 0.2)      # window expires -> half-open
            results = await asyncio.gather(*[call(gw, 100 + i) for i in range(6)])
            phase2.append(["concurrent_after_window", results,
                           breaker.state(time.monotonic())])
            after = [await call(gw, 200 + i) for i in range(3)]
            phase2.append(["after_probe", after, breaker.state(time.monotonic())])
        finally:
            stop(standin)

    phases = [{"phase": "error_rate=1.0", "calls": phase1},
              {"phase": "error_rate=0.0", "calls": phase2}]
    res = {"label": "UNCALIBRATED", "ran_in": "agent sandbox",
           "backend": "relay stand-in over real HTTP", "real_groq_calls": 0,
           "thresholds": {"fail_threshold": FAIL_THRESHOLD, "open_s": OPEN_S,
                          "note": "UNMEASURED - chosen to be reachable in a test run"},
           "phases": phases}
    with open(os.path.join(ROOT, "runs/standin/breaker_cycle.json"), "w") as f:
        json.dump(res, f, indent=2)
    for ph in phases:
        print(ph["phase"])
        for row in ph["calls"]:
            print("   ", row)


asyncio.run(main())
