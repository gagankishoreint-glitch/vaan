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
| `per_minute_limit` | 8000 | limits page |
| `per_day_limit` | 200000 | limits page |

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

`[UNVERIFIED]` — **nothing in this section has been observed against the real
service.** No real call has been made (no key is used in this work). The stand-in is
built from the Groq docs table and from inference.

| claim | status | where |
|---|---|---|
| header names `x-ratelimit-limit/remaining/reset-{tokens,requests}` | docs table | `_headers()` |
| `*-requests` describes a **day**, `*-tokens` a **minute** | **UNVERIFIED (Q-04)** | `parse_rl_headers` docstring |
| `max_tokens` is reserved against TPM up front | **UNVERIFIED (Q-06)** | `complete()` note, item 3 below |
| every 429 carries `retry-after` | **UNVERIFIED (Q-11)** | `_r429()` always sends it |
| a day-limit 429 is distinguishable from a minute one | **UNVERIFIED (Q-09)** | `_r429()` `type` field |

**What changed (5e).** `_r429` used to have a single `day` branch that always
reported `retry-after: 60`, always `type: "requests"`, and always sent
`reset-tokens` computed from the **minute** bucket — so a per-day exhaustion told the
client to retry in under a minute. It now takes `minute | day_tokens | day_requests`
and reports the refusing bucket's own reset. `[VERIFIED in the stand-in]` by
`tests/test_standin_buckets.py` and by `runs/standin/bucket_429.json`
(UNCALIBRATED).

**Stand-in-only headers.** The stand-in enforces a day *token* bucket that Groq is
not believed to expose. Its counters are emitted under `x-standin-*` names so they
can never be mistaken for a provider header; a test asserts every `*day*` header
carries that prefix. The gateway ignores unknown headers, so this costs nothing.

**Still absent.** The stand-in does not model a per-request cost that differs from
`max_tokens`, so it cannot settle Q-06 on its own even when the probe runs.

## Documented differences from the real service

1. Model IDs are whatever `config/relay.yaml` says; no real model list.
2. Token counting is `len(json)/4` for prompts and `max_tokens` for completions.
   Not a tokenizer.
3. `max_tokens` is charged to the TPM bucket **up front**, mirroring the
   *unverified* hypothesis that TPM is reserved rather than charged on usage (Q-06).
4. Daily reset is a rolling 86400 s window, not a wall-clock boundary.
5. No context-length limit is enforced (Q-12 unmeasured).
6. Authentication is not checked.
