# P8: LOAD GENERATOR AND THE THREE SHAPES

Open-loop: arrival times are precomputed and never adjusted for completions, so a
slow server cannot slow the offered load. Drift is reported to prove it.

```bash
curl -s -X POST localhost:8009/__reset
python -m scripts.loadgen --shape steady   --rps 3  --duration 6 --max-tokens 8  --out runs/shape_steady
python -m scripts.loadgen --shape burst    --rps 2  --duration 4 --burst 25 --max-tokens 8 --out runs/shape_burst
python -m scripts.loadgen --shape overload --rps 40 --duration 6 --max-tokens 40 --out runs/shape_overload
```

## Measured (stand-in, full pipeline, after `/__reset`)

| shape | planned | statuses | drift p95 | first 429 |
|---|---|---|---|---|
| steady 3 rps × 6 s | 18 | 18 × `200` | **41 ms** | none |
| burst 2 rps + 25 | 33 | 33 × `200` | **12 ms** | none |
| overload 40 rps × 6 s | 240 | 200 × `200`, **40 × `429`** | **2 ms** | request **200** |

**Drift stays in the tens of milliseconds even at 40 rps**, which is the proof the
loop is genuinely open: the 40 ms of the steady run is scheduler jitter, not
queueing (overload's drift is *lower* because there is nothing to wait on).

## The result that matters for the report

Overload shows **200 successes then a clean 429 wall** — the stand-in's 8000 TPM
bucket is consumed by exactly 200 calls at 40 reserved tokens. There is no
graceful degradation: once the bucket is empty every subsequent arrival is
refused. That is what the degradation ladder (P7, not built) exists to fix.

## A trap that cost me a run

An earlier set of three shapes reported **100% 429 from request 0** in every
shape. The cause was not the load generator: the stand-in's *day* bucket still
held 20 000 tokens from earlier hand-testing. `POST /__reset` fixed it. Any load
number is meaningless unless the server state is named alongside it — the run
directory now records the stats snapshot it started from.

## Naive retry vs the managed gateway

The comparison had to be isolated with `httpx.MockTransport` because against a
real server the local budget and the breaker both refuse *before* the retry
decision is reached — the retry policy is masked by admission control.

| policy | deadline | `retry-after` | HTTP calls | outcome |
|---|---|---|---|---|
| managed | 3 s | 5 s | **1** | `DeadlineExceeded` (clean refusal) |
| naive | 3 s | 5 s | **489** | **`RecursionError` — process crash** |

Naive retry honours neither `retry-after` nor the deadline, so a persistent 429
recursees until the stack dies. Against a real provider this is a self-inflicted
outage: 489 requests sent while the provider is explicitly asking for 5 s of
quiet. **Managed retry sends one request and returns an honest error.**

Reproduce: `bash runs/naive_vs_managed/run.sh`
