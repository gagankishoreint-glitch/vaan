# BRIEF TRACE — every PRD requirement, and where it actually lives

Item I. The PRD (`prd.md`) is the brief. This file answers one question per
requirement: **what proves it?** Not "was it intended" — every row needs a test, a
run, or an explicit NOT BUILT.

**Read the status column before quoting a row.** Three states are used, and they are
not interchangeable:

| status | meaning |
|---|---|
| **TESTED** | unit/integration test fails if the behaviour is removed |
| **RUN** | executed end to end, artifact exists, labelled with what it validates |
| **BUILT, NOT WIRED** | the code exists and is tested **in isolation**; `Pipeline.answer()` does not call it |
| **NOT BUILT** | no code path reaches this requirement |

"BUILT, NOT WIRED" is the honest category for most of the compressed-mode work
(items C, D, E, G): the component is real, its own tests are green, and a user
traffic path does not yet use it. Saying "built" without that qualifier would be the
single easiest lie in this document.

Evidence was re-run in the agent sandbox at the time of writing. **No PDFs are
present**, so nothing corpus-dependent ran here; those rows say so.

---

## 2. Goals

| goal | requirement | status | evidence |
|---|---|---|---|
| Fast | TTFT p50/p95, total p95 ≤ TBD | **NOT MEASURED** | thresholds are null in `config/relay.yaml`; no real-provider run exists. Stand-in latency is not provider latency (`docs/STANDIN.md`) |
| Good | ≥ TBD % correct-and-cited on 15+ questions | **NOT MEASURED** | 27 questions exist (`data/eval/questions.jsonl`: 12 single, 4 cross, 4 numeric, 4 unanswerable, 3 ambiguous); grading needs the corpus |
| Cheap | median tokens per answer ≤ TBD | **NOT MEASURED** | `runs/h4_tokens.json` is abandon-token data, not cost per answer |
| Nobody turned away | every request gets a reply; weaker never wrong | **TESTED + RUN** | H1 at `send_reply` (`contracts.is_reply`); shedding returns `PassagesOnly(queue_full)` not a bare rejection (item D); `runs/standin/admission_queue.json` — 5 over-capacity → 5 terminals, 0 dropped |

## 4. Pipeline

| step | requirement | status | evidence |
|---|---|---|---|
| 1 Admission | deadline + budget check, cache lookup, coalescing | **BUILT, NOT WIRED** | `relay/pipeline/queue.py` (11 tests), `relay/pipeline/cache.py` (12 tests). `answer()` calls neither — grep confirms no `AnswerCache`/`AdmissionQueue` reference |
| 2 Retrieve | BM25 on the raw question, concurrent with rewrite | **PARTIAL** | BM25 retrieval exists (`relay/retrieval/bm25.py`); there is **no rewrite step**, so there is nothing to run concurrently with |
| 3 Decide | code gate first, LLM grade only if ambiguous; rewrite+widen loop (max 1) | **PARTIAL** | code gate is `gate()` + `pipeline.gate_threshold`. **The LLM grader and the rewrite/widen loop are NOT BUILT** |
| 4 Draft | quote-first, streamed | **TESTED + RUN** | `_draft` routes via `model_for` (item F); streaming covered by `test_protocol_error_path.py` and `test_stream_http_error.py` |
| 5 Verify | code checks first; LLM groundedness only if budget allows **and code checks pass**; fail → redraft once → `PassagesOnly` | **PARTIAL** | code checks: `relay/pipeline/verify.py` (`check_citations`, `check_numbers_present`). LLM self-check: `relay/pipeline/selfcheck.py`, 16 tests, **downgrade-only and NOT WIRED**. **No redraft-once loop exists** |

## 5. Model gateway

| requirement | status | evidence |
|---|---|---|
| Check order: deadline → admission → budget → breaker → send → reconcile → classify → retry | **PARTIAL** | budget → breaker → send → classify → retry is in `Gateway.call`; admission is item D and not wired into this path |
| RPM (local), TPM/RPD from headers, TPD local + 429 | **TESTED + RUN** | `test_per_model_buckets.py` (6), `test_p4_p6.py` rate-limit tests; `runs/standin/` day-limit artifacts |
| Parse `ms/s/m/h/d`, always store the raw string | **TESTED** | `relay/ratelimit_headers.py` + tests; `attempt.rl_headers_raw` on every attempt |
| 429 minute vs day by `retry-after` size; **never retry a day limit** | **TESTED + RUN** | `_next_delay` returns `None` on `RATE_LIMITED_DAY`; BUG-031 artifact; `test_a_day_limit_429_still_yields_budget_gone` |
| Retry: honour `retry-after`, global retry budget, never sleep past deadline, release slot while sleeping | **TESTED** | `_next_delay`; `retry_budget_ratio` 0.1 / floor 1.0 (UNMEASURED); `test_stream_http_error.py` pins the 1-retry arithmetic |
| **Jitter** | **NOT BUILT** | `_next_delay` returns `retry_after` or 1.0; no jitter term |
| Timeouts: per-attempt + total deadline above the transport | **TESTED** | `test_attempt_timeout.py` (8), item A |
| Breaker closed/open/half-open **with a single probe** | **TESTED** | `test_breaker_half_open.py` (5); BUG-041b — half-open was a label only |
| `retry_policy: managed \| naive` | **TESTED** | `_next_delay` is the only policy difference; naive uses `naive_max_attempts` 5 |

