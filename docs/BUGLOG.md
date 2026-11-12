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

## BUG-015 · L2 eval · M3 was answerable but had an empty gold
**Cause.** M3 ("what problem does full-duplex dialogue modelling solve") was typed
`single` and given `gold: []`. Its gold chunk exists and states the answer
verbatim: `moshi-v1:s1:c0002`, "fundamentally turn-based, assuming that dialogue is
a sequence of well-defined single-speaker segments".
**Effect.** M3 counted as an unanswerable question, inflating the false-answer rate
and deflating recall. Every retrieval number in P3 was wrong by one to three
questions until it was fixed.
**How it was found.** The new `scripts/check_questions.py` rejected `type=single`
with empty gold. The fault was invisible to every other check.
**Fix.** Gold set from a verbatim-verified quote; the checker now enforces that
only `ambiguous` and `unanswerable` may have no gold, and that every gold id
resolves against the index.
**Lesson.** The same class of error as BUG-003, caught by the same class of check.
A metric that cannot distinguish "no gold" from "gold not found yet" will silently
report a number.

## BUG-016 · L6 checker · `reply_type` fell back to the terminal name
**Cause.** `kind = t.get("reply_type") or t.get("terminal")`. With abandonment
introduced, an abandoned request legitimately has `reply_type: null` — and the
fallback turned that null into `"abandoned"`, which is not a permitted reply. Five
of eight requests were reported as H1 violations when nothing was sent at all.
**Fix.** An explicit `reply_type: null` is now a distinct case: legal when the
terminal is `abandoned`, and a violation otherwise ("sent nothing but was not
abandoned"). A *missing* key still falls back, so older logs keep checking.
**Lesson.** `or` is the same hazard as BUG-003/015: it silently treats "absent" as
a value. An explicit null and an absent key must not be conflated.

## BUG-017 · L3 gateway · stream timestamps stamped at replay, not arrival
**Cause.** Frames were buffered until the first content frame arrived, then replayed
through the consumer, which stamped `first_delta` and `model_ttft` as it read them.
Both landed microseconds apart, destroying the distinction the two fields exist to
make — and the role-only frame's true arrival time was lost entirely.
**Fix.** `consume()` stamps each frame as it arrives. The role-only frame sets
`first_delta`; the first non-empty content delta sets `model_ttft`.
Observed separation after the fix: 184 ms vs 196 ms.
**Test.** `test_stream_timestamps_are_stamped_at_arrival_not_at_replay`.

## BUG-018 · L4 pipeline · quote verification bypassed normalisation, discarding correct answers
**Cause.** The citation-building loop tested `sentence in chunk.text` on raw text.
A streamed draft joins words with spaces where the PDF chunk has a newline (SSE
deltas are word-shaped; the newline between two PDF lines belongs to no delta).
The raw test failed, `citations` came out empty, and the reply became
`passages_only / no citations` — **a correct answer discarded as unverifiable**.
**Effect.** Streaming answered 1/12 where buffering answered 6/12 on identical
questions. Reproducible, deterministic.
**Fix.** Route the test through `contains_quote`, the same NFKC + de-hyphenation
normalisation the verifier has used since BUG-006.
**Why it hid for two phases.** A buffered draft happened to reproduce the source's
newline exactly, so draft and chunk matched byte for byte. The stand-in was
accidentally perfectly aligned. Any real model that wraps a line would have
triggered it.
**Test.** `test_verification_normalises_whitespace_between_draft_and_source`,
`test_streamed_and_buffered_pipelines_agree`.

## BUG-019 · (number unused — no bug was ever recorded here)
**Status: NOT A BUG. This number is deliberately left empty.**

The sequence runs BUG-018 → BUG-020 with no BUG-019 entry anywhere in this file or in
the git history. An audit of the repository could not determine what, if anything,
BUG-019 was meant to record, so **no entry has been invented for it**. Renumbering
BUG-020..028 to close the gap was rejected: those numbers are cited from
`docs/DECISIONS.md`, `docs/STREAMING.md` and several commit messages, and renumbering
would silently break every one of those references.

If the supervisor has a record of what BUG-019 was, add it here. Otherwise treat the
gap as a gap: the count of real bugs in this project is the number of headings that
have a cause, not the highest number used.

## BUG-020 · L4 instrumentation · "verification cost" was actually generation time
**Cause.** `user_ttft - model_ttft` was reported as verification cost. But H1 forbids
showing anything unverified, so the pipeline cannot observe the user-facing answer
until the draft is COMPLETE — the whole of the remaining generation sits inside that
gap. Measured as "verification": 0.10–0.32 s.
**Actual.** With `generation_end` stamped: generating 0.196–0.259 s, **verifying
0.0003–0.0006 s**. The claim was wrong by ~300×.
**Fix.** `Attempt.t_generation_end`, stamped when the stream closes, logged on
`attempt.end` and split out in `reply.ready` as `generating_s` / `verifying_s`.
**Why it matters beyond the number.** The wrong figure supported a wrong argument
("verification is why we need a degradation ladder"). Verification is free; the
ladder would have to act on generation, and it would have to act before the call.
**Lesson.** A two-point measurement cannot attribute a gap that contains a third,
unmeasured phase. Stamp the boundary.

## BUG-021 · L2 retrieval · chunk size was compared with context size varying
**Cause.** The three settings were compared at fixed `k=4` while mean chunk length
grew 570 → 845 → 1110 characters, so 1200/200 retrieved 4260 chars against 2254 for
600/100. The "best setting" was substantially a "biggest context" result.
**Fix.** `--char-budget` (default 3600, the 900/150 fixed-k mean) truncates retrieved
hits to an equal character count and reports mean chars per answer so the cap is
auditable.
**Result.** 1200/200 falls from 55% to 45% recall at equal characters, below
900/150's 50%. The committed setting survives; the ORIGINAL JUSTIFICATION for it
("1200 leads on both recall and MRR, but by noise") was wrong in both directions.
**Lesson.** When comparing two configurations, list every quantity that differs
between them, not just the one named in the experiment title.

## BUG-022 · probe · Q-06 reported a verdict from a negative measurement
**Cause.** The TPM-drop test compared `remaining_tokens` between two responses and
picked whichever of two candidate costs was closer. It was seen producing a verdict
from a drop of **-50** — the bucket refilled between reads, so no consumption was
measured at all. Both candidate costs were also built on a `len/3` estimate that gave
88 tokens against 117 actual.
**Fix.** Three conditions before any verdict: reads under 1 s apart, positive drop,
a measured prompt overhead. Otherwise `INCONCLUSIVE (refill confound)` with the
failing condition named. The estimate is replaced by the first real
`usage.prompt_tokens`.
**Lesson.** "Which of these two numbers is closer" is not a test when both are
unvalidated and the measurement may be zero.

## BUG-023 · probe · an aborted run was charged and recorded nowhere
**Cause.** `main()` did `except CeilingReached: return 1` above the block that writes
`docs/TOKEN_LEDGER.md`. Every path that returned early — ceiling abort, exception —
skipped the write, so tokens taken from a finite daily budget left no trace. The
ceilings exist to protect a ~200K-token day; a ceiling that silently loses spend
makes the budget unaccountable exactly when it matters most.
**Fix.** The ledger write moved into a `finally`. The abort reason and exit code are
computed before the return and stamped onto the row (`abort`, `label="aborted: …"`),
so an aborted run is visible as aborted rather than looking like a short successful
one. Regression test drives the abort through a fake transport and asserts the charge
lands.
**Second bug found by the fix.** `Ledger.__init__(self, path=LEDGER_PATH)` bound the
path as a *default argument*, evaluated once at class definition. Patching the module
constant in a test therefore did nothing and the test wrote **234 fictional tokens to
the real ledger**. Default is now `None`, resolved at call time, and an autouse guard
in `tests/conftest.py` redirects the path for every test.
**Mutation check.** The regression test was verified to fail against the *original*
control flow, not just to pass against the fix. Restoring `return 1` inside the
`CeilingReached` handler and moving the ledger block back out of the `finally` makes it
fail with `ABORTED RUN LOST ITS CHARGE -- the (o) bug is back`, the ledger still reading
`# TOKEN LEDGER`. A first attempt at that check passed spuriously: the only thing
reverted was the `finally` placement, but `main()` now computes `exit_code` instead of
returning early, so the trailing block still ran. Position of the `finally` is not what
fixes this — *not returning early* is. Both halves are load-bearing.
**Lesson.** A budget ledger must be written in a `finally`, and a constant used as a
default argument is not configurable.

## BUG-024 · tests · a unit test spent real Groq tokens
**Cause.** `test_go_without_key_exits_2` deleted `GROQ_API_KEY` and ran `main()`. The
probe then called `load_env()`, which read the developer's real `.env` and put a real
key straight back into `os.environ`. The "no key" test ran the probe for real: 117
tokens were charged (`runs/probe_20261111T064821Z`). Absence of a credential was
being treated as a safety mechanism, but the credential was only absent from the
process environment — not from disk.
**Fix.** Three layers, because one was clearly not enough. (1) `RELAY_NO_DOTENV=1`
disarms the loader, set by an autouse fixture for the whole suite. (2) An autouse
guard fails any test that opens a socket to a non-localhost host, so a future leak
fails loudly instead of spending money. (3) The probe takes `--env K=V,…` and
resolves its key and base URL against that mapping, making the "no key" path testable
with no environment at all.
**Proof.** With a real `.env` present in the repo, `pytest -q` twice: 278 passed both
times, `sha256(docs/TOKEN_LEDGER.md)` identical before and after
(`ec97edd0…33cc63`), zero files under `runs/` modified. The guard was verified to
fail a direct `socket.connect(("api.groq.com", 443))` and an `httpx.get` to the same
host while still permitting `127.0.0.1:8009`.
**Lesson.** Tests that run production entry points need the network denied, not just
credentials withheld.

### The (n) proof, as run

How the real `.env` was **simulated**: a single line, in the repository root, containing
an obviously fake key —

    printf 'GROQ_API_KEY=FAKE_key_for_the_test_suite_only\n' > .env

That is the whole simulation. It reproduces the condition that caused the bug (a `.env`
on disk holding a key-shaped value that the loader will find) without ever possessing a
real credential, so nothing in the run could have spent money even if the guard had
failed. `.env` is git-ignored (`.gitignore:1`), so it never enters a commit.

| Where | Condition | Result |
|---|---|---|
| `/home/user/vaan` | `.env` present | `280 passed` — run 1 |
| `/home/user/vaan` | `.env` present | `280 passed` — run 2 |
| fresh clone of `06a1a11` | `.env` present, 3 PDFs | `280 passed` |
| fresh clone, second run | `.env` present | `280 passed`, `runs/` identical (same 4 files, same mtimes) |

`sha256(docs/TOKEN_LEDGER.md)` was `56addc254168c35f…` before both runs and after them,
in both the working copy and the clone. A file-by-file `mtime` listing of `runs/` before
and after one run `diff`ed clean.

The guard was proved to *fire*, not merely to be installed: a throwaway test that opened
`socket.connect(("api.groq.com", 443))` failed with `RuntimeError: test attempted a live
network connection to 'api.groq.com'`, and an `httpx.get` to the same host failed the
same way, while a `connect(("127.0.0.1", 8009))` was still permitted so the stand-in
suite keeps working.

## BUG-025 · gateway · the busiest code path ignored rate-limit headers
**Cause.** `consume()` parsed SSE frames and threw away the HTTP response headers, so
`_streamed_call` never called `learn_limits`/`reconcile`. Every pipeline answer is
streamed, so the local bucket was reconciled only on the probe's non-streamed calls —
the gateway's rate-limit behaviour depended on which function happened to be running.
**Fix.** `consume()` takes the headers and returns them on `StreamTimings`; the
streamed branch reconciles exactly as the buffered branch does. `Budget.reconcile` now
moves in both directions (capped by `tpm_used_floor`) and `settle()` releases a
reservation when its response arrives.
**Proof the test catches it.** With the streamed reconciliation removed the (m) test
fails as `relay.gateway.gateway.DeadlineExceeded: local TPM budget exhausted: 7700+350 > 8000`
after 25 answers whose provider-reported window was still full. Restored: `4 passed`.
**Side finding.** The two new tests passed alone and failed in the suite with
`RuntimeError: There is no current event loop` — `asyncio.get_event_loop()` is
deprecated and does not survive another test closing the loop. `asyncio.run` fixes it.
**Lesson.** A test that only passes when run alone is not passing.

## BUG-026 · L6 observability · `flush()` waited for the dequeue, not the write
**Symptom.** `tests/test_events.py::test_backend_is_not_reserved_at_the_shared_channel`
failed **only inside the full suite**, on the supervisor's machine (Python 3.14.8:
278 passed, 1 failed, 1 skipped). `read_events(lg.path)` came back empty immediately
after `lg.flush()`. It passed alone (5×) and across the whole file (26 tests).

