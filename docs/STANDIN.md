# P4: STAND-IN CALIBRATION

`relay/standin/server.py` — FastAPI, Groq-compatible paths, seeded.

```bash
.venv/bin/uvicorn relay.standin.server:app --host 0.0.0.0 --port 8009
curl -s localhost:8009/openai/v1/models
curl -s localhost:8009/__stats
curl -s -X POST localhost:8009/__reset
```

## Calibration status: NOT CALIBRATED

Every parameter is still provisional, because the P1 probe has not run (no limits
page, no key). The server prints a warning per null at startup so a provisional
value can never be mistaken for a measured one:

```
[standin] standin.ttft_ms is null; using 180.0 (provisional: no real probe yet)
[standin] standin.per_minute_limit is null; using 8000 (provisional: docs-table TPM, UNVERIFIED)
```

| parameter | provisional | set by |
|---|---|---|
| `ttft_ms` | 180 | P1 `single` mode |
| `tokens_per_s` | 90 | P1 `stream` mode |
| `error_rate` | 0.0 | P1 (observed 5xx rate) |
| `p429_rate` | 0.0 | P1 `burst` |
| `per_minute_limit` | **8000** | **OBSERVED** (transcribed, n=4) — was docs table |
| `per_day_limit` | 200000 | limits page, still UNVERIFIED (Q-04) |
| `refund_unused_cap` | false | **OBSERVED**-consistent, never isolated (Q-06) |

**The stand-in is therefore a load *shape* generator, not a latency model.** Any
latency number measured against it is a property of this file, not of Groq. The
report must not present stand-in latency as provider latency.

## Controls that do work (and are tested)

- per-minute token bucket, per-day token bucket, per-day request bucket
- 429 with `retry-after` and full `x-ratelimit-*` headers in Groq's shape
- 5xx injection (`standin.error_rate`), hang (`STANDIN_HANG_S`), slow success
  (`STANDIN_SLOW=1`), load-dependent slowdown (`STANDIN_LOAD`)
- SSE streaming with per-token gaps and a final usage chunk
- citation-aware answers: quotes verbatim from a supplied passage so the happy
  path is exercised, with `STANDIN_UNVERIFIABLE_RATE` (default 0.2) producing
  deliberately unverifiable answers so the *failure* path is exercised too

## Bucket model: what is VERIFIED and what is not

### Transcribed observations — `transcribed, n=4, raw JSONL pending`

Real runs by the supervisor against `openai/gpt-oss-20b` on a **free account**. These
are relays of his `curl` output, not a stored artifact: `calibration/probe/` lands
when he is back at his PC. `n=4`, all within ~2 s of each other, so treat every
inference below as provisional.

```
limit-tokens 8000, limit-requests 1000
call 1 (full bucket, cap 80): prompt 76, completion 41
       remaining-tokens 7844, reset-tokens 1.17 s
       remaining-requests 999, reset-requests 1m26.4 s
call 2 (+0.79 s): remaining 7822, reset 1.335 s
call 3 (+0.98 s): remaining 7872, reset 960 ms
```

**What they show.**

| finding | confidence |
|---|---|
| deficit = prompt + **cap**, not prompt + completion (call 1: 156 = 76 + 80, with 41 generated) | strong for this shape, n=1 isolates it -> Q-06 favours up-front reservation |
| `reset-tokens` = deficit / (8000/60) in **all three** | strong: three independent points, exact to the recorded precision |
| the TPM bucket refills **continuously** at 133.3 tokens/s | **refutes the old fixed-60 s-window model**, which would report ~60 s |
| `reset-requests` 1m26.4 s = 86400/1000 | consistent with `*-requests` being per day (Q-04) |

**What they do NOT show.** The refill function over gaps longer than ~2 s; whether
unused cap is refunded on completion (never isolated — hence
`standin.refund_unused_cap`, default `false` because the observed deficit carried the
full cap); what a 429 body looks like (Q-09); whether `retry-after` is always present
(Q-11). **No 429 appears in these four observations at all.**

The old `Bucket` (fixed window) got `remaining` right — 7844 exactly — and `reset`
wrong by a factor of 50. A model can be half right, and the half it gets wrong was
the half the gateway reads to decide when to retry.

### Verified in the stand-in

`RefillBucket` reproduces the observations: call 1 lands on `remaining 7844,
reset 1.170` exactly; calls 2–3 land within 1 % of the recorded reset (the inter-call
gaps survive transcription only to 2 dp, worth ~1.3 tokens).
`tests/test_standin_observed.py` (5 tests) also *records the refutation* of the
fixed-window model, so the change cannot be quietly reverted.

### Stand-in-only headers

The stand-in enforces a day *token* bucket that Groq is not believed to expose. Its
counters are emitted under `x-standin-*` names so they can never be mistaken for a
provider header; a test asserts every `*day*` header carries that prefix.

## Documented differences from the real service

1. Model IDs are whatever `config/relay.yaml` says; no real model list.
2. Token counting is `len(json)/4` for prompts and `max_tokens` for completions.
   Not a tokenizer.
3. `max_tokens` is charged to the TPM bucket **up front**. This is no longer a
   hypothesis: call 1's deficit was 76 + 80 with only 41 tokens generated
   (transcribed, n=4). Whether unused cap is later refunded is still OPEN, hence
   `standin.refund_unused_cap` (default false).
4. Daily reset is a rolling 86400 s window, not a wall-clock boundary.
5. No context-length limit is enforced (Q-12 unmeasured).
6. Authentication is not checked.
