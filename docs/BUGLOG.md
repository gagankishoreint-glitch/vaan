# BUGLOG

Bugs found, with the layer, the cause, and the regression test that now pins them.
Layer vocabulary: L0 runtime · L1 transport · L2 provider protocol · L3 gateway ·
L4 pipeline · L5 request/user · L6 observability · L7 harness.

The two entries below were **found by running the code**, not by review, and both were
in P0 scaffolding I had just written. They are recorded because the same ordering and
shutdown mistakes will reappear in P5/P6 under concurrency.

---

## BUG-001 · L6 observability · terminal event emitted before `request.end`

**Symptom.** `tests/test_smoke_p0.py` failed with
`TerminalEventAlreadyEmitted: q-good: event 'request.end' emitted after terminal event`.

**Cause.** The smoke script called `scope.terminal(...)` and then emitted `request.end` with
the latency decomposition. The scope guard rejected it — correctly. The ordering was wrong,
not the guard: "exactly one terminal, and nothing after it" means the totals must be logged
first. This is an easy trap because the totals are only known at the end of the request.

**Fix.** Added `RequestScope.finish(terminal, total_elapsed_s, waiting_s, working_s,
retrying_s, **fields)` which emits `request.end` then `terminal`, and made it the only
supported exit (DECISIONS D-002).

**Regression tests.** `tests/test_events.py::test_finish_emits_end_before_terminal`,
`::test_emit_after_finish_raises`, `::test_finish_twice_raises`, and the end-to-end
`tests/test_smoke_p0.py::test_smoke_run_round_trips_through_checker`.

**Still exposed?** Yes, in a different form: a future streaming path that wants to log after
the reply is sent. If that is needed, `terminal` moves to `request.closed` (see D-002).

---

## BUG-002 · L0 runtime · `flush()` after `close()` raised on a closed file

**Symptom.** `ValueError: I/O operation on closed file` raised from `EventLog.flush()` in a
`finally` block, turning a clean shutdown into a crash.

**Cause.** `close()` already joins the writer thread and closes the handle, so the flush in
`flush()` was redundant — but callers reasonably wrote `close(); flush()`. The `finally` order
is the natural one to write, so the API was the problem.

**Fix.** `flush()` returns immediately when `self._closed`, and `close()` is idempotent.
Both are now asserted.

**Regression tests.** `tests/test_events.py::test_flush_after_close_is_noop`,
`::test_close_is_idempotent`, `::test_emit_after_close_raises` (the one case that *must*
still raise: emitting into a closed log is data loss, not a harmless no-op).

**Note on a non-bug.** A test I wrote, `test_no_orphan_tbd_comments`, failed three times in a
row on `config/relay.yaml` — but it was the *test* that was wrong (it matched any line
mentioning the key, so a `# set by ...` comment on a neighbouring line satisfied it). It was
tightened to require the note on the null's own line, and the YAML was then fixed for real.
Recording it here because a test that passes for the wrong reason is worse than no test.

---

## Open risks not yet bugs

| Risk | Layer | Why it matters | Planned cover |
|---|---|---|---|
| Two coroutines `await` between budget check and take | L3 | Bucket overspend (rule 9) | P5: synchronous `take()` with no await; a test that asserts no `await` on the path |
| `retry-after` honoured while holding a concurrency slot | L3 | Slot starvation under burst | P5: release slot before sleeping; assert via event timestamps |
| Terminal event written but reply send fails | L5 | User gets nothing while log says answered | P6: send then terminal? — decide in P6, see D-002 |
| Clock skew between harness and server | L7 | Arrival-rate error in the report | P8: measure send-time drift, report it |
| Nightly TPD reset at an unknown hour | L3 | Wrong rollover → false "budget gone" | P1 probe open question Q-09 |

---

# Bugs in the *spec*, not the implementation

These were written into the P0 specification by the assistant and would have shipped
if nobody read them closely. They are recorded separately because the lesson is
different: implementation bugs are caught by tests, spec bugs are caught by reading,
and they are the cheapest bugs to fix and the most expensive to trust.

## BUG-003 · L2 provider protocol · `parse_duration` accepted hostile floats

**Layer.** L2 (provider protocol), parsing untrusted header values.

**The bug, as specified.**
```python
try:
    return float(s)                  # plain seconds, e.g. retry-after
except ValueError:
    pass
```
`float()` accepts `"nan"`, `"inf"`, `"-5"`, `"1e5"`, `"Infinity"`. A `retry-after: inf`
becomes a valid number and every "can we retry before the deadline?" comparison becomes
trivially false; a `nan` makes every comparison false *and* every `min`/`max` return its
other argument, so the gateway silently mis-schedules. Neither raises, so neither would
show up in a test that only checks the accept path. My own P0 tests missed it for exactly
that reason: they tested the values I expected, not the values a hostile or broken
proxy could send.

