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

### D-008 · 2026-11-11 · P0 · `backend` is run scope, `attempt_backend` is attempt scope
**Decision.** The event envelope keeps `backend` = the run's backend. Attempt events carry
`attempt_backend` = the backend that served that attempt. A terminal event carries
`primary_backend` = majority of attempts, ties to first appearance.
**Why.** A new reserved-field guard (BUG-004) revealed that both meanings had been sharing
one key, so the per-attempt value was silently lost (BUG-005). The supervisor chose
"envelope wins, rename the attempt field" and "primary" for mixed runs.
**Deviation, flagged.** "Primary" is implemented as *majority with first-appearance
tie-break*, not literally the first attempt. Literal first is a race under concurrency and
mislabels a request that failed over. Revert to strict-first on request.
**Rules out.** Run-level `backend` meaning "the backend of the first attempt".
**Re-open if.** A run is defined as single-backend by construction (then `mixed` disappears
and the envelope field is redundant).

### D-009 · 2026-11-11 · P1 · The probe is dry-run by default and ceiling-gated
**Decision.** `scripts/probe.py` sends nothing without both `--go` and
`--max-tokens-total N`; the ceiling uses reserve-before-send so a request that turns out
to cost more than estimated cannot overshoot it. No retries. Authorization is never
logged and the key value is scrubbed from every artefact as a second defence. Spend is
appended to `docs/TOKEN_LEDGER.md` only on `--go`. `rpd` is excluded from `--mode all`.
**Why.** The probe is the first code that spends real money, and the failure mode of a
probe is a silent overspend on day 1. Reserve-before-send is the only ordering that
cannot overshoot, because it does not depend on knowing the cost in advance.
**Rules out.** A probe that retries (a failure is data), and a probe that infers the
key is absent rather than refusing.
**Re-open if.** The measured daily cap makes a 60K day plan obviously wrong.

### D-010 · 2026-11-11 · P1 · `bigctx` must not run inside the default plan
**Decision.** `bigctx` is measured with its own token reservation, not as part of `--mode all`.
**Why.** The dry run's own arithmetic: a 400-repeat filler prompt is ~240K tokens at the
deliberate over-estimate (÷3 chars), four times the whole 60K day plan. The over-estimate
is *correct* behaviour — it refused before spending — but the mode as specified would
have needed a second day.
**Rules out.** A single `--go` invocation covering `bigctx` plus everything else.
**Re-open when.** `usage.prompt_tokens` for a known prompt is measured; the divisor moves
from 3 to the observed chars-per-token and bigctx shrinks accordingly.

### D-011 · 2026-11-11 · P0/P1 · `backend` is DECLARED, never computed (supersedes D-008)
**Decision.** `EventLog(backend=...)` is a declaration, one of `groq`/`standin`/`mixed`,
validated at construction. Per-attempt values go in `attempt_backend`. The observed
breakdown is emitted once in `run.end` as `attempt_backend_counts`. Checker I7 compares
each `attempt_backend` against the *declaration*; I8 checks the counts sum to the number
of attempts.
**Why.** A label computed from the attempts it describes cannot contradict them — so a
run launched at the stand-in URL but tagged `groq` was undetectable, and I7's
"mixed" escape hatch was itself derived from the data. Supervisor review; D-008's
majority-with-tie-break is withdrawn.
**What this fixed.** `RequestScope` no longer holds backend state; `run.start` and
`run.end` carry the same declaration by construction. `close()` deliberately does not
emit `run.end`, so a crashed run is distinguishable from a clean one.
**Re-open if.** Runs become single-backend by construction and `mixed` is dead.

### D-012 · 2026-11-11 · P1 · `bigctx` is sized in tokens, not repeat counts
**Decision.** `--bigctx-tokens` defaults to `1.25 x models.small.tpm`. `--bigctx-repeat`
is removed and rejects loudly rather than silently doing the wrong thing.
**Why.** A repeat count made the prompt depend on a chars/token guess: 400 repeats
estimated at 240K, four times the day plan, and it answered a question (context window)
nobody asked. Sizing by TPM answers the actual question — what happens when ONE request
exceeds the per-minute token limit — and lets bigctx share a day with the other modes.
**Re-open when.** `usage.prompt_tokens` is measured for a known prompt; the estimate
divisor moves from 3 and 1.25x may be tightened.

### D-013 · 2026-11-11 · P2 · Chunks keep contaminated text; they are flagged, not filtered
**Decision.** Table/figure caption chunks stay in the corpus with a `caption` flag.
Longest-wins and dedup are not applied. Chunk size/overlap stay `null` in config until P10.
**Why.** The retrieval section needs real examples of broken numeric rows. Filtering them
would make the retriever look better than it is and delete the evidence. Choosing
900/150 now would be choosing a number P10 exists to measure.
**Re-open at P10.** If a filter improves recall@k, it becomes a *measured* setting with
the untouched corpus as its control.

### D-014 · 2026-11-11 · P4 · the stand-in may use raw time; nothing else may
**Decision.** `tests/test_lint_rules.py` allows `time.monotonic()` and
`asyncio.sleep()` in `relay/standin/server.py` only.
**Why.** Rule 7 exists so our own duration measurements are injectable and testable.
The stand-in's entire job is to *fabricate* latency; forcing it through our Clock
would make it measure itself. The allowlist entry carries this justification inline.
**Re-open if.** Any other module is added to the allowlist — at that point the rule
has stopped meaning anything.

### D-015 · 2026-11-11 · P6 · the evidence gate is permissive on purpose
**Decision.** `retrieval.gate_threshold: 15.86` is committed and the gate admits
when top-1 >= it. It is deliberately not tuned to minimise false-answers.
**Why.** P3 measured that no single BM25 threshold separates answerable from
unanswerable (26% false-abstain and 12.5% false-answer at the same point). A strict
gate would refuse real questions; a loose one is safe *because* `verify.py` enforces
H1 afterwards. Verification is the guarantee; the gate is only a cost control.
**Rules out.** Treating the BM25 score as the safety mechanism.
**Re-open at P10.** If a reranker improves separation, the gate can tighten.
