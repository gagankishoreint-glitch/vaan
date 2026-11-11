# DECISIONS

One scannable block per decision. Format: ID, date, phase, decision, why, what it rules out, re-open condition.
If a decision is reversed, do not edit it — add a new one that supersedes it.

---

### D-001 · 2026-11-11 · P0 · Event log contract
**Decision.** `runs/<run>/events.jsonl`, append-only, one JSON object per line, envelope
`{type, t_mono, t_wall, run_id, backend, req_id}` plus per-type fields. `t_mono` is the
only clock used for durations; `t_wall` is a human label.
**Why.** PRD s10 needs every report number derived from one file, and the invariant
checker must be able to run on a finished run with no live process.
**Rules out.** In-memory metrics as a source of truth, and per-request timings computed
from wall time (breaks under NTP adjustment).
**Re-open if.** JSONL size becomes a problem at P8 load (estimate: 2M lines/run, fine).

### D-002 · 2026-11-11 · P0 · Terminal event is last; `finish()` is the only exit
**Decision.** Order is `request.start -> … -> request.end -> terminal`. `request.end` carries
`total_elapsed_s`, `waiting_s`, `working_s`, `retrying_s`. `RequestScope.finish()` emits both
and is the only supported way to end a request; `terminal()` alone is for tests.
**Why.** The first draft of the smoke script emitted the latency totals after the terminal
(BUG-001). Making the correct order the only ergonomic path beats documenting it.
**Rules out.** Per-layer "log then decide" code that appends after the terminal.
**Re-open if.** Streaming needs partial output events after the reply is sent — then those
become `stream.*` events and `terminal` moves to a new `request.closed`.

### D-003 · 2026-11-11 · P0 · Config nulls fail loudly
**Decision.** `config/relay.yaml` is the only home for numbers. `null` means *not yet
measured*; `Config.require()` raises rather than defaulting, and `Config.get(k, default)`
must be used explicitly. A test forces every null to name its measuring phase on its own line.
**Why.** Rule 4 plus the PRD's "no magic numbers". A default is a silent guess.
**Rules out.** `os.environ.get("TIMEOUT", "30")` style fallbacks anywhere in `relay/`.
**Re-open if.** A number is genuinely unknowable and must be a bounded guess — then it is
recorded as a *range* plus the measurement that narrows it, not a bare default.

### D-004 · 2026-11-11 · P0 · `runs/` is git-ignored during development only
**Decision.** `.gitignore` excludes `runs/*/` with `!runs/.gitkeep`. Raw results are required
in the submission, so the deliverable archive is produced by `scripts/package_submission.sh`,
which forces `runs/` in with `git add -f`.
**Why.** Keeps experiment churn out of history without risking a missing deliverable.
**Rules out.** Committing every run directory as it is produced.
**Re-open before submission.** Verify the archive actually contains `runs/` — a git-ignored
directory is the single easiest thing to lose between "works" and "handed in".

### D-005 · 2026-11-11 · P0 · Paper PDFs kept out of git, hashes kept in
**Decision.** `data/papers/*.pdf` is ignored; `data/papers/SHA256SUMS` is committed.
**Why.** ~8 MB of binaries that cannot be diffed, but reproducibility requires proving which
bytes were ingested.
**Verification.** All three stamps confirmed on page 1: `arXiv:1706.03762v7 [cs.CL] 2 Aug 2023`,
`arXiv:2410.00037v1 [eess.AS] 17 Sep 2024`, `arXiv:2507.07955v2 [cs.LG] 15 Jul 2025`.
**Re-open if.** The submission channel cannot carry 8 MB of PDFs (then they move to LFS).

### D-006 · 2026-11-11 · P0 · In-process guards are asserts, not the enforcement
**Decision.** `EventLog`/`RequestScope` raise on double-terminal and on events after terminal
so bugs surface in development. `scripts/check_events.py` re-derives every invariant from the
written file and is the authority for the report.
**Why.** Belt and braces, deliberately duplicated: the checker is written against the file
format, so a bug in `EventLog` cannot hide from it (BUG-001 and BUG-002 were both ordering/
shutdown bugs that the live guards caught; the checker catches the ones they cannot).
**Rules out.** Trusting a single code path to both produce and validate the evidence.
**Re-open if.** The checker and the guards ever disagree on a real run — the checker wins.

### D-007 · 2026-11-11 · P0 · Groq header semantics are UNVERIFIED until P1
**Decision.** `relay/ratelimit_headers.py` encodes the documented reading (`*-requests` per day,
`*-tokens` per minute, no per-minute request header) but every 429 keeps its raw headers, and
an unparseable 429 stays `RATE_LIMITED_UNKNOWN` rather than being guessed into a bucket.
**Why.** Rule 5: never assert a Groq fact from memory. Wrong classification must degrade to
"unknown", never to "safe to retry".
**Rules out.** Retry decisions that depend on a parsed `retry-after` when it did not parse.
**Re-open at P1.** The probe in `docs/OPEN_QUESTIONS.md` replaces every claim with an observation.
