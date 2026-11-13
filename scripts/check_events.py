"""L6: check runtime invariants against a written events.jsonl.

The EventLog enforces "one terminal" and "no attempt after terminal" in-process.
This checker re-derives them from the file, which is the only source of truth
for the report (PRD s10). It is deliberately separate code: a bug in EventLog
must not be able to hide from it.

Invariants checked here (the ones decidable from events alone):
  I1  exactly one terminal event per request
  I2  no attempt.start/attempt.end after that request's terminal event
  I3  no bucket goes negative
  I4  waiting + working + retrying ~= total (using counted sleeps)
  I5  no reply emitted that is not a permitted reply type
  I6  no tokens consumed after abandon
  I7  backend scope: the DECLARED run backend must be in {groq, standin, mixed},
      every attempt must carry `attempt_backend`, and for a non-mixed declaration
      every attempt_backend must equal it (a `groq` run served by `standin` is a
      contradiction, not a label)
  I8  run.end: attempt_backend_counts sums to the number of attempts (lost events)ment

Usage:
    python scripts/check_events.py runs/<run>/events.jsonl [--json]
Exit code 0 = all invariants hold; 1 = violations (printed).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

TERMINAL_TYPES = {"terminal", "request.terminal", "req.terminal"}
PERMITTED_REPLIES = {"verified_answer", "no_evidence", "passages_only"}
#: D-006: deliberately RE-TYPED, not imported. This checker exists so that a bug in
#: the library cannot hide from it; importing the library's own set would make the
#: checker agree with the bug. The cost of duplication is drift, so
#: `tests/test_reasons.py` asserts these two literals are equal -- drift fails a
#: test instead of silently passing both files.
#:
#: `budget_gone` means a BUDGET was refused. `upstream_error` means the provider
#: failed or the deadline passed. Conflating them was BUG-042: a 500 storm reached
#: the user as a budget problem with the budget untouched.
_PERMITTED_REASONS = {
    "budget_gone", "upstream_error", "verify_failed", "breaker_open", "queue_full",
}
TOKEN_EVENTS = {"attempt.end", "usage"}
ATTEMPT_TYPES = {"attempt.start", "attempt.end"}


@dataclass
class Violation:
    invariant: str
    req_id: str | None
    detail: str


@dataclass
class Report:
    n_events: int = 0
    n_requests: int = 0
    violations: list[Violation] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_events": self.n_events,
            "n_requests": self.n_requests,
            "ok": self.ok,
            "declared_backend": None,
            "counts": self.counts,
            "violations": [v.__dict__ for v in self.violations],
        }


def _load(path: str | Path) -> list[dict]:
    events = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: corrupt JSON line: {e}") from e
    return events


def check(events: Iterable[dict], latency_tol_s: float = 0.05) -> Report:
    events = list(events)
    rep = Report(n_events=len(events))

    by_req: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        req = ev.get("req_id")
        if req is not None:
            by_req[req].append(ev)
    rep.n_requests = len(by_req)

    # The run's DECLARATION, taken from the envelope of the first event that has it.
    declared = next((ev.get("backend") for ev in events if ev.get("backend")), None)
    if declared is not None and declared not in ("groq", "standin", "mixed"):
        rep.violations.append(Violation(
            "I7_backend_scope", None,
            f"declared backend={declared!r} is not one of groq/standin/mixed"))

    # I8 run.end consistency
    run_ends = [e for e in events if e.get("type") == "run.end"]
    if len(run_ends) > 1:
        rep.violations.append(Violation(
            "I8_run_end", None, f"{len(run_ends)} run.end events, want at most 1"))
    for re_ in run_ends:
        counts = re_.get("attempt_backend_counts")
        if not isinstance(counts, dict):
            continue
        n_attempts = sum(1 for e in events if e.get("type") == "attempt.start")
        if sum(counts.values()) != n_attempts:
            rep.violations.append(Violation(
                "I8_run_end", None,
                f"attempt_backend_counts sums to {sum(counts.values())} but there "
                f"are {n_attempts} attempt.start events"))
        if declared in ("groq", "standin"):
            foreign = {k: v for k, v in counts.items() if k != declared}
            if foreign:
                rep.violations.append(Violation(
                    "I8_run_end", None,
                    f"run declared {declared!r} but attempts were served by {foreign}"))

    for req_id, evs in by_req.items():
        terminals = [e for e in evs if e.get("type") in TERMINAL_TYPES]

        # I1 exactly one terminal
        if len(terminals) != 1:
            rep.violations.append(Violation(
                "I1_one_terminal", req_id,
                f"found {len(terminals)} terminal events, want exactly 1"))

        # I2 nothing after terminal. File order is authoritative (append-only log);
        # t_mono is used only as a secondary signal, because a missing timestamp
        # must not make a violation invisible.
        if terminals:
            t_term = terminals[-1].get("t_mono")
            late_by_time = [
                e for e in evs
                if e.get("type") in ATTEMPT_TYPES
                and isinstance(e.get("t_mono"), (int, float))
                and isinstance(t_term, (int, float))
                and e["t_mono"] > t_term
            ]
            first_term_idx = min(evs.index(t) for t in terminals)
            late_by_order = [e for e in evs[first_term_idx + 1:]
                             if e.get("type") in ATTEMPT_TYPES]
            late = late_by_time or late_by_order
            if late:
                rep.violations.append(Violation(
                    "I2_no_attempt_after_terminal", req_id,
                    f"{len(late)} attempt event(s) after terminal"))

        # I5 reply type.
        #
        # `reply_type` is the CLASS of reply that was sent, and it is null exactly
        # when nothing was sent -- which is the only correct outcome for an
        # abandoned request (H4: the user has gone, so there is nobody to send to).
        # A null reply_type on any other terminal is a bug: it means a request
        # ended without a reply and without an abandonment to explain it.
        #
        # This used to fall back to the terminal name when reply_type was absent.
        # That fallback conflated the two axes (how it ended vs what was sent) and
        # turned every abandonment into a false H1 violation.
        for t in terminals:
            kind = t.get("reply_type")
            # `reply_type` absent entirely = older log; fall back so old logs still
            # check. An explicit null is different from absent and is validated.
            if "reply_type" not in t:
                kind = t.get("terminal")
            if kind is None:
                if t.get("terminal") != "abandoned":
                    rep.violations.append(Violation(
                        "I5_permitted_reply_only", req_id,
                        f"terminal={t.get('terminal')!r} sent nothing but was not "
                        f"abandoned; every other terminal must carry a reply"))
                continue
            if kind not in PERMITTED_REPLIES:
                rep.violations.append(Violation(
                    "I5_permitted_reply_only", req_id,
                    f"terminal reply_type={kind!r} is not one of {sorted(PERMITTED_REPLIES)}"))
            # The REASON is checked too, and only for the reply type that has one.
            # A passages_only with a misspelt or invented reason is a report row
            # that cannot be aggregated -- and before BUG-042 the set had no
            # `upstream_error` member, so a 5xx had to be logged as `budget_gone`.
            if kind == "passages_only":
                reason = t.get("reason")
                if reason is not None and reason not in _PERMITTED_REASONS:
                    rep.violations.append(Violation(
                        "I5_permitted_reply_only", req_id,
                        f"passages_only reason={reason!r} is not one of "
                        f"{sorted(_PERMITTED_REASONS)}"))

        # I6 no tokens after abandonment
        abandons = [e for e in evs if e.get("type") == "request.abandoned"]
        if abandons:
            t_ab = min(e.get("t_mono", 0.0) for e in abandons)
            after = [e for e in evs
                     if e.get("type") in TOKEN_EVENTS
                     and (e.get("tokens_out") or 0) > 0
                     and isinstance(e.get("t_mono"), (int, float))
                     and e["t_mono"] > t_ab]
            if after:
                rep.violations.append(Violation(
                    "I6_no_tokens_after_abandon", req_id,
                    f"{len(after)} token-consuming event(s) after abandon"))

        # I4 latency decomposition
        totals = [e for e in evs if e.get("type") == "request.end"]
        sleeps = [e for e in evs if e.get("type") == "retry.sleep"]
        for tot in totals:
            total = tot.get("total_elapsed_s")
            parts = tot.get("waiting_s"), tot.get("working_s"), tot.get("retrying_s")
            if total is None or any(p is None for p in parts):
                continue
            s = sum(parts)  # type: ignore[arg-type]
            if abs(s - total) > latency_tol_s:
                rep.violations.append(Violation(
                    "I4_latency_sum", req_id,
                    f"waiting+working+retrying={s:.4f}s vs total={total:.4f}s "
                    f"(tol {latency_tol_s}s)"))
        if sleeps and not totals:
            rep.violations.append(Violation(
                "I4_latency_sum", req_id, "retry sleeps recorded but no request.end totals"))

        # I7 backend scope. `declared` comes from the envelope (a construction-time
        # declaration), never from the attempts it describes -- a label computed
        # from the data cannot contradict the data.
        for e in evs:
            if e.get("type") not in ATTEMPT_TYPES:
                continue
            ab = e.get("attempt_backend")
            if ab is None and e.get("type") == "attempt.start":
                rep.violations.append(Violation(
                    "I7_backend_scope", req_id,
                    "attempt.start has no attempt_backend: per-attempt provenance lost"))
            elif ab is not None and declared in ("groq", "standin") and ab != declared:
                rep.violations.append(Violation(
                    "I7_backend_scope", req_id,
                    f"run declared backend={declared!r} but an attempt was served by "
                    f"{ab!r}: the declaration is false"))

    # I3 no negative bucket
    for ev in events:
        if ev.get("type") != "budget.update":
            continue
        after = ev.get("remaining_after")
        if isinstance(after, (int, float)) and after < 0:
            rep.violations.append(Violation(
                "I3_no_negative_bucket", ev.get("req_id"),
                f"bucket {ev.get('bucket')!r} remaining_after={after}"))

    rep.counts = dict(sorted(
        (k, sum(1 for e in events if e.get("type") == k)) for k in {e.get("type") for e in events}
    ))
    return rep


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check_events.py <events.jsonl> [--json]", file=sys.stderr)
        return 2
    if not Path(argv[1]).is_file():
        print(f"error: no such events file: {argv[1]}", file=sys.stderr)
        return 2
    events = _load(argv[1])
    rep = check(events)
    if "--json" in argv:
        print(json.dumps(rep.as_dict(), indent=2))
    else:
        print(f"events={rep.n_events} requests={rep.n_requests} violations={len(rep.violations)}")
        for v in rep.violations:
            print(f"  FAIL {v.invariant} req={v.req_id}: {v.detail}")
        print("event types:", rep.counts)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
