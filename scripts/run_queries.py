"""P6: run the eval set through the full pipeline and log events.

    python -m scripts.run_queries --base-url http://127.0.0.1:8009/openai/v1 \\
        --run-dir runs/p6_standin --limit 5

Real Groq is the same command with --base-url https://api.groq.com/openai/v1 and a
key in .env. Nothing else changes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

from relay.clock import RealClock
from relay.config import load_config
from relay.env import load_env
from relay.contracts import NoEvidence, PassagesOnly, VerifiedAnswer


def reply_type_of(reply) -> str:
    """Name the reply CLASS, not the terminal state. These are different axes:
    `terminal` says how the request ended, `reply_type` says what was sent."""
    if isinstance(reply, VerifiedAnswer):
        return "verified_answer"
    if isinstance(reply, NoEvidence):
        return "no_evidence"
    if isinstance(reply, PassagesOnly):
        return "passages_only"
    raise TypeError(f"not a permitted reply: {type(reply).__name__}")
from relay.events import EventLog
from relay.gateway.gateway import Gateway
from relay.pipeline.pipeline import Outcome_, Pipeline, send_reply
from relay.retrieval.bm25 import Retriever


async def main_async(a) -> int:
    cfg = load_config()
    clock = RealClock()
    log = EventLog(a.run_dir, run_id=Path(a.run_dir).name, backend=a.backend)
    questions = [json.loads(l) for l in
                 open(a.questions, encoding="utf-8") if l.strip()][: a.limit]
    r = Retriever.from_jsonl(a.chunks)
    # .env is loaded so a key placed there works for every entry point, not just
    # the probe. Default "standin" keeps the local path working with no key at all.
    load_env()
    key = os.environ.get("GROQ_API_KEY") or "standin"

    async with httpx.AsyncClient(base_url=a.base_url, timeout=60.0) as client:
        gw = Gateway.from_config(cfg, clock, log, base_url=a.base_url,
                                 api_key=key, client=client)
        rows = []
        for q in questions:
            scope = log.request(q["qid"])
            t0 = clock.now()
            scope.emit("request.start", question=q["question"][:200])
            pipe = Pipeline(cfg, r, gw, scope, patience_s=a.patience,
                            stream=a.stream)
            try:
                out = await pipe.answer(q["question"])
            except (httpx.HTTPError, OSError) as e:
                # A transport failure must still produce exactly one terminal event:
                # an exception escaping here would violate I1 and lose the request
                # from every report. Transport errors are the backend's problem, not
                # the user's, so the honest reply is still a reply.
                out = Outcome_(
                    send_reply(PassagesOnly(
                        "The model backend is unreachable; here are the closest "
                        "passages.", (), "breaker_open")),
                    "passages_only", f"transport:{type(e).__name__}")
            total = clock.now() - t0
            reply = out.reply
            n_cites = len(reply.citations) if isinstance(reply, VerifiedAnswer) else 0
            if reply is None:      # abandoned: nothing is sent, at all (H4)
                scope.finish(out.terminal, reply_type=None,
                             total_elapsed_s=round(total, 4), waiting_s=0.0,
                             working_s=round(total, 4), retrying_s=0.0)
            else:
                scope.finish(out.terminal, reply_type=reply_type_of(reply),
                             total_elapsed_s=round(total, 4), waiting_s=0.0,
                             working_s=round(total, 4), retrying_s=0.0)
            gold = set(q["gold"])
            cited = {c.chunk_id for c in reply.citations} if isinstance(
                reply, VerifiedAnswer) else set()
            rows.append({"qid": q["qid"], "type": q["type"], "terminal": out.terminal,
                         "reason": out.reason, "cites": n_cites,
                         "gold_hit": bool(gold & cited) if gold else None,
                         "total_s": round(total, 3)})
            print(f"  {q['qid']:<4} {out.terminal:<13} {out.reason[:40]:<40} "
                  f"{total:5.2f}s cites={n_cites}")
    log.end_run(n_requests=len(rows))
    log.close()

    answered = [r_ for r_ in rows if r_["terminal"] == "answered"]
    with_gold = [r_ for r_ in rows if r_["gold_hit"] is not None]
    print(f"\nanswered {len(answered)}/{len(rows)}  "
          f"gold_hit {sum(1 for x in with_gold if x['gold_hit'])}/{len(with_gold)}")
    Path(a.run_dir, "summary.json").write_text(json.dumps(rows, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8009/openai/v1")
    ap.add_argument("--backend", default="standin", choices=["standin", "groq", "mixed"])
    ap.add_argument("--run-dir", default="runs/p6_standin")
    ap.add_argument("--chunks", default="data/chunks/exp900/chunks.jsonl")
    ap.add_argument("--questions", default="data/eval/questions.jsonl")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--stream", action="store_true",
                    help="stream drafts so first_delta and model_ttft are observable")
    ap.add_argument("--patience", type=float, default=None,
                    help="seconds before the user abandons; expiry cancels the "
                         "draft and stops token spend (H4). Default from "
                         "user.patience_s, which is null until measured.")
    return asyncio.run(main_async(ap.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
