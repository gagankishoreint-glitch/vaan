# P8: managed vs naive retry, same schedule

**Every number here is UNCALIBRATED.** The stand-in's TTFT, token rate and limits
are provisional values (it prints a warning per null at startup). These figures
are properties of `relay/standin/server.py`, not of Groq. The *comparison* between
the two policies is meaningful; the absolute level is not.

```bash
.venv/bin/uvicorn relay.standin.server:app --port 8009
python -m scripts.load_compare --rps 40 --duration 6 --max-tokens 40 --out runs/compare_overload
```

Same precomputed arrival schedule for both policies (seed 7). The only thing that
differs between the two rows is the retry decision.

## Overload: 240 arrivals at 40 rps, `max_completion_tokens=40`

| policy | users | provider calls/s | goodput | gave up | p50 | p95 | amplification |
|---|---|---|---|---|---|---|---|
| managed | 240 | **33.5** | 200 | 40 | 0.183 s | **0.184 s** | 0.83 |
| naive | 240 | **58.9** | 200 | 40 | 0.183 s | **0.814 s** | 1.67 |

Reproduced twice with identical figures.

**Reading it.** Goodput is the same 200 answers. Naive sends **76% more HTTP
requests** to get there and its p95 is **4.4× worse**. The extra requests are
pure waste: they are retries of calls whose 429 already told them the bucket was
empty. Every one of them makes the bucket empty for longer, which is why the tail
grows even though the count of successful answers does not.

`amplification` is HTTP requests per user request. Managed stays under 1 only
because local admission control refuses some calls before sending; naive has no
local budget, so it sends everything and then retries the refusals.

## Steady (60 arrivals at 10 rps) and burst (24 at 6 rps): no difference

| shape | managed p95 | naive p95 | amplification (both) |
|---|---|---|---|
| steady 10 rps × 6 s, 8 tokens | 0.185 s | 0.185 s | 1.00 |
| burst 6 rps × 4 s, 8 tokens | 0.186 s | 0.185 s | 1.00 |

**The policies are indistinguishable when nothing pushes back.** No 429 ever
occurs, so no retry decision is ever taken. This is the honest framing for the
report: the retry policy does not matter under normal load, and matters a great
deal under overload. A benchmark that only ran the steady shape would conclude
the choice of retry policy was irrelevant.

## What this does and does not show

**Shows.** Naive retry converts a rate limit into additional load. Under overload
it raises request pressure by 76% and p95 by 4.4× while producing zero extra
answers.

**Does not show.** Anything about Groq's actual behaviour, real token accounting
(the stand-in charges `max_completion_tokens` up front, which is an UNVERIFIED
hypothesis about TPM reservation), or real latency.

## The local-budget subtlety this exposed

That managed sends *fewer* requests than it serves (0.83×) looks like a win but
is not free: those 40 "gave up" requests were refused locally before they were
ever sent. Managed trades user-visible refusals for provider protection. Whether
that is the right trade is a product decision, not a measurement — and it is why
the pipeline's failure path is a `PassagesOnly` reply rather than an error.
