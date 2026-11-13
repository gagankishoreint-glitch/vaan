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

| parameter | provisional | source |
|---|---|---|
| `ttft_ms` | 180 | NOT YET MEASURED: placeholder until probe single-mode data |
| `tokens_per_s` | 90 | NOT YET MEASURED: placeholder until probe stream data |
| `error_rate` | 0.0 | NOT YET MEASURED: placeholder until probe burst/stream data |
| `p429_rate` | 0.0 | NOT YET MEASURED: placeholder until probe burst data |
| `per_minute_limit` | **8000** | OBSERVED (n=4), from the probe's own records |
| `per_day_limit` | 200000 | NOT YET MEASURED: placeholder until probe data (Q-04) |
| `refund_unused_cap` | false | **ASSUMPTION, OPEN (Q-06)** until the supervisor's A/B curl result |

**Never cite a probe mode as a source before it ran.** The four `null` rows above
have no measured value at all; the provisional numbers are the stand-in's own
fallbacks, printed at startup, and they are placeholders rather than findings. The
one measured number in this table (`per_minute_limit`) comes from the probe's
jsonl, not from a mode that was merely planned.

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

Real runs by the supervisor against `openai/gpt-oss-20b` on a **free account**.

**Source: the probe's own records** — `runs/probe_20261111T062707Z/single.jsonl` and
`runs/probe_20261111T064821Z` — **not** output relayed through `curl`. The files are
not in this repository yet: the supervisor is at his PC and will commit
`calibration/probe/`. Until then `tests/test_standin_observed.py` retypes the values,
and once the files land it must **read them from those files instead of retyping
them**, so a transcription error has one place to be wrong rather than two.

`n=4`, all within ~2 s of each other, so every inference below is provisional.

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
| deficit = prompt + **cap**, not prompt + completion (call 1: 156 = 76 + 80, with 41 generated) | reservation is **n=2** (calls 1 and 4), one model, one prompt shape |
| `reset-tokens` = deficit / (8000/60) in **all three** | exact against the transcribed deficit, to the precision recorded |
| the TPM bucket refills **continuously** at 133.3 tokens/s | **refutes the old fixed-60 s-window model**, which would report ~60 s |
| `reset-requests` 1m26.4 s = 86400/1000 | consistent with `*-requests` being per day (Q-04) |

**What they do NOT show.** The refill function over gaps longer than ~2 s; whether
unused cap is refunded on completion (Q-06 — see below); what a 429 body looks like
(Q-09); whether `retry-after` is always present (Q-11). **No 429 appears in these
four observations at all.**

### Refund of unused cap: ASSUMPTION, OPEN (Q-06)

`standin.refund_unused_cap` defaults to `false`, and that is an **assumption**: the
branch we start from, not a finding. It stays OPEN until the supervisor's A/B curl
result lands.

An earlier version of this file called the default "OBSERVED-consistent" and
reasoned from *the deficit carried the full cap even though 41 of 80 tokens were
generated*. **That is the admission-time reading.** It says the cap is reserved up
front — which the observations do support — and says nothing about whether unused
cap comes back when the call finishes. Drawing a refund conclusion from it does not
follow, and the label was wrong to suggest otherwise.

The only evidence that speaks to refund at all is weaker, and it is not decisive.
Assuming call 2 reserved the same 156 tokens as call 1:

| model | implied reserve for call 2 | miss vs 156 |
|---|---|---|
| no refund | 127.3 | **~29 tokens** |
| refund (39 tokens back after call 1) | 166.3 | **~10 tokens** |

So the 1→2 interval fits refund *slightly* better. Two caveats, both against
over-reading it:

* **refund is still ~10 tokens out**, and in the direction of *more* than was
  reserved. "Closer" is not "correct".
* that is **one interval**. The 2→3 interval gives no independent check, because
  call 3's reservation is not in the record either. **n=2 intervals, one model, one
  prompt shape: INCONCLUSIVE.**

Every stand-in run records the value it used (`run.start.standin_refund_unused_cap`,
and `assumptions` in the stand-in's own `/__stats`), so overload results can be
reported under both settings and tied to the branch that produced them.

### Overload under both settings — UNCALIBRATED, run in the agent sandbox

Both arms: `loadgen --shape overload --rps 40 --duration 12 --max-tokens 80`,
`per_minute_limit 8000`, seed 7, real HTTP against the stand-in, **0 Groq calls**.

| arm | 200 | 429 | first 429 at arrival |
|---|---|---|---|
| `refund_unused_cap: false` | 92 | 388 | **79** |
| `refund_unused_cap: true` | 149 | 331 | **126** |

`runs/standin/overload_refund_ab.json` (and the two `overload_refund_*` run dirs).

**What this shows: the assumption is not cosmetic.** Refund serves ~62 % more requests
and pushes the first rejection back by 47 arrivals, because under no-refund every
call permanently loses the cap it did not use. **What it does not show: which branch
Groq implements.** That is still Q-06, still OPEN, still the supervisor's A/B curl.
The 429s here are the stand-in's own bucket, not the provider's.

The old `Bucket` (fixed window) got `remaining` right — 7844 exactly — and `reset`
wrong by a factor of 50. A model can be half right, and the half it gets wrong was
the half the gateway reads to decide when to retry.

### Verified in the stand-in — two separate claims

These are different strengths of result and must not be reported as one:

1. **`reset-tokens` is exact against the transcribed deficit.** Call 1 lands on
   `remaining 7844, reset 1.170` exactly — the arithmetic is `deficit / 133.3`, and
   the stand-in reproduces it.
2. **Calls 2–3 are reproduced within 1 % of the *rounded* gaps.** The inter-call
   gaps survive transcription to 2 dp, worth ~1.3 tokens, so this is a tolerance
   check on rounded inputs, not an exact reproduction.

Claim 2 is weaker than claim 1, and it is the one that would silently pass if the
stand-in's rate were slightly wrong but the tolerance were slightly generous.

`tests/test_standin_observed.py` also *records the refutation* of the fixed-window
model, so the change cannot be quietly reverted.

### Stand-in-only headers

The stand-in enforces a day *token* bucket that Groq is not believed to expose. Its
counters are emitted under `x-standin-*` names so they can never be mistaken for a
provider header; a test asserts every `*day*` header carries that prefix.

## Documented differences from the real service

1. Model IDs are whatever `config/relay.yaml` says; no real model list.
2. Token counting is `len(json)/4` for prompts and `max_tokens` for completions.
   Not a tokenizer.
3. `max_tokens` is charged to the TPM bucket **up front**. Call 1's deficit-time
   reading was 76 + 80 with only 41 tokens generated (n=2 reservations, one model,
   one prompt shape). Whether unused cap is later refunded is **OPEN (Q-06)**, hence
   `standin.refund_unused_cap` (default false, labelled an assumption).
4. Daily reset is a rolling 86400 s window, not a wall-clock boundary.
5. No context-length limit is enforced (Q-12 unmeasured).
6. Authentication is not checked.
