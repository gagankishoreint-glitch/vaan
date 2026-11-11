"""(b) What does a user actually receive when the local budget refuses the call?

The load harness measures the GATEWAY, so it never produces a user-facing reply.
This drives the PIPELINE, which is what a user talks to, and records the reply
class and token spend for every request -- including the ones refused locally.

    python -m scripts.pipeline_overload --n 40

Answer expected: PassagesOnly at 0 tokens, never an error, never a 429 surfaced.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

import httpx

from relay.clock import RealClock
from relay.config import load_config
from relay.contracts import NoEvidence, PassagesOnly, VerifiedAnswer
from relay.gateway.gateway import Gateway
from relay.pipeline.pipeline import Pipeline
from relay.retrieval.bm25 import Retriever

BASE = "http://127.0.0.1:8009/openai/v1"  # stand-in only


class _Scope:
    def __init__(self, rid):
        self.req_id = rid

    def emit(self, *a, **k):
        pass

    def abandon(self, *a, **k):
        pass

    def attempt_start(self, a):
        pass

    def attempt_end(self, a):
        pass


def kind_of(reply) -> str:
    if isinstance(reply, VerifiedAnswer):
        return "verified_answer"
    if isinstance(reply, PassagesOnly):
        return "passages_only"
    if isinstance(reply, NoEvidence):
        return "no_evidence"
    return "NOTHING_SENT"


async def main_async(a) -> int:
    cfg = load_config()
    r = Retriever.from_jsonl(a.chunks)
    qs = [json.loads(l) for l in open(a.questions) if l.strip()]
    # Answerable questions only, so any refusal is the budget and not the gate.
    qs = [q for q in qs if q["gold"]]

    async with httpx.AsyncClient(base_url=BASE, timeout=60.0) as c:
        await c.post("http://127.0.0.1:8009/__reset")
        gw = Gateway.from_config(cfg, RealClock(), None, base_url=BASE,
                                 api_key="x", client=c, policy="managed")
        rows = []
        for i in range(a.n):
            q = qs[i % len(qs)]
            scope = _Scope(f"u{i}")
            pipe = Pipeline(cfg, r, gw, scope, patience_s=None)
            before = gw.budget.tpm_used
            out = await pipe.answer(q["question"])
            spent = gw.budget.tpm_used - before
            rows.append({"i": i, "qid": q["qid"], "terminal": out.terminal,
                         "reply": kind_of(out.reply), "reason": out.reason,
                         "tokens_spent": spent,
                         "message": getattr(out.reply, "message", None),
                         "passages": len(getattr(out.reply, "passages", ()) or ())})

    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    by = Counter((x["reply"], x["reason"][:38], x["tokens_spent"] > 0) for x in rows)
    print(f"{a.n} user requests through the pipeline\n")
    print(f"{'n':>4}  {'spent?':<7} {'reply':<16} reason")
    print("-" * 74)
    for (k, reason, spent), n in sorted(by.items(), key=lambda kv: -kv[1]):
        print(f"{n:>4}  {'yes' if spent else 'NO':<7} {k:<16} {reason}")

    refused = [x for x in rows if x["reply"] != "verified_answer"]
    zero = [x for x in refused if x["tokens_spent"] == 0]
    print(f"\nrefused: {len(refused)}/{len(rows)}   of those at 0 tokens: "
          f"{len(zero)}/{len(refused)}")
    msgs = {x["message"] for x in zero if x["message"]}
    print(f"messages shown to a refused user ({len(msgs)} distinct):")
    for m in sorted(msgs):
        print(f"  {m!r}")
    bad = [x for x in rows if x["reply"] == "NOTHING_SENT"]
    print(f"\nrequests that received nothing at all: {len(bad)} "
          f"(must be 0; abandonment is the only legitimate case and is off here)")
    return 0 if not bad else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--base-url", default=BASE)
    ap.add_argument("--chunks", default="data/chunks/exp900/chunks.jsonl")
    ap.add_argument("--questions", default="data/eval/questions.jsonl")
    ap.add_argument("--out", default="runs/pipeline_overload/replies.json")
    return asyncio.run(main_async(ap.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
