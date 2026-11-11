# PRD: The Relay

Status: DRAFT v0.1. Numbers marked TBD are set after Phase 1 (probe).

## 1. Purpose
A Python service that answers engineers' questions about three arXiv papers by
chaining model calls and one local tool, under bursty load and strict provider
limits. The deliverable is the system plus measurements showing that every
trade-off follows from data.

Papers (exact versions):
- Attention Is All You Need, 1706.03762 v7
- Moshi, 2410.00037 v1
- Dynamic Chunking for End-to-End Hierarchical Sequence Modeling, 2507.07955 v2

## 2. Goals and the trade-offs we accept
| Goal | Definition (TBD values marked) |
|---|---|
| Fast | TTFT p50 <= TBD s, p95 <= TBD s; total p95 <= TBD s. User patience (give-up) = TBD s. |
| Good | >= TBD% correct-and-cited on our 15+ question set; 100% of abstain questions abstain. |
| Cheap | Median tokens per answer <= TBD; cached tokens do not count toward Groq limits. |
| Nobody turned away | Every request receives a reply. The reply may be weaker, never wrong. |

Accepted trade-offs:
- Speed vs cost: skip optional LLM steps under pressure.
- Truth vs coverage: when evidence is weak, abstain or show passages. Never guess.
- Under token exhaustion, "not turned away" means a zero-token passages-only reply.

Hard rules (non-negotiable):
- H1. No reply is sent unless it is a `VerifiedAnswer`, a `NoEvidence`, or a `PassagesOnly`.
- H2. Every factual claim cites paper + section/page + chunk id; quotes match verbatim.
- H3. If the papers do not say, the reply says so.
- H4. Abandoned requests stop consuming tokens.

## 3. Actors
Engineer (asks questions; may abandon). Assistant (the pipeline).

## 4. Pipeline
1. Admission: deadline and budget check, cache lookup, coalescing.
2. Retrieve (TOOL, local BM25) on the raw question, concurrent with the optional rewrite.
3. Decide (code gate first, LLM grade only if ambiguous):
   - strong evidence -> draft
   - weak -> rewrite + widen, max N loops (TBD, default 1)
   - none / out of scope -> NoEvidence reply (0 tokens)
4. Draft, quote-first: extract verbatim quotes with locations, then write the answer from the quotes only; streamed.
5. Verify: code checks first (chunk ids exist, quotes verbatim, numbers present). LLM groundedness check only if budget allows and the code checks pass.
   - fail -> redraft once -> else PassagesOnly.

## 5. Model gateway (single owner of limit state)
Order of checks per call: deadline -> admission/queue -> budget reserve -> breaker -> send -> reconcile -> classify -> retry.
- Budget: RPM (local), TPM (from `x-ratelimit-remaining-tokens`), RPD (from `x-ratelimit-remaining-requests`), TPD (local + 429).
- Headers: parse `ms/s/m/h/d` forms; always store the raw string.
- 429: classify minute vs day by `retry-after` size and body text (recorded in the probe; no assumptions).
  Never retry a day-limit 429.
- Retry: honor retry-after, jitter, global retry budget (TBD % of traffic), never sleep past deadline, release concurrency slot while sleeping.
- Timeouts: per-attempt, plus total request deadline above the transport (catches "slow success").
- Breaker: closed / open / half-open with a single probe.
- Policy switch: `retry_policy: managed | naive` (naive exists only to demonstrate harm on the stand-in).

## 6. Degradation ladder (driven by remaining budget)
| Level | Trigger (TBD thresholds) | Behaviour |
|---|---|---|
| L0 Normal | budget healthy | full pipeline, k=TBD |
| L1 Pressure | TPM remaining < TBD% or queue wait > TBD s | smaller model for rewrite/verify, smaller k, no loop |
| L2 Heavy | repeated identical questions, queue deep | cache + coalescing, shorter answer cap |
| L3 No budget | RPD/TPD gone or breaker open | PassagesOnly / NoEvidence, 0 tokens, honest message |
Never: skip verification and send a draft.

## 7. Cost levers
Model cascade; rule-based routing; code-based citation checks; structured output; max_tokens caps; exact cache; request coalescing; stable prompt prefix first (cached tokens do not count toward limits; verify model support).

## 8. Stand-in server (FastAPI + uvicorn)
Groq-compatible `/openai/v1/chat/completions`, SSE streaming. Controls: latency distribution (fit from probe), load-dependent slowdown, error rates (5xx, hang), slow-success mode, 429 with `retry-after` and `x-ratelimit-*` headers in Groq's format, per-minute and per-day limits, mid-stream disconnect. Seeded. Documented differences from the real service are listed in the report.

## 9. Load generation
Custom open-loop asyncio generator in a separate process. Arrival schedule precomputed from a seed; send-time drift is measured and reported. Shapes: steady, burst, sustained overload (+ optional abandon-heavy). Real Groq only for small runs; stand-in for the rest.

## 10. Observability
Append-only JSONL events; all report numbers derived from events. Invariants checked automatically:
exactly one terminal event per request; no attempt after terminal; no negative bucket; waiting+working+retrying ~= total; no unverified reply; no tokens consumed after abandon.

## 11. Evaluation
- >= 20 hand-written questions (single-paper, cross-paper, numeric/table, ambiguous-term, unanswerable), each with reference answer + source.
- Graded: correct / partly / wrong / correctly-abstained / wrongly-abstained; citation valid y/n.
- Retrieval experiment: >= 3 settings (chunk size, k, rerank); report quality, tokens per answer, TTFT.

## 12. Non-goals (deliberately not built)
TBD pick two, candidates: distributed shared limiter (Redis), embedding/vector index, durable workflow engine, multi-tenant fairness, UI.

## 13. Open questions (answered by Phase 1)
- Which model IDs exist for this key; real limits on the limits page.
- Are limits per model (separate buckets) or shared?
- Reasoning-token behaviour and its effect on TTFT and tokens per answer.
- Does `max_tokens` reserve TPM up front?
- What do minute-429 and day-429 look like (status, headers, body)?
- TPM refill shape; daily reset time.
- Which models support prompt caching; do cache hits show in `usage`?
- Context-too-large behaviour (status code).

## 14. Phases and exit criteria
P0 Setup+contracts | P1 Probe | P2 Ingest+chunk | P3 Retrieval+eval set | P4 Stand-in (calibrated) |
P5 Gateway | P6 Pipeline | P7 Cache/coalesce/abandon | P8 Harness | P9 Analysis | P10 Retrieval experiment | P11 Report.
Each phase exits only when its tests pass and its BUGLOG/DECISIONS entries are written.

## 15. Real-token budget plan
Groq free tier has a daily token cap (about 200K TPD per the docs table; verify). Allocate across days:
probe, eval x settings, final real runs. Track spend in `docs/TOKEN_LEDGER.md`.
