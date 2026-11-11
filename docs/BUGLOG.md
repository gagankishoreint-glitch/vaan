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