**Cause — the hypothesis, confirmed.** `flush()` polled `while not self._q.empty()`.
That asks whether the queue has work *waiting*, not whether work has been *done*. The
writer thread can already have dequeued an item and still be serialising it, so the
queue reads empty with an event in flight; the poll exits, the file is short by one
line, and the event lands a moment later. Under a full suite the process is busy
enough for the scheduler to preempt the writer inside that window.

**Proof, three ways.**
1. *Noise first: not reproducible by load.* 2 000 quiet iterations and 500 iterations
   with 4 CPU-burning threads and a 200-event-deep queue lost **0** events. The window
   is microseconds, so luck is the wrong instrument.
2. *Mechanism, deterministically.* Widening only the writer's `get()` → `write()` gap
   (a 50 ms `json.dumps`) made the old `flush()` return in **1.1 ms with 0 events
   readable**, and the event then appeared. If `flush()` waited for the write, widening
   that gap could not change anything. It changed everything.
3. *Mutation check.* New regression test
   `tests/test_flush_race.py::test_flush_waits_for_the_write_not_the_dequeue` widens the
   same gap and asserts the line is readable after `flush()`. Against the restored old
   poll it fails `assert 0 == 1`; against the fix it passes.

**Fix.** `queue.SimpleQueue` → `queue.Queue` (unbounded, so `put()` stays non-blocking
and `emit()` remains an enqueue — `test_emit_does_not_block_caller` still holds at 2000
emits < 1 s). The writer now calls `task_done()` after each write, in a `finally` so the
sentinel is covered too, and `flush()` calls `join()` before flushing the handle.
`close()`-then-`flush()` was re-checked twice for hangs: no hang.

