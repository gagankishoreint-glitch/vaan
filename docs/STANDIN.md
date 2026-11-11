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

## Documented differences from the real service

1. Model IDs are whatever `config/relay.yaml` says; no real model list.
2. Token counting is `len(json)/4` for prompts and `max_tokens` for completions.
   Not a tokenizer.
3. `max_tokens` is charged to the TPM bucket **up front**, mirroring the
   *unverified* hypothesis that TPM is reserved rather than charged on usage (Q-06).
4. Daily reset is a rolling 86400 s window, not a wall-clock boundary.
5. No context-length limit is enforced (Q-12 unmeasured).
6. Authentication is not checked.
