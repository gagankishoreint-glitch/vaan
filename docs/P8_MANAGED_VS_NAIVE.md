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

**Goodput was EQUAL: 200 answers for both policies.** Naive did not answer a single
additional question. Every extra request it sent bought nothing.

### Both headline numbers are functions of configuration, not of the policy

This matters more than the table, because it is the difference between a result and
an artefact:

**(1) Amplification 1.67 = (successes × 1 + failures × `naive_max_attempts`) / users.**
With `naive_max_attempts = 5`: (200×1 + 40×5)/240 = 400/240 = **1.67**. Exactly the
observed figure. Naive's amplification is not an emergent property of contention; it
is arithmetic on the attempt cap. Change the cap to 3 and it becomes (200+120)/240 =
1.33 with no other change to the system.

**(2) Naive p95 0.814 s = (max_attempts − 1) × backoff + work.**
(5−1)×0.2 s + 0.014 s work = **0.814 s**. Exactly the observed figure. The tail is
`naive_backoff_s × (naive_max_attempts − 1)`, because a giving-up request sleeps
every backoff in sequence and the p95 request is the one that exhausted its retries.

So neither number measures "the harm of naive retry" in any general way. What the
table legitimately shows is narrower and still worth having: **naive retry spent 400
provider requests to produce the same 200 answers that managed produced with 200
requests**, and the size of the overspend is set by two config values. A report
claiming "naive is 76% worse" from this would be describing my settings.

`amplification` is HTTP requests per user request. Managed stays under 1 because
local admission control refuses some calls before sending (see below); naive has no
local budget, so it sends everything and retries the refusals.

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

**Shows.** Naive retry spends strictly more provider requests for strictly the same
goodput. With `naive_max_attempts=5` and 0.2 s backoff it spends 2× the requests and
a tail of `backoff × (attempts−1)`. Both magnitudes are set by those two values, not
measured from the system.

**Does not show.** Anything about Groq's actual behaviour, real token accounting
(the stand-in charges `max_completion_tokens` up front, which is an UNVERIFIED
hypothesis about TPM reservation), or real latency.

## The local-budget subtlety this exposed

That managed sends *fewer* requests than it serves (0.83×) looks like a win but
is not free: those 40 "gave up" requests were refused locally before they were
ever sent. Managed trades user-visible refusals for provider protection. Whether
that is the right trade is a product decision, not a measurement — and it is why
the pipeline's failure path is a `PassagesOnly` reply rather than an error.