**Why it mattered.** A short read is indistinguishable from a missing event, and every
report number comes from this file. This is the same failure class as BUG-001/002:
correct-looking cleanup code and an API that made the wrong thing natural.

**Not fixed here.** `commit 8f0ff4b` (the supervisor's 351-row ledger) is not on origin;
`docs/TOKEN_LEDGER.md` was left untouched by this change, by instruction.

## BUG-027 · L2 eval · `evaluate()` still scored ambiguous questions as false answers
**Cause.** `sweep()` was corrected to split answerable (A) / unanswerable (U) /
ambiguous (T), and `docs/P3_RETRIEVAL.md` was rewritten to say `false_answer` is
measured against **4**, not 7. But `evaluate()` — the function that *writes*
`data/eval/retrieval_results.json` — still built its denominator as "every question
without gold", which is 4 U + 3 T = **7**. So the committed artifact and the page
that describes it disagreed, and a test pinned only `sweep()`, so nothing caught it.

**Effect, and its direction.** At the committed operating point the stored file says
`false_answer = 1/7 = 14.3%`; the correct figure is `1/4 = 25.0%`. The bug made the
system look **better than it is** at exactly the metric the gate is judged on — the
failure direction that matters, because it flatters the design. A high score on an
ambiguous question is *correct behaviour* (several answers are defensible), so
counting it as a fault both inflated the denominator and, worse, blurred the one
distinction the page spends a section establishing.

**Fix.** `evaluate()` splits the pool exactly as `sweep()` does, returns
`n_ambiguous` and `ambiguous_admitted` alongside, and never counts T in
`false_answer`. New test
`test_evaluate_counts_ambiguous_separately_from_unanswerable` pins `evaluate()`
(previously only `sweep()` was pinned).

**Proof.** Verified on a synthetic 10-chunk corpus (the PDFs are unavailable in the
sandbox, so the real index could not be rebuilt). With one admitted ambiguous
question and one refused unanswerable one: old code reports `false_answer = 0.5`
(1/2), fixed code reports `0.0` (0/1). Recomputed from the *existing* stored rows,
the corrected rates are 0.0% / **25.0%** / **25.0%**.

**Not done, deliberately.** `data/eval/retrieval_results.json` was **not**
regenerated — the corpus is absent here and the instruction was not to regenerate
data files without it. `docs/P3_RETRIEVAL.md` carries the status box and the
recomputed table instead, so the page cannot silently claim agreement with a file
that still disagrees. Regenerate with `python -m scripts.retrieval_eval` once the
indexes exist.

**Lesson.** Fixing a metric in the function you are reading is not fixing the metric.
`grep` every producer of the number, and pin the one that writes the artifact.

## BUG-028 · L4 pipeline · a measured threshold had a magic-number fallback
**Cause.** `pipeline.py` read `cfg.get("retrieval.gate_threshold", 15.0)` while
`config/relay.yaml` commits **15.86** — a value measured in P3 and justified in D-015.
Deleting or renaming that one key would have moved every gate decision to 15.0, a
number nobody measured, with no error and no log line. This is precisely the class
rule 4 exists to prevent, and it sat in the file that implements the gate.

**Same hazard, second site.** `gateway.retry_credit_floor` was read with a `0.0`
default against a committed `1.0` ("a cold gateway may retry its first failure").
With `0.0`, the first failure after a key rename would silently stop being retried.

**Fix.** `cfg.require()` for both. `gateway.request_deadline_s` / `user.patience_s`
keep documented fallbacks — they are null *by design* until measured — but the
pipeline now records `deadline_source` (`measured` | `standin`) instead of hiding the
choice behind `or`, and absent-key handling was made consistent (`cfg.get(k, None)`),
because `Config.get` raises on a missing key but returns None on a present-and-null one.

**The durable half.** `test_no_numeric_literal_fallback_for_measured_config_keys` is an
AST walk over `relay/` and `scripts/` that flags any `cfg.get(key, <number>)` where
`key` is a **non-null number in config that differs from the literal**. Provisional
keys are listed explicitly in `_PROVISIONAL` with a note, so adding one is a visible
decision rather than a pattern exemption. Mutation check: restoring
`cfg.get("retrieval.gate_threshold", 15.0)` makes it fail with
`('relay/pipeline/pipeline.py', 90, 'retrieval.gate_threshold', 15.0, 15.86)`.

**Lesson.** The lint that existed checked model ids and URLs. The numbers were the
unwatched half — and a default is a magic number wearing a safety argument.

## BUG-029 · L3 evaluation · two "15.86"s were different thresholds
**Cause.** `sweep()` derives its candidate thresholds from scores rounded to three
decimals, compares raw scores against them, then stores `round(t, 3)`. One answerable
query (A8) has a raw score a hair below the committed `15.86` that rounds to exactly
`15.86`. So a sweep point displaying **15.86** — which is really A8's own score —
counts A8 as gated-in, while `evaluate()` comparing against the config value `15.86`
counts it as refused. Same printed threshold, different answer: **5/20 vs 6/20**.

**Consequence.** `docs/P3_RETRIEVAL.md` quoted `5/20` for all three operating points,
transcribed from the sweep. The correct column is **6/20, 6/20, 5/20** — which is what
`retrieval_results.json`'s own `false_abstain` field (0.30, 0.30, 0.25) always said.
The doc contradicted the artifact it was describing.

**Not affected.** The false-answer rate. No U or T score lies within 0.01 of its
threshold at any setting, so 0.0% / 25.0% / 25.0% holds under either reading. This
bug moved a count of *refusals*, not the headline rate.

**Fix.** `sweep()` now stores `exact` (the full-precision value the comparison used)
alongside the display `threshold`. `scripts/make_tables.py --check` re-derives every
false-answer figure from the stored rows and fails when a doc row disagrees; it
catches the historical `12.5%` if reintroduced.

**Why it survived.** Two artifacts disagreed and both were arithmetically correct, so
neither looked wrong in isolation. The discrepancy was only visible from a third
place that recomputed from the rows — which is what `make_tables.py` is for.

## BUG-030 · L4 streaming · the SSE parser destroyed the evidence
**Cause.** `parse_sse_line` returned `None` for every line it did not recognise —
malformed JSON, an HTML error page injected by a proxy, a truncated frame, a bare
non-SSE line. The caller could not distinguish "not parseable" from "nothing yet", so
a corrupted stream and a slow model produced the **same** `TimeoutError`. The bytes on
the wire were discarded at the first line and were unrecoverable afterwards.

**Why it matters here specifically.** This project's rule is that a number must be
traceable to a line in a file. A failure whose only record is "no content arrived"
violates that: the post-mortem cannot answer what the provider sent.

**Fix.** `parse_sse_line_verbose` classifies **every** line and never raises:
`frame | done | blank | comment | event | malformed`, keeping `raw` verbatim and the
decode error. `consume()` records lines into a **bounded** buffer (cap 40, plus a
liveness marker), counts them, and raises `StreamProtocolError` — distinct from
`TimeoutError` — when a stream opens with garbage or consists only of it. Legal but
non-data lines (`:` comments, `event:`/`id:`/`retry:` fields) are recognised, so
tolerance means *understanding more*, not *ignoring more*.

**Reaches the log.** `attempt.end` now carries `sse_raw`, `n_sse_lines`,
`n_sse_malformed`, `sse_saw_done` and `protocol_error`. Pinning this in a unit test
alone would not have helped: the post-mortem reads the JSONL, so the evidence had to
travel there. `tests/test_sse_end_to_end.py` asserts it does.

**Also surfaced.** `saw_done` records whether `[DONE]` arrived. A stream that ends
without it was cut short; the old code could not tell a complete answer from a
truncated one.

**Mutation check.** Reverting to a parser that drops `raw` and treats garbage as a
quiet stream fails 2 of the 19 tolerance tests. **Sandbox:** the stand-in run
(8 lines, 0 malformed, `saw_done`) ran here and is filed UNCALIBRATED.

## BUG-031 · stand-in · a day-limit 429 advertised a retry 60 s away
**Cause.** `_r429` had one `day` branch shared by the daily-request and daily-token
buckets. It hard-coded `retry-after: 60`, always set `type: "requests"`, and always
emitted `x-ratelimit-reset-tokens` computed from the **minute** bucket — so exhausting
the *daily* budget told the client to come back in under a minute. The minute and day
buckets reset 1440 minutes apart, and the header said the wrong one.

**Why it mattered.** The gateway's minute-vs-day classification reads exactly these
fields. A test of "does a day 429 stop the caller retrying?" was really testing the
stand-in's arithmetic, and would have passed or failed for reasons unrelated to the
gateway. Q-09 ("what does a day 429 look like?") could not be approached against an
instrument that answers the question wrongly by construction.

**Fix.** `_r429(kind)` takes `minute | day_tokens | day_requests` and reports the
refusing bucket's own reset. The daily-token bucket, which Groq is not believed to
expose, publishes its counters as `x-standin-*` so they cannot be mistaken for
provider headers.

**Mutation check.** Restoring `wait = 60.0` for `day_tokens` fails
`test_day_token_429_does_not_advertise_a_minute_reset`.

**CALIBRATION.** Everything about the *real* service in this area remains UNVERIFIED:
header names and the per-day reading (Q-04), whether `retry-after` is always present
(Q-11), and what a real day 429 looks like (Q-09). `docs/STANDIN.md` now carries a
claim-by-claim table separating what the docs say from what has been observed — which,
for all of it, is nothing.

## BUG-032 · L3 evaluation · `top_score` was stored rounded while `gated_in` used the raw value
**Cause.** `evaluate()` computed `gated_in = top >= threshold` from the **raw** score
but stored `"top_score": round(top, 3)`. The artifact was therefore not internally
consistent. Two committed rows prove it:

```
M1 @ 600/100: top_score 15.477, threshold 15.477, gated_in False
A8 @ 900/150: top_score 15.86,  threshold 15.86,  gated_in False
```

Both are correct arithmetic — the raw score was a hair under and only *rounded* to the
threshold — but a consumer recomputing the gate from the stored row gets the opposite
answer. This is the same defect as BUG-029 one layer down: BUG-029 was `sweep()`
rounding a **threshold**, this is `evaluate()` rounding a **score**. Fixing one did not
fix the other, which is why the question was worth asking twice.

**Fix.** `top_score` is now the raw float; `top_score_display` carries the rounded form
for tables.

**Mutation check — and a false first pass.** The first version of the regression test
used a round threshold (2.5). Restoring the rounding did **not** fail it, because no
score in that corpus sat in the gap between a value and its 3dp form near 2.5. The
test now asserts the corpus even *has* such a gap and places the threshold strictly
inside it: `disp0 < threshold <= raw0`. With that, restoring `round(top, 3)` fails
`test_stored_score_reproduces_the_gate_decision`, and the fix passes. Recorded because
a mutation check that passes is evidence about the test, not the code.

## BUG-033 · stand-in · the TPM bucket was a fixed window and reserved the wrong amount
**Cause, part 1 — the wrong model.** `Bucket` reset `used` at a boundary and reported
`reset = reset_at - now`, which right after a request is ~60 s. The transcribed real
observations show `reset-tokens` of **1.17 s / 1.335 s / 0.96 s**, and in every case
`reset = deficit / (8000/60)`. The service refills **continuously**; the stand-in
emptied once a minute. It got `remaining` exactly right (7844) and `reset` wrong by a
factor of ~50 — and `reset` is the number the gateway uses to decide when to retry.

**Cause, part 2 — the wrong amount.** The stand-in reserved `max_tokens` alone.
Call 1's deficit was 156 = prompt **76** + cap **80**, with only 41 generated, so the
service reserves prompt + cap and reserves the cap in full. Charging cap only made the
stand-in advertise remaining 7920 against the service's 7844 — same order, wrong
number, which is how a wrong model survives a spot check.

**Cause, part 3 — headers taken after the sleep.** Even with the reservation fixed, the
advertised remaining came out cap-only because headers were computed *after* the TTFT
sleep, by which time ~24 tokens had already refilled and cancelled the prompt half.
The observation `reset 1.17 s = 156/133.3` exactly implies the advertised deficit is the
reservation **undecayed**, so the snapshot is now taken at reservation time.

**Fix.** `RefillBucket` (continuous refill, `reset = deficit / rate`), reservation =
`prompt + cap`, rate-limit snapshot at reservation. `standin.refund_unused_cap`
(default `false`, matching the observation) makes the refund an explicit switch:
Q-06 is settled for *reservation* by n=4 but the refund branch was never isolated.

**Evidence.** `tests/test_standin_observed.py` (7 tests) feeds the four transcribed
points to the bucket and also **records the refutation** of the fixed-window model, so
the change cannot be quietly reverted by someone who assumes a bucket is a window.
`runs/standin/refill_bucket.json` (UNCALIBRATED) shows the stand-in's residual
`7896` vs `7844` is fully explained by `len(json)//4 = 24` versus a real 76-token
prompt — the documented tokenizer difference, not a bucket error.

## BUG-034 · L4 streaming · `StreamProtocolError` had no handler, so the evidence died at the raise
**Cause.** 5c introduced `StreamProtocolError` and the tolerant parser, but *nothing in
the gateway caught it*. Two consequences: the exception escaped `Gateway.call()` as an
unhandled error instead of a terminal reply, and — worse — no `attempt.end` was written
for the failing attempt, so the offending bytes the parser had carefully retained were
discarded at the moment they became useful.

**Fix.** The gateway now handles it alongside the HTTP-error path: outcome
`SERVER_ERROR` (retryable, and deliberately **not** `TIMEOUT` — a wrong-looking stream
and a slow model want different responses), breaker records a failure, `_next_delay`
applies so the deadline still binds, and the error propagates only when no retry is
available. `StreamProtocolError` carries its partial `StreamTimings`, because
`consume()` raises before control returns and the attempt would otherwise never see
them.

**No new `Outcome` member.** `Outcome` lives in `contracts.py`; `SERVER_ERROR` is the
right severity and `protocol_error` keeps it distinguishable in the log.

**Also.** `usage_from()` now checks `x_groq.usage` as well as top-level `usage`
(UNVERIFIED location, from memory). A wrong lookup makes `tokens_in/out` null and the
TPM reconciliation a silent no-op, so both are accepted, top-level first.

**Groq-shaped stream.** A test pins the real shape — role chunk first, **reasoning
deltas before content**, no usage chunk, then `[DONE]` — as a valid, complete stream
with `n_malformed == 0`. Reasoning deltas must not become `model_ttft`: the first
*content* token is the honest one, or TTFT is measured against the start of the
thinking block and flatters the system.

**Mutation check.** Removing the handler fails 2 of 3 tests.

## BUG-035 · L4 gateway · `attempt_timeout_s` was read by nobody, and could not have worked
**Cause, part 1.** `gateway.attempt_timeout_s` was declared in `config/relay.yaml` with
a comment saying the P1 probe would set it. **No code read it.** A configuration key
that nothing consumes is worse than a missing feature: it reads as implemented.

**Cause, part 2 — the reason reading it would not have been enough.** The buffered
attempt's `TimeoutError` handler ended with `raise DeadlineExceeded(...)`
*unconditionally*. So even once the value was plumbed through, the **first** slow
attempt would have terminated the request: a per-attempt timeout would have behaved
exactly like an outer deadline. The feature is not "add a timeout", it is "make one
kind of expiry retryable and the other terminal", and only the second half changes
behaviour.

**Fix.** `_attempt_budget()` returns `min(remaining deadline, attempt_timeout_s)` and
says which limit produced it. Taking the minimum is what makes it impossible for a
per-attempt cap to *extend* the outer deadline. On expiry, `timeout_limit` decides:
`attempt_timeout` → run `_next_delay` and retry; `deadline` → raise as before. Each
expiry writes its own `attempt.end` with `attempt_timed_out` and `timeout_limit`, so a
retry storm cannot masquerade as normal traffic.

**Preserved.** The pre-existing `max(1.0, …)` floor: a nearly-spent deadline still gets
one real attempt rather than an instant timeout. I removed it by accident mid-change,
caught it by diffing against the old line, and put it back.

**Config.** `attempt_timeout_s` stays **null** — no per-attempt cap until the probe
measures the fast path's p99. An invented value would silently cut healthy requests,
and that is not a failure this project could detect after the fact.

**Sandbox.** `STANDIN_HANG_S=30`, cap 0.5 s: 2 attempts, each with its own
`attempt.end`, both `attempt_timed_out=True`, one `retry.sleep`, then a clean
surface. Filed UNCALIBRATED — 0.5 s exercises the mechanism, it is not a recommendation.

## BUG-036 · L4 gateway · one shared budget for every model
**Cause.** `Gateway` held a single `Budget` built from `models.small.tpm/rpd`. Every
model id drew from it. `models.buckets_separate_per_model` existed in
`config/relay.yaml` and was read by nothing — the same pattern as BUG-035.

**Why one shared bucket is the wrong default.** It fails in the *expensive*
direction: exhausting the large model refuses calls to the small one, so the caller is
told there is no budget when there is. A shared bucket cannot "lose" capacity by being
too generous; it loses it by refusing requests that would have succeeded.

**Fix.** `BudgetBook` holds one `Budget` per model id, and each reconciles from its own
response headers. `buckets_separate_per_model` is honoured for `true`/`false`.
**`null` resolves to separate**, and the reasoning is stated in the class: when the
answer is unmeasured, prefer the assumption that fails loudly rather than the one that
silently refuses capacity.

**UNVERIFIED, and labelled as such.** Whether Groq's per-model buckets are genuinely
independent has never been observed — `buckets_separate_per_model` stays `null` until
the probe's `buckets` mode exhausts one model and watches the other's headers. The
class docstring says UNVERIFIED and names the key, and a test asserts both survive.

**Back-compat.** Legacy `gw.budget.tpm_used` reads resolve to the most recently used
model's bucket, because before this change there was exactly one bucket and that is
what such a read meant. `__getattr__` only fires when normal lookup fails, so real
attributes always win.

**Caught by the existing lint.** My first version hard-coded a model id as the default
bucket key; `test_no_hardcoded_model_or_url_in_package` failed and the id now comes
from `models.small.id`.

**Mutation check.** Forcing `for_model()` to always return the shared bucket fails 2 of
6 tests.

## BUG-037 · L6 pipeline · no cache, no coalescing, and a naive version of either is a bug
**Missing, not broken.** The pipeline ran once per question, every time. Nothing was
cached, and two concurrent identical questions each ran a full pipeline: two drafts,
two verifications, two bills.

**Two designs that would have been wrong, and why the chosen one is not.**

1. *Cache keyed on the question.* An answer produced by a different index, a different
   `top_k`, or a different prompt would be served as this one, and nothing downstream
   could detect it. The key here includes the normalised question **plus** index id,
   `top_k`, both model ids and a `prompt_version`, and a test asserts that changing
   any one of them produces a different key.

2. *Cancel the shared run when any waiter leaves.* That makes the system's behaviour
   depend on its least patient caller: one impatient user kills the request for
   everyone sharing it. Coalescing is refcounted, and **only the last departure
   cancels**. Pinned by `test_one_follower_abandoning_does_not_cancel_the_others` and
   `test_last_waiter_abandoning_cancels_the_pipeline`.

**Only `VerifiedAnswer` and `NoEvidence` are cached.** `PassagesOnly(budget_gone)` is
a statement about *our* state at that instant; caching it would convert a transient
shortage into a durable refusal that outlives the shortage. An unverified answer is
also the one thing this project must never replay as a result.

**Test-visible evidence.** `cache_hit` and `coalesced_follower` are on the returned
value *and* emitted to the event log. The 20-question burst is asserted there — one
leader, 19 followers — because the event log is what a post-mortem reads, and a
counter only proves an object's internal bookkeeping.

**A bug found in my own first draft.** The leader never decremented the waiter count,
so the refcount could never reach zero and the pipeline could never be cancelled at
all — abandonment would have looked implemented and been dead. Fixed to exactly one
`leave` per waiter on every path.

**Mutation checks.** Cancelling on any departure fails the "one follower leaving"
test; caching every terminal fails the "only verified" test.

**UNMEASURED.** `ttl_s: 900` is a placeholder with no basis: how long an answer stays
valid depends on the corpus, which changes only when papers change. The stand-in run
used no model at all, so it measures the mechanism and **not** any token saving.

## BUG-038 · L5 admission · no queue at all, and "reject when full" is a trap
**Missing.** `gateway.queue_max` was null and read by nothing. Every request went
straight to a model call; nothing bounded concurrency and nothing could shed load
before spending a token.

**The trap.** The obvious implementation of "reject when full" is a bare rejection --
return `None`, or an HTTP 429 with no body. That violates the project's terminal rule:
a dropped request leaves **no terminal event**, and a post-mortem cannot distinguish
it from a crash. It also gives the caller no way to tell "retry shortly" from "this
will never work".

**Chosen behaviour.** A shed request gets `PassagesOnly(queue_full)` — the passages
that would have answered, at **zero tokens**, with the reason recorded. Two shed
reasons are distinguished: `queue_full` (no room) and `would_wait_past_deadline`
(the expected wait exceeds the caller's remaining patience). The second refuses
**before** queueing, so a request never spends its remaining patience to reach a
refusal it could have had immediately.

**Expected wait, not depth.** A queue of depth 3 is harmless at 40 ms per request and
fatal at 30 s. The check converts depth into expected wait using a moving average of
observed service time, and compares that against the deadline.

**Two bugs found by my own tests.**
1. `release()` freed the slot and the waiter re-incremented it. Between those two
   points another `acquire()` could see a free worker and take it — the queue
   over-admitted. The slot is now **transferred** in `release()` and the waiter does
   not increment.
2. My first `expected_wait_s` returned 0 for interactive requests regardless of depth,
   so a deep queue predicted no wait. Priority decides ordering among the queued; it
   cannot erase work already occupying the workers.

**`queue_max: null` does not become 0.** A capacity of 0 sheds every request as
`queue_full` — a production outage wearing the costume of a safety default. Null
resolves to a named provisional 32 and `capacity_was_provisional` is True so the log
can say so.

**Sandbox.** Forced to capacity 2 / 1 worker: 5 further requests → 5 shed as
`passages_only(queue_full)`, 5 terminals, **0 dropped without a terminal**, all 0
tokens. UNCALIBRATED — `workers`, `queue_max` and `service_estimate_s` are all
unmeasured.
