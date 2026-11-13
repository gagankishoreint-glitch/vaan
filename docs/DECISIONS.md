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
**Why.** The P3 threshold sweep evaluates every achievable operating point across
20 answerable and 7 unanswerable questions, and finds **no threshold with both
errors at zero**; the best point (14.82) still misclassifies 3 of 27. A strict gate
would refuse real questions at a measured rate. The gate can therefore only be a
cost control, never a correctness mechanism: H1 is guaranteed by `verify.py`
afterwards. Verification is the guarantee; the gate decides how often it is needed.
**Not tuned to 14.82.** Three questions separate it from 15.86 at n=27. Picking the
argmin of a sweep over 27 questions is fitting to noise; the fix is a larger eval
set, not a better threshold.
**Rules out.** Treating the BM25 score as the safety mechanism.
**Re-open at P10.** If a reranker improves separation, the gate can tighten.

### D-016 · 2026-11-11 · P5 · The local bucket mirrors the header in both directions
**Decision.** `Budget` reserves `max_tokens` at admission and then, when any response
arrives, hands the reservation back (`settle`) and adopts the provider's own view of
the window from `x-ratelimit-remaining-tokens` (`reconcile`) — upward as well as
downward.

**What the gateway did before this, stated plainly, because the question deserved a
precise answer.** It reserved prompt+cap at admission and never refunded locally. The
only correction was `reconcile`, which moved the bucket **downward only**
(`max(tpm_used, provider_used)`). Two consequences followed:

1. A short answer left the difference between its reservation and its real cost in the
   local bucket until the window rolled over. Twenty-five answers reserving 350
   against a 20-token actual cost closed an 8000-token window while the provider still
   reported the window empty. The gateway would throttle itself against a limit nobody
   was hitting. The test that now catches this fails with
   `local TPM budget exhausted: 7700+350 > 8000` after the provider has repeatedly said
   the bucket is full.
2. The streamed path never reconciled at all. (`pipeline.stream` defaults to **false**,
   so this was *latent* rather than universal: the pipeline sends buffered answers unless
   the flag is set. The original wording here said streamed was "every answer the
   pipeline sends", which was wrong — see the correction at the end of this entry.) `consume()` discarded the response headers, so the bucket was learned and
   corrected only on the probe's non-streamed calls. The rate-limit behaviour therefore
   depended on which code path happened to be used.

**Why upward is safe now.** `tpm_used_floor` holds the tokens taken in the current
window that no response has yet accounted for; `reconcile` cannot move the bucket below
it, so a header read can never forget an in-flight reservation. `settle` drops the
floor by exactly what the arriving response reserved. The floor is clamped at zero so
out-of-order settlement is harmless: too low only lets the header speak.

**What this does NOT decide.** Whether Groq refunds the unused part of the cap is still
unproven (n=2, and the two models fit equally well — see Q-06b and the pending A/B).
This design does not need that answer: it copies the header instead of predicting it,
and it adds no refund of its own on top. If Groq does not refund, the header will not
move and the local bucket will not move either. If it does, both move together.

**Rules out.** Reconstructing usage from `remaining` against *our* limit (BUG-010,
units mismatch); moving only downward; trusting the header across a window rollover;
and any second, independent refund calculation layered on top of the header.

**Correction (2026-11-11).** This entry twice asserted that streamed responses were
"every answer the pipeline sends". They are not: `config/relay.yaml` sets
`pipeline.stream: false`, and `scripts/run_queries.py` only streams with `--stream`.
The BUG-025 fix stands — a streamed run must reconcile exactly like a buffered one,
or the gateway's behaviour depends on which mode you happen to be running — but the
justification was overstated. Correct statement: **the streamed path must behave
identically to the buffered path whenever streaming is enabled.**

**Re-open if.** The A/B shows the header is not refreshed per response — then
reconciliation must be rate-limited to the reset interval rather than per call.
**Run it.** `python -m pytest -q tests/test_p4_p6.py -k "reconcile or ratchet"` →
`2 passed`.

### D-017 · 2026-11-11 · P6 · A measured value has no default
**Decision.** Any config key whose committed value is a measured number is read with
`cfg.require()`. A fallback is allowed only for keys that are null *by design* until
measured, and those are listed in one place in `tests/test_lint_rules.py`.

**Why.** `retrieval.gate_threshold` was read as `cfg.get(..., 15.0)` against a committed
15.86, and `gateway.retry_credit_floor` as `0.0` against 1.0 (BUG-028). A default does
not merely risk being wrong; it converts a configuration error into a silent behaviour
change, which is the one outcome rule 4 cannot tolerate.

**Rules out.** `cfg.get(measured_key, <number>)` anywhere, and the argument that a
default is "just a safety net" — a net that catches a renamed key and replaces it with
a number nobody measured is not safety.

**Re-open if.** A measured key genuinely needs to run before its measurement exists —
then it is null in config and belongs in `_PROVISIONAL` with the reason written down.

### D-018 · 2026-11-11 · P3 · Thresholds are recorded at full precision
**Decision.** Any artifact that records a decision boundary stores the value the
comparison actually used, in addition to whatever rounded form is displayed.

**Why.** BUG-029: `sweep()` stored `round(t, 3)`, so a candidate that was really
`15.8599…` printed as `15.86` — indistinguishable from the committed `15.86`, while
being a different threshold that gave a different count. A reader (and a table
generator, and the author) could not tell which decision a row described.

**Rules out.** Rounding a threshold before storing it, and quoting a threshold to
fewer decimals than it was compared at. Display precision is a presentation choice;
it must not be the only record.

**Re-open if.** An artifact format genuinely cannot carry full precision — then it
must carry the counts as well, so the decision is recoverable even if the boundary
is not.
