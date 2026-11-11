# P6: PIPELINE + GATEWAY, MINIMAL FORM

## What runs

```
retrieve (BM25, k=4) -> gate (top-1 score >= 15.86) -> draft (1 LLM call)
   -> parse [chunk_id] citations -> verify code checks -> VerifiedAnswer
   -> any failure: PassagesOnly | NoEvidence
```

```bash
.venv/bin/uvicorn relay.standin.server:app --port 8009 &
.venv/bin/python -m scripts.run_queries --limit 8 --run-dir runs/p6_clean
.venv/bin/python scripts/check_events.py runs/p6_clean/events.jsonl
```

Actual output:

```
  A2   answered      ok                    0.21s cites=1
  A6   passages_only no citations          0.19s cites=0
  A7   passages_only gate_low_score        0.00s cites=0
answered 4/8  gold_hit 4/8
events=35 requests=8 violations=0
```

**Zero invariant violations** on the written log: one terminal per request, no
attempt after terminal, latency sums agree, every reply a permitted type.

## H1 is enforced at exactly one place

`relay/pipeline/pipeline.py::send_reply` rejects anything that is not
`VerifiedAnswer | NoEvidence | PassagesOnly`, and `mint_verified` is called only
from `relay/pipeline/verify.py` (AST-linted). A test feeds a bare string to
`send_reply` and expects `TypeError`.

## The verify failure path is real, not theoretical

The stand-in produces 20% deliberately unverifiable answers. Those never reach the
user as answers:

```
A6  passages_only  no citations   <- model cited nothing that existed
```

## Gateway behaviours implemented

| behaviour | where | tested |
|---|---|---|
| no bucket negative | `Budget.take` asserts | `test_budget_never_goes_negative` |
| check-and-take, no await between | `Budget.take` | (rule 9, by construction) |
| reconcile from headers, ratio-based | `Budget.reconcile` | `test_budget_reconcile_uses_provider_ratio...` |
| breaker closed/open/half-open | `Breaker` | `test_breaker_opens_after_threshold...` |
| never retry a day 429 | `_maybe_retry` | (code path) |
| never sleep past the deadline | `_maybe_retry` | observed: `retry-after would exceed the deadline` |
| transport error still terminates | `run_queries` | checker I1 |

## What is NOT implemented (deliberately, and to be listed as such)

- exact cache and request coalescing (P7)
- the degradation ladder L0-L3 (P7)
- streaming output to the user (the draft is non-streaming)
- the optional LLM groundedness check (code checks only)
