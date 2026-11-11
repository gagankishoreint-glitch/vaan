# P7 (minimal): abandonment cancels in-flight work — H4

The only P7 feature built. Exact cache and request coalescing were **not built**
(they remain on the "deliberately did not build" list, with the semantic cache).

```bash
python -m scripts.run_queries --limit 8 --patience 0.05 --run-dir runs/h4_abandon
python scripts/check_events.py runs/h4_abandon/events.jsonl
python -m scripts.analyze runs/h4_abandon --request A2
```
Observed: 5 of 8 abandoned at exactly 0.05 s, `violations=0`.

## What happens on abandonment

```
patience timer fires
  -> asyncio.wait_for cancels the draft coroutine
    -> cancels httpx request
      -> gateway catches CancelledError: marks the attempt `cancelled`,
         does NOT retry, does NOT spend retry credit, RE-RAISES
        -> scope.abandon("patience") -> pipeline returns reply=None
          -> send_reply(None, abandoned=True) -> terminal `abandoned`, reply_type null
```

The event log for an abandoned request:

```
attempt.end        A2  outcome=cancelled  t_end-t_sent=0.051s  status=null
request.abandoned  A2  reason=patience
request.end        A2  total=0.0526  working=0.0526
terminal           A2  terminal=abandoned  reply_type=null
```

Three details that are deliberate:

1. **Re-raise, don't swallow.** A caught `CancelledError` that is not re-raised
   leaves a task running for a user who has left. The gateway marks the attempt
   and re-raises so cancellation keeps propagating.
2. **`reply_type` is `null`, not `passages_only`.** Nothing is sent to nobody.
   `send_reply(None, abandoned=True)` is a second, explicit exit, and it *refuses*
   a non-null payload — an abandonment that still carries an answer is a bug.
3. **No retry.** A cancelled attempt must not consume retry credit; the user's
   departure is not the provider's fault.

## The measured limit: cancellation does not refund tokens

Against the stand-in, 10 identical calls with two patience settings:

| patience | completed | admitted by provider | day tokens charged |
|---|---|---|---|
| 5.0 s | 10 | 10 | **2000** |
| 0.05 s | **0** | 10 | **2000** |

**Cancelling stops the wait and stops all further work on that request, but the
tokens already reserved are still spent.** Zero calls completed and the token bill
was identical.

This is the honest statement of H4:

> Abandonment stops the client waiting and prevents any further work being
> scheduled for that request. It does **not** reduce the tokens already committed
> at the provider for the in-flight call. Under a reserved-up-front TPM model
> (UNVERIFIED, Q-06), an abandoned request costs the same as a completed one.

The consequence for the budget is direct: **user abandonment does not save tokens.**
Only *not sending the request* saves tokens. That is why the gate and the retry
budget matter more than the abandonment path for cost control, and why the
degradation ladder would need to act *before* the call, not after the user leaves.

## Failure-path tests (the one per mechanism rule)

- `test_abandonment_cancels_in_flight_and_returns_no_reply` — a handler that never
  completes; asserts `terminal == "abandoned"` and `reply is None`.
- `test_send_reply_refuses_a_payload_on_an_abandoned_request` — pins the second
  exit so a future refactor cannot start sending answers to departed users.
- `test_checker_accepts_a_null_reply_type_only_for_abandoned` — a null reply type
  is legal for `abandoned` and a violation for anything else.