**Fix.** Explicit `_PLAIN = re.compile(r"\d+(?:\.\d+)?", re.ASCII)` for the
plain-seconds branch, plus `_duration()` which rejects non-finite and negative values
*before returning*, so even a future regex edit cannot leak a bad number. `re.ASCII`
also stops `\d` matching non-ASCII digits (`"٥"` → 5) which `float()` accepts.

**Regression tests.** `test_parse_duration_rejects_hostile_values` (7 values incl.
`nan`/`inf`/`-inf`/`Infinity`/`1e5`/`1m30`), `test_parse_duration_still_accepts_plain_seconds`,
plus the new ASCII-digit case in `test_bad`.

**Why it matters here rather than in theory.** This is the one field that decides
whether we retry into a day-limit. A wrong-but-plausible number is worse than `None`,
because `None` is the path we already guard (raw string kept, `RATE_LIMITED_UNKNOWN`).

## BUG-004 · L6 observability · caller fields silently overwrote the envelope

**Layer.** L6 (observability).

**The bug, as specified.** `EventLog.emit` built the record as
`{"type": ..., "t_mono": ..., **fields}`, so a call with `run_id=`, `t_mono=` or
`backend=` overwrote the reserved key with no error. The envelope is what every report
number is derived from (`D-001`); a silent overwrite is corruption that looks like data.

**Fix.** `RESERVED_FIELDS = {type, t_mono, t_wall, run_id, backend}` and a
`ReservedFieldError` on collision. `req_id`, `t_sent`, `t_first_byte` and friends are
**not** reserved — they are legitimate per-event fields, and over-reserving broke
`attempt.end` the moment I tried it (`BUG-005` below). The set is exactly what the
envelope writes.

**Regression tests.** `test_reserved_field_collision_raises` (5 hostile keys),
`test_req_id_is_not_reserved`, `test_attempt_timestamps_are_not_reserved`.

## BUG-005 · L6 observability · `backend` meant two things; one silently won

**Layer.** L6, discovered only because of BUG-004's fix — the new guard turned a
*successful* `attempt.start` into an exception, which is how we learned the field was
being clobbered.

**The bug.** The envelope writes `backend` = the log's run-wide backend
(`"standin"`), while `Attempt.backend` = the backend that served *that attempt*
(`"groq"`). Both went into the same key. For two years of P0 the event log would have
said every attempt ran on the stand-in during a real run — the single field the
naive-vs-managed comparison groups by. A silent overwrite of the one thing being
measured.

**Why the tests did not catch it.** `test_attempt_lifecycle_fields_survive_json`
asserted on `outcome`, `rl_headers_raw` and token counts — every field *except* the one
that collided, because I wrote the assertion from the same mental model that produced
the bug.

**Fix (supervisor decision, D-008).** Envelope keeps `backend` (run scope);
attempt events carry `attempt_backend` (attempt scope); a terminal event carries
`primary_backend` = majority backend with first-appearance tie-break. Checker gains
**I7**: an attempt event must carry `attempt_backend`, and it must agree with the
envelope unless that request genuinely mixed backends.

**Regression tests.** `test_attempt_backend_is_the_attempt_value_and_backend_is_run_scope`,
`test_primary_backend_is_majority`, `test_primary_backend_tie_falls_back_to_first_appearance`,
`test_primary_backend_none_without_attempts`, and four `I7` cases in
`tests/test_check_events.py` including the exact BUG-005 shape.

---

## BUG-006 · L4 pipeline · chunk overlap started mid-word (H2)
**Layer.** L4 (pipeline), ingest.

**Cause.** `start = end - overlap` landed inside a word, so the overlap head was a
word fragment. A quote spanning that boundary is a substring of *neither* chunk, so
`verify()` would reject a correct answer and `PassagesOnly` would replace a good
reply — a hard-rule H2 failure presenting as a mysterious quality problem.

**Why tests missed it.** The first test asserted "every word appears in some chunk".
That assertion **cannot fail**: even a splitter that hard-cuts mid-word loses no
characters. It was a tautology dressed as a check.

**Fix.** Snap the next start forward to the first whitespace boundary.

**Regression tests.** `test_no_chunk_starts_or_ends_mid_word`,
`test_adjacent_chunks_overlap_by_a_whole_word` (asserts real words are shared).

## BUG-007 · L4 pipeline · 17.6% of chunks contain a table caption, unflagged
**Layer.** L4 (pipeline), ingest quality.

**Cause.** No caption detection. `attn-v7:s3.4:c0000` was flagged `ok` while
containing `Table 1: Maximum path lengths...` followed by mangled header cells.

**Why it matters.** This is the mechanism behind "the library misleads the retriever",
and it was invisible: 50 of 449 `ok` chunks were contaminated.

**Fix.** `caption` / `caption_lead` flags. Chunks are kept deliberately — they are the
evidence the retrieval section cites.

**Regression test.** `test_real_corpus_caption_rate_is_measured` pins the rate so a
chunking change that doubles it is visible.

