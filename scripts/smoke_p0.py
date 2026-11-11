"""P0 smoke: a run directory, a complete event log, and the checker on it.

This is not the pipeline -- there is no gateway yet (that is P5). It proves the
*contract* holds end to end: EventLog writes a log that scripts/check_events.py
can read and validate, and the checker catches a deliberately broken request.

    python -m scripts.smoke_p0
    python scripts/check_events.py runs/p0_smoke/events.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from relay.clock import FakeClock
from relay.config import load_config
from relay.contracts import Attempt, Citation, Outcome, Terminal, mint_verified
from relay.events import EventLog

RUN_DIR = Path("runs/p0_smoke")
RUN_ID = "p0_smoke"


def healthy_request(log: EventLog, clock: FakeClock, req_id: str) -> None:
    s = log.request(req_id)
    s.emit("request.start", question="What is scaled dot-product attention?")
    a = Attempt(f"{req_id}-a1", req_id, "draft", "standin",
                load_config().get("models.small.id"), t_sent=clock.now())
    s.attempt_start(a)
    clock.advance(0.25)
    a.t_first_token = clock.now()
    a.rl_headers_raw = {"x-ratelimit-remaining-tokens": "7938",
                        "x-ratelimit-reset-tokens": "7.66s"}
    a.status, a.outcome = 200, Outcome.OK
    a.tokens_in, a.tokens_out, a.tokens_cached = 512, 64, 0
    a.t_end = clock.now()
    s.attempt_end(a)
    s.finish(Terminal.ANSWERED, reply_type="verified_answer",
             total_elapsed_s=0.25, waiting_s=0.0, working_s=0.25, retrying_s=0.0)


def broken_request(log: EventLog, req_id: str) -> None:
    """Writes the two things the checker exists to catch, bypassing the scope guards.

    EventLog.request() would raise on both, so we emit raw. This is exactly the
    bug class a future layer could introduce by holding a stale scope.
    """
    log.emit("request.start", req_id=req_id)
    log.emit("terminal", req_id=req_id, terminal="passages_only",
             reply_type="passages_only")
    log.emit("attempt.start", req_id=req_id, attempt_id=f"{req_id}-late",
             attempt_backend="groq", backend="spoofed")   # envelope owns `backend`
    log.emit("terminal", req_id=req_id, terminal="busy", reply_type="busy")


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    log = EventLog(str(RUN_DIR), run_id=RUN_ID, backend="standin")
    clock = FakeClock(start=1000.0)
    try:
        healthy_request(log, clock, "q-happy")
        broken_request(log, "q-broken")
        log.emit("run.end", n_requests=2)
    finally:
        log.close()
        log.flush()

    events = [json.loads(ln) for ln in log.path.read_text().splitlines() if ln.strip()]
    print(f"wrote {len(events)} events to {log.path}")
    print("terminal events:", sum(1 for e in events if e["type"] == "terminal"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
