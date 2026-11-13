"""Probe used by run_all_standin.sh: assert a STREAMED failure wrote attempt.end.

Run: python scripts/_stream_error_probe.py http://127.0.0.1:8009/openai/v1

Succeeds only if the streamed path produced at least one `attempt.end` with outcome
`server_error`. A healthy stand-in yields `ok` and no failure evidence, and a run in
which nothing failed proves nothing -- so that case FAILS, deliberately. The first
version of the harness treated it as a pass.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import tempfile

import httpx

# Run as a SCRIPT (`python scripts/_stream_error_probe.py`), so the repo root is not
# on sys.path the way it is for `-m`. Without this the import fails and the harness
# reports a FAIL that is really a packaging mistake.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from relay.clock import RealClock  # noqa: E402
from relay.config import load_config
from relay.events import EventLog, RequestScope  # noqa: E402
from relay.gateway.gateway import Gateway  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8009/openai/v1"


async def go() -> int:
    cfg = load_config()
    log = EventLog(tempfile.mkdtemp(prefix="s500_"), run_id="s500", backend="standin")
    async with httpx.AsyncClient(base_url=BASE) as client:
        gw = Gateway.from_config(cfg, clock=RealClock(), log=log, base_url=BASE,
                                 api_key="x", client=client)
        gw.max_attempts = 3
        try:
            await gw.call(scope=RequestScope(log, "s"), step="draft", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=8, deadline_s=15.0, stream=True)
        except Exception:
            pass            # the failure is the point; the LOG is the evidence
        finally:
            log.close()
    evs = [json.loads(l) for l in open(pathlib.Path(log.path)) if l.strip()]
    ends = [e for e in evs if e["type"] == "attempt.end"]
    bad = [e for e in ends if e.get("outcome") == "server_error"]
    if not bad:
        print(f"FAIL: no server_error attempt.end; stand-in did not fail: {ends}")
        return 1
    print(json.dumps({"attempt_end": len(ends), "server_error": len(bad),
                      "statuses": sorted({e.get("status") for e in bad})}))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(go()))