## BUG-008 · L4 pipeline · heading detection required bold; moshi/hnet are not bold
**Layer.** L4 (pipeline), ingest.

**Cause.** Three separate errors in one condition: (a) the size test was only applied
inside the one-line branch, so a bare `2.2` line never qualified; (b) the two-line
heading path required the *next* line to be bold, which it never is in moshi/hnet;
(c) the whole-detection gate required bold, and 12pt regular headings are the norm.
Result: **hnet produced 0 chunks and moshi 7 sections** out of ~30.

**Fix.** Heading = bold OR clearly larger than body; the split-heading path accepts a
non-bold title; body-sized numbered lines are accepted via the monotonicity rule.

**Regression tests.** `test_size_only_heading_not_bold`,
`test_body_sized_numbered_heading_accepted_by_sequence`,
`test_split_heading_across_two_lines`, and the integration guard
`test_real_pdfs_produce_sane_sections`.

---

# P4-P6 bugs (compressed mode)

## BUG-009 · L3 gateway · retry budget computed per-call, so it was always zero
**Cause.** `max(1, int(self._calls * ratio))` was evaluated inside each call, so
with `ratio=0.1` the limit was `int(0.1)=0` on call 1 and `int(0.2)=0` on call 2 —
a retry could never happen until the 10th call, and `max(1, ...)` then allowed
exactly one for the rest of the run.
**Fix.** An accruing credit that grows by `retry_budget_ratio` per call and is
spent one unit per retry, plus `gateway.retry_credit_floor` so a cold gateway can
retry its first failure.
**Lesson.** A budget expressed as a *rate* must be integrated, not re-derived from
a counter each time.

## BUG-010 · L3 gateway · reconcile mixed two different limits
**Cause.** `provider_used = self.tpm - remaining_tpm` reconstructed the provider's
usage using *our* limit. When the two differed (a large local budget against the
stand-in's 8000), `remaining=0` became `used=10**9` and every subsequent request
was refused locally as "TPM exhausted" — a self-inflicted outage that looked like
correct rate limiting.
**Fix.** Learn the provider's advertised limit from `x-ratelimit-limit-*`, convert
`remaining` to a *fraction*, and apply that fraction to our own limit. Reconciling
without a learned limit is now a no-op.
**Test.** `test_budget_reconcile_uses_provider_ratio_not_our_limit`,
`test_budget_reconcile_without_learned_limits_is_a_noop`.

## BUG-011 · L4 pipeline · terminal `reply_type` named the terminal state
**Cause.** The terminal event carried `reply_type=Terminal.ANSWERED` (`"answered"`)
while the checker's permitted set is `verified_answer | no_evidence |
passages_only`. Four of eight requests were reported as H1 violations — the
checker was right and the pipeline was wrong.
**Fix.** `reply_type_of(reply)` names the reply *class*. `terminal` and
`reply_type` are different axes: how the request ended vs what was sent.

## BUG-012 · L4 pipeline · transport errors escaped without a terminal event
**Cause.** An `httpx.ConnectError` propagated out of `run_queries`, so a request
got `request.start` and `request.end` but no `terminal` — an I1 violation, and the
request would vanish from every report.
**Fix.** Transport failures are caught and converted into a `PassagesOnly` reply.
The user still gets an honest answer, and the log still has exactly one terminal.
**Test.** The checker on a run with the stand-in down reports `violations=0`.

## BUG-013 · L3 gateway · naive retry was recursive and crashed the process
**Cause.** `_maybe_retry` called `self.call(...)` on failure. Against a persistent
429 that never yields a 200, retry-after was ignored and the deadline was never
checked, so the call chain grew until Python's stack died: **489 HTTP requests
then `RecursionError`**.
**Fix.** `call()` is a single bounded `for attempt_no in range(1, max_attempts+1)`
loop. Policy lives in `_next_delay()`, a pure function returning either `None`
(stop) or `(seconds, why)`. Naive: `naive_max_attempts=5`, fixed 0.2 s backoff,
no local budget, no breaker, ignores retry-after — all from config.
**Why it matters.** The old code made the *demonstration of harm* its own harm:
the naive policy took the whole process down, which would have been reported as a
gateway bug rather than as a policy result.
**Test.** `test_naive_is_bounded_and_never_recurses` asserts exactly
`naive_max_attempts` HTTP calls and no RecursionError.

## BUG-014 · L4 stand-in · stale process read `max_tokens` as zero
**Cause.** The gateway moved to `max_completion_tokens` while the running
stand-in still read `max_tokens`. It got `None`, charged **1 token** per call, and
so its 8000 TPM bucket never emptied. Managed vs naive came out *identical*.
**Fix.** Stand-in reads `max_completion_tokens` with `max_tokens` as fallback.
**Lesson.** A green comparison against a stale binary is indistinguishable from a
null result. Both policies reported the same numbers; that was the tell.