## 6. Degradation ladder

| level | requirement | status | evidence |
|---|---|---|---|
| L0–L3 | thresholds TBD → now config keys, all UNMEASURED | **BUILT, NOT WIRED** | `relay/pipeline/ladder.py`, 13 tests, mutation-checked; `compute_level` is a pure function. `answer()` **takes `ladder_level` as a parameter** instead of computing it |
| L1 | smaller model for rewrite/verify, smaller k, no loop | **PARTIAL** | model routing for `draft` is wired (item F); rewrite/verify steps have no implementation to route |
| L2 | cache + coalescing, shorter answer cap | **NOT WIRED** | cache/coalescer exist and are tested; `max_tokens` scaling exists as `l2_max_tokens_scale`, provisional |
| L3 | `PassagesOnly` / `NoEvidence`, 0 tokens, honest message | **TESTED** | ladder emits L3 at zero budget; the 0-token path is `PassagesOnly` (BUG-042 mapping) |
| **Never: skip verification and send a draft** | **TESTED** | `send_reply` is the single exit; `VerifiedAnswer` cannot be built without `mint_verified` (`test_smoke_p0.py`) |

## 7. Cost levers

| lever | status | evidence |
|---|---|---|
| Model cascade | **TESTED, saving UNVERIFIED** | `cascade.py` (9 tests); Q-03 OPEN — `buckets_separate_per_model` null, so the saving is conditional |
| Rule-based routing | **TESTED** | `model_for(step, level, cfg)`, ladder check first |
| Code-based citation checks | **TESTED** | `verify.py`, `test_p4_p6.py` citation/number tests |
| Structured output | **NOT BUILT** | no `response_format` anywhere in `relay/` |
| `max_tokens` caps | **TESTED** | config-driven, no numeric fallback (BUG-028 lint) |
| Exact cache | **BUILT, NOT WIRED** | `cache.py`, 12 tests |
| Request coalescing | **BUILT, NOT WIRED** | same module; refcounted cancellation |
| **Stable prompt prefix first** | **TESTED** | `test_prompt_prefix.py` — instructions before passages, byte-identical across requests, no request id/level/date/latency interpolated |

## 8. Stand-in server

| control | status | evidence |
|---|---|---|
| Groq-compatible path, SSE | **TESTED + RUN** | `relay/standin/server.py`; `test_sse_end_to_end.py` |
| Latency distribution fit from probe | **NOT BUILT (no probe data)** | `ttft_ms` null → 180 ms provisional, printed at startup |
| Load-dependent slowdown | **TESTED** | `STANDIN_LOAD` |
| Error rates (5xx, hang) | **TESTED + RUN** | `standin.error_rate`; `runs/standin/breaker_cycle.json`, `stream_http_error.json` |
| Slow-success mode | **TESTED** | `STANDIN_SLOW=1` |
| 429 with `retry-after` + Groq-shaped headers | **TESTED + RUN** | `runs/standin/` day-limit artifact; BUG-031 |
| Per-minute / per-day limits | **RUN** | continuous refill 133.3 tok/s (BUG-033), `test_standin_observed.py` (9) |
| **Mid-stream disconnect** | **NOT BUILT** | no such control in `relay/standin/server.py` |
| Seeded, reproducible | **TESTED** | `standin.seed` 7 |
| Documented differences | **DONE** | `docs/STANDIN.md`, "Documented differences" |

## 9. Load generation

| requirement | status | evidence |
|---|---|---|
| Open-loop asyncio generator, separate process | **TESTED + RUN** | `scripts/loadgen.py`; `runs/standin/overload_refund_*` |
| Precomputed schedule from a seed, **drift measured and reported** | **TESTED + RUN** | `--out` writes planned vs actual; drift p95 0.002 s in the refund A/B |
| Shapes: steady, burst, overload | **TESTED** | `--shape` |
| Abandon-heavy | **TESTED** | `docs/P7_ABANDON.md`, `runs/h4_tokens.json` |
| Real Groq only for small runs | **N/A here** | 0 real calls made in this sandbox, by instruction |

## 10. Observability

| invariant | status | evidence |
|---|---|---|
| Append-only JSONL, all numbers from events | **TESTED** | `relay/events.py`; `flush()` waits for the write (BUG-026) |
| I1 exactly one terminal | **TESTED + CHECKED** | `check_events.py`, `test_events.py` |
| I2 no attempt after terminal | **TESTED + CHECKED** | same |
| I3 no negative bucket | **TESTED + CHECKED** | same |
| I4 waiting+working+retrying ≈ total | **TESTED + CHECKED** | same |
| I5 permitted reply type **and reason** | **TESTED** | `check_events.py` + `analyze.py` re-typed sets, `test_reasons.py` asserts all three agree |
| I6 no tokens after abandon | **TESTED + CHECKED** | `test_p4_p6.py`, `docs/P7_ABANDON.md` |
| I7/I8 backend scope, run.end continuity | **TESTED** | `test_check_events.py` |
| **`/__stats` usable** | **FIXED** | BUG-044 — it had raised `AttributeError` on every call since BUG-033 |

