# P7 (minimal): abandonment cancels in-flight work — H4

The only P7 feature built. Exact cache and request coalescing were **not built**
(they remain on the "deliberately did not build" list, with the semantic cache).

```bash
python -m scripts.run_queries --limit 8 --patience 0.05 --run-dir runs/h4_abandon
python scripts/check_events.py runs/h4_abandon/events.jsonl
python -m scripts.analyze runs/h4_abandon --request A2
```
Observed: 5 of 8 abandoned, **every one at 0.050 s of a 0.05 s patience budget**
(recorded totals: 0.0523–0.0530 s), `violations=0`.

> **The patience used was 50 ms, not 5 ms.** Earlier prose in this project said
> "5 ms"; the event log says otherwise and the event log is the source. The
> `request.abandoned` reason now records the value (`patience_0.05s`) so this
> cannot be misread again.

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

## What cancellation does, and the one thing this measurement cannot tell you

Against the stand-in, 10 identical calls with two patience settings:

| patience | completed | admitted by provider | tokens debited |
|---|---|---|---|
| 5.0 s | 10 | 10 | **2000** |
| 0.05 s | **0** | 10 | **2000** |

Zero calls completed, identical token figure.

> **This is a property of the stand-in's debit-at-admission design, and is
> UNVERIFIED for Groq.**
>
> `relay/standin/server.py` charges its token buckets the moment a call is
> *accepted*, before any generation happens (which mirrors the reserve-up-front
> hypothesis, Q-06 — itself unverified). Under that design the token count is
> decided at admission, so of course cancellation cannot change it. The experiment
> is therefore measuring the stand-in's accounting model, not a fact about the
> provider. A service that bills on tokens actually generated would show a
> different number, and we have no observation either way.
>
> **Do not put "abandonment does not save tokens" in the report as a finding.** The
> reportable statement is that the cost of an abandoned request is
> **unmeasured** — P1 observes `usage` on a completed call but cannot observe the
> usage of one we cancelled mid-flight without spending real tokens to find out.

What *is* established, from the log rather than from accounting: cancellation
stops the client waiting (0.05 s instead of 0.18 s), stops any retry (no retry
credit spent), and leaves `attempt.outcome = cancelled` with `status = null`. The
request is over; whether the provider still bills for it is open.

## Failure-path tests (the one per mechanism rule)

- `test_abandonment_cancels_in_flight_and_returns_no_reply` — a handler that never
  completes; asserts `terminal == "abandoned"` and `reply is None`.
- `test_send_reply_refuses_a_payload_on_an_abandoned_request` — pins the second
  exit so a future refactor cannot start sending answers to departed users.
- `test_checker_accepts_a_null_reply_type_only_for_abandoned` — a null reply type
  is legal for `abandoned` and a violation for anything else.
