"""L6: read a run's event log and print the report tables. Zero tokens, no network.

The event log is the ONLY input. Nothing here calls a model, reads a clock, or
consults live state, so the same log always produces the same tables -- which is
what makes a number in the report traceable to a line in a file.

    python -m scripts.analyze runs/p6_clean
    python -m scripts.analyze runs/p6_clean --request A2

Tables:
    1. latency      TTFT and total at p50/p95/p99, with n for every row
    2. outcomes     terminals, failures, abandons
    3. tokens       tokens per answered request
    4. one request  waiting / working / retrying split, attempt by attempt
    5. invariants   the same checks scripts.check_events runs

Exit 0 = log is well formed, 1 = invariant violations found.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

TERMINALS = ("answered", "no_evidence", "passages_only", "busy", "abandoned", "error")
#: Re-typed from relay/contracts.PASSAGES_ONLY_REASONS, deliberately not imported
#: for the same reason as check_events (D-006). tests/test_reasons.py keeps them equal.
_PERMITTED_REASONS = {
    "budget_gone", "upstream_error", "verify_failed", "breaker_open", "queue_full",
}


# ---------------------------------------------------------------- loading

def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def pct(xs: list[float], p: float) -> float:
    """Nearest-rank percentile. Deliberately simple: no interpolation to explain."""
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


def table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


# ---------------------------------------------------------------- aggregates

def latency_rows(events: list[dict]) -> list[dict]:
    """Per attempt: TTFT and total. One row per completed attempt."""
    rows = []
    for e in events:
        if e["type"] != "attempt.end" or e.get("t_end") is None:
            continue
        ttft = (e["t_first_token"] - e["t_sent"]
                if e.get("t_first_token") is not None else None)
        rows.append({
            "req_id": e["req_id"], "attempt_id": e.get("attempt_id"),
            "step": e.get("step"), "outcome": e.get("outcome"),
            "status": e.get("status"),
            "ttft_s": ttft,
            "total_s": e["t_end"] - e["t_sent"],
            "tokens_in": e.get("tokens_in"), "tokens_out": e.get("tokens_out"),
        })
    return rows


def request_rows(events: list[dict]) -> list[dict]:
    ends = {e["req_id"]: e for e in events if e["type"] == "request.end"}
    terms = {e["req_id"]: e for e in events if e["type"] == "terminal"}
    abandons = {e["req_id"] for e in events if e["type"] == "request.abandoned"}
    out = []
    for rid, end in ends.items():
        term = terms.get(rid, {})
        out.append({
            "req_id": rid,
            "terminal": term.get("terminal"),
            "reply_type": term.get("reply_type"),
            "total_s": end.get("total_elapsed_s"),
            "waiting_s": end.get("waiting_s"),
            "working_s": end.get("working_s"),
            "retrying_s": end.get("retrying_s"),
            "abandoned": rid in abandons,
        })
    return out


# ---------------------------------------------------------------- invariants

def check(events: list[dict], tol: float = 0.05) -> list[str]:
    faults: list[str] = []
    by_req: dict[str, list[dict]] = {}
    for e in events:
        if "req_id" in e:
            by_req.setdefault(e["req_id"], []).append(e)
    for rid, evs in by_req.items():
        terms = [e for e in evs if e["type"] == "terminal"]
        if len(terms) != 1:
            faults.append(f"I1 {rid}: {len(terms)} terminal event(s), want exactly 1")
        elif evs[-1]["type"] != "terminal":
            faults.append(f"I2 {rid}: events after terminal ({evs[-1]['type']})")
        terr = terms[0].get("terminal") if terms else None
        if terr is not None and terr not in TERMINALS:
            faults.append(f"I3 {rid}: unknown terminal {terr!r}")
        rt = terms[0].get("reply_type") if terms else None
        if rt is not None and rt not in ("verified_answer", "no_evidence",
                                          "passages_only"):
            faults.append(f"I5 {rid}: terminal reply_type={rt!r} is not a permitted reply")
        # Same re-typed set as check_events (D-006); test_reasons keeps them equal.
        rs = terms[0].get("reason") if terms else None
        if rs is not None and rs not in _PERMITTED_REASONS:
            faults.append(f"I5 {rid}: passages_only reason={rs!r} is not permitted")
        ends = [e for e in evs if e["type"] == "request.end"]
        if not ends:
            faults.append(f"I6 {rid}: no request.end")
            continue
        end = ends[0]
        parts = sum(end.get(k) or 0.0 for k in ("waiting_s", "working_s", "retrying_s"))
        total = end.get("total_elapsed_s") or 0.0
        if abs(parts - total) > tol:
            faults.append(f"I7 {rid}: waiting+working+retrying={parts:.3f} != "
                          f"total={total:.3f} (tol {tol})")
    return faults


# ---------------------------------------------------------------- rendering

def render(events: list[dict], request: str | None) -> tuple[str, bool]:
    lines: list[str] = []
    meta = next((e for e in events if e.get("type") == "run.end"), {})
    backend = events[0].get("backend") if events else "?"
    lines.append(f"# run `{meta.get('run_id', events[0].get('run_id', '?'))}` "
                 f"· declared backend `{backend}`\n")

    att = latency_rows(events)
    reqs = request_rows(events)
    ok_att = [a for a in att if a["outcome"] == "ok"]
    answered = [r for r in reqs if r["terminal"] == "answered"]

    # -- 1 latency
    tot = [a["total_s"] for a in ok_att]
    rt = [r["total_s"] for r in reqs if r["total_s"] is not None]
    # TTFT is only real if the call streamed. Report it as unavailable otherwise,
    # because a TTFT that equals the total by construction is not a measurement.
    streamed = [a for a in ok_att if a.get("streamed")]
    tt = [a["ttft_s"] for a in streamed if a["ttft_s"] is not None]
    rows = [["attempt total", f"{len(tot)}", f"{pct(tot,50):.3f}", f"{pct(tot,95):.3f}",
             f"{pct(tot,99):.3f}"],
            ["request total", f"{len(rt)}", f"{pct(rt,50):.3f}", f"{pct(rt,95):.3f}",
             f"{pct(rt,99):.3f}"]]
    if tt:
        rows.insert(0, ["TTFT (streamed)", f"{len(tt)}", f"{pct(tt,50):.3f}",
                        f"{pct(tt,95):.3f}", f"{pct(tt,99):.3f}"])
    else:
        rows.insert(0, ["TTFT", "0", "—", "—", "—"])
    lines.append("## Latency (seconds)\n")
    lines.append(table(["level", "n", "p50", "p95", "p99"], rows))
    if not tt:
        lines.append(
            "\n> **TTFT is not measured.** All calls are non-streaming, so the first "
            "token is only observable when the whole response has arrived; a TTFT "
            "figure would equal the attempt total by construction and would be a "
            "fabricated measurement. Every latency figure in this report is "
            "time-to-complete-response. Streaming is the fix and is not built.\n")

    # -- 2 outcomes
    term_counts: dict[str, int] = {}
    for r in reqs:
        term_counts[str(r["terminal"])] = term_counts.get(str(r["terminal"]), 0) + 1
    failed_att = [a for a in att if a["outcome"] != "ok"]
    abandons = [e for e in events if e["type"] == "request.abandoned"]
    rows = [["requests", str(len(reqs))],
            ["terminals", ", ".join(f"`{k}` {v}" for k, v in sorted(term_counts.items()))],
            ["attempts", str(len(att))],
            ["failed attempts", f"{len(failed_att)}"
             + (f" ({', '.join(sorted({str(a['outcome']) for a in failed_att}))})"
                if failed_att else "")],
            ["abandons", f"{len(abandons)}"
             + (f" ({', '.join(str(e.get('reason')) for e in abandons)})"
                if abandons else "")]]
    lines.append("## Outcomes\n")
    lines.append(table(["measure", "value"], rows))
    lines.append("")

    # -- 3 tokens
    tin = [a["tokens_in"] for a in ok_att if a["tokens_in"] is not None]
    tout = [a["tokens_out"] for a in ok_att if a["tokens_out"] is not None]
    if tin or tout:
        lines.append("## Tokens per answered request\n")
        rows = [["prompt", f"{len(tin)}", f"{sum(tin)/len(tin):.0f}" if tin else "n/a",
                 f"{sum(tin)}" if tin else "n/a"],
                ["completion", f"{len(tout)}",
                 f"{sum(tout)/len(tout):.0f}" if tout else "n/a",
                 f"{sum(tout)}" if tout else "n/a"]]
        lines.append(table(["kind", "n", "mean", "total"], rows))
        lines.append("")
    else:
        lines.append("## Tokens per answered request\n\n"
                     "No usage recorded: this backend does not return token counts "
                     "in the shape the gateway reads. Report as unmeasured.\n")

    # -- 4 one request
    if request:
        lines.append(f"## Request `{request}`\n")
        mine = [e for e in events if e.get("req_id") == request]
        if not mine:
            lines.append(f"No events for `{request}`.\n")
        else:
            end = next((e for e in mine if e["type"] == "request.end"), {})
            parts = [("waiting", end.get("waiting_s")), ("working", end.get("working_s")),
                     ("retrying", end.get("retrying_s")),
                     ("total", end.get("total_elapsed_s"))]
            rows = [[f"`{k}`", "n/a" if v is None else f"{v:.4f}"] for k, v in parts]
            lines.append(table(["phase", "seconds"], rows))
            term = next((e for e in mine if e["type"] == "terminal"), {})
            lines.append(f"\nterminal `{term.get('terminal')}`, "
                         f"reply `{term.get('reply_type')}`\n")
            # One row per attempt, in send order; sleeps interleaved where they fell.
            steps = []
            ended = {e["attempt_id"]: e for e in mine if e["type"] == "attempt.end"}
            for e in mine:
                if e["type"] == "attempt.start":
                    end = ended.get(e.get("attempt_id"), {})
                    dur = ((end["t_end"] - end["t_sent"])
                           if end.get("t_end") and end.get("t_sent") else None)
                    steps.append([
                        f"`{e.get('attempt_id')}`", f"`{e.get('step')}`",
                        (f"`{end.get('outcome')}` status={end.get('status')}"
                         if end else "no end event"),
                        f"{dur:.4f}" if dur is not None else ""])
                elif e["type"] == "retry.sleep":
                    steps.append(["retry", "", f"sleep {e.get('sleep_s')}s "
                                  f"({e.get('why', e.get('policy'))})", ""])
            if steps:
                lines.append(table(["attempt", "step", "event", "duration_s"], steps))
            lines.append("")

    # -- 5 invariants
    faults = check(events)
    lines.append("## Invariants\n")
    if faults:
        lines.append(f"**{len(faults)} violation(s):**\n")
        lines += [f"- {f}" for f in faults]
    else:
        lines.append(f"OK: {len(reqs)} requests, one terminal each, no event after "
                     f"a terminal, every reply a permitted type, and every latency "
                     f"decomposition sums to its total.")
    lines.append("")
    return "\n".join(lines), not faults


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="directory containing events.jsonl")
    ap.add_argument("--request", default=None, help="request id for the phase split")
    ap.add_argument("--tol", type=float, default=0.05,
                    help="tolerance for the latency-sum invariant")
    ap.add_argument("--json", action="store_true", help="emit machine-readable summary")
    a = ap.parse_args(argv)

    path = Path(a.run_dir) / "events.jsonl"
    if not path.is_file():
        print(f"no event log at {path}", file=sys.stderr)
        return 2
    events = load(path)
    if not events:
        print(f"{path} is empty", file=sys.stderr)
        return 2

    if a.json:
        att = latency_rows(events)
        ok = [x for x in att if x["outcome"] == "ok"]
        reqs = request_rows(events)
        print(json.dumps({
            "run": events[0].get("run_id"),
            "backend": events[0].get("backend"),
            "requests": len(reqs),
            "terminals": {r["terminal"]: sum(1 for x in reqs if x["terminal"] == r["terminal"])
                          for r in reqs},
            "attempts_ok": len(ok),
            "ttft_p50": pct([x["ttft_s"] for x in ok if x["ttft_s"] is not None], 50),
            "total_p95": pct([r["total_s"] for r in reqs if r["total_s"] is not None], 95),
            "invariant_faults": check(events, a.tol),
        }, indent=2))
        return 0

    text, ok = render(events, a.request)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