## 11. Evaluation

| requirement | status | evidence |
|---|---|---|
| ≥ 20 questions, five types | **DONE** | 27 questions, all five types present |
| Graded correct/partly/wrong/correctly-abstained/wrongly-abstained + citation valid | **PARTIAL** | `evaluate()`/`sweep()` fixed for ambiguous-vs-false (BUG-027, BUG-032); **grading needs the corpus, absent here** |
| Retrieval experiment ≥ 3 settings | **NOT RUN HERE** | `scripts/retrieval_eval.py` + `docs/P3_RETRIEVAL.md`; needs PDFs |

## 12. Non-goals

Chosen two (per `docs/DECISIONS.md`): **no distributed shared limiter (Redis)** and
**no embedding/vector index**. Neither appears in the tree.

## 13. Open questions

| question | status |
|---|---|
| Model IDs, real limits page | OPEN — `per_day_limit` null |
| **Limits per model or shared (Q-03)** | **OPEN** — `buckets_separate_per_model` null; code assumes separate and says so |
| Reasoning tokens and TTFT | OPEN |
| Does `max_tokens` reserve TPM up front (Q-06) | **PARTIALLY ANSWERED, n=2** — reservation at admission is supported; **refund at completion is OPEN** and the switch is labelled an assumption |
| Minute-429 vs day-429 shape (Q-09) | OPEN — no 429 in the four observations |
| TPM refill shape | **ANSWERED for short gaps** — continuous 133.3 tok/s; refutes the fixed window. Longer gaps unknown |
| Prompt caching support | OPEN |
| Context-too-large status (Q-12) | OPEN |

## 14. Phases

P0–P3 have committed artifacts and docs. **P4 is NOT CALIBRATED** (no probe data).
P5–P8 pieces exist as listed above; several are built-but-not-wired. P9 (analysis),
P10 (retrieval experiment) and P11 (report) are **not complete**.
Each phase exits only when its tests pass **and** its BUGLOG/DECISIONS entries exist;
by that rule P4 has not exited.

## 15. Real-token budget

`docs/TOKEN_LEDGER.md` exists and was **not touched** by this work, by instruction.
No real Groq call was made in this sandbox; the ledger is the supervisor's.

---

## The short version

**Solid, tested, and wired:** H1 at the single exit, the gateway (budget per model,
429 classification, retries, per-attempt timeout, breaker with a real single probe,
streamed non-200 handling), the stand-in's bucket model, the event log and its
invariants, the prompt prefix, and the reason vocabulary.

**Built and tested but NOT reached by `answer()`:** admission queue, cache,
coalescing, the ladder's level computation, the LLM self-check. These are the
compressed-mode items; their own tests are green and they change nothing for a user
until wired.

**Not built at all:** the rewrite/widen step, the LLM ambiguity grader, the
redraft-once loop, structured output, retry jitter, mid-stream disconnect, and the
latency fit from probe data.

**Not measurable here:** every corpus-dependent number. The PDFs are absent, so no
retrieval or answer-quality figure in this repository was produced by this sandbox.

---

## 5b · quality grading (`scripts/run_quality.py`)

PRD §11 asks for six outcomes per question. **Four are decidable from the run
artifact; two are not**, and the script refuses to guess the difference.

| PRD class | decided here? | how |
|---|---|---|
| correctly abstained | **yes** | `no_evidence`/`passages_only` on an `unanswerable` question, with a non-infrastructure reason |
| wrongly abstained | **yes** | abstained on an answerable question |
| wrong | **yes** | answered, but cited no gold chunk (H2: every claim cites the paper) |
| correct | **NO** | needs a reader; a gold citation is necessary, not sufficient |
| partly | **NO** | needs a reader |
| citation valid y/n | **partly** | `gold_hit` = "cited ≥1 gold chunk", **not** "every citation resolves" — the latter needs the chunk index |

Two classes exist because the naive version of each would have inflated the table:

* **`abandoned`** is not an abstention. Counting it as one improves every quality
  metric by simply having impatient users.
* **`infra_abstention`** is not a correct abstention. A `passages_only` on an
  unanswerable question *reads* as correct, but with `reason=upstream_error` we
  abstained because the provider failed — the papers' silence was never established.
  Found by running the script on a synthetic row, not by reasoning about it.

**Mutation checks:** scoring `correct` from a gold citation fails 3 tests; adding
`abandoned` to the abstain set fails the strengthened order test (it passed before
that test existed, because `classify` returns on `abandoned` first — the guard is the
ORDER, and the order is now pinned).

**Run:** `runs/standin/quality_smoke/` — 6 synthetic rows covering every class,
graded in the agent sandbox. **UNCALIBRATED and synthetic**: it exercises the
classifier, it is not a quality measurement of the system.
