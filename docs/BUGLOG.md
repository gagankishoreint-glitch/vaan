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
