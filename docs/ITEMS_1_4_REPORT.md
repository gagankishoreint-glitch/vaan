# Items 1–4: what was fixed, what was proven, what was not

Scope: `78ea980`, `3068b2e`, `3379b8d`, `df9b668`, `82b216d`.

Every claim below says **where it was observed**. The sandbox has no PDFs, so
anything that needs the chunk index **did not run here**; those tests fail with
"PDFs missing" and are not counted as passes anywhere in this document.

---

## 1 · `flush()` waited for the dequeue, not the write — BUG-026

**The verdict: a real bug, correctly diagnosed, and the fix is proven.**

`flush()` polled `while not self._q.empty()`. That asks whether work is *waiting*,
not whether it is *done*: the writer can have dequeued an item and still be
serialising it, so the queue reads empty with an event in flight. `read_events()`
then sees a short file and the event appears a moment later.

**It is not a load bug, and that matters.** 2 000 quiet iterations and 500
iterations with four CPU-burning threads lost **0** events. A fix based on
"reproduce under load" would have been built on luck. The mechanism was proven
instead by widening only the writer's `get()` → `write()` gap: the old `flush()`
returned in **1.1 ms with 0 events readable**.

**Re-verified live just now, not from memory:**

| mutation | result |
|---|---|
| restore `while not self._q.empty(): pass` | `test_flush_waits_for_the_write_not_the_dequeue` **FAILS** |
| the fix (`join()` + `task_done()` in a `finally`) | **passes** |

The test asserts `assert 0 == 1` against the old code. It is a real regression test,
not a test that happens to pass.

**Why it mattered:** every report number comes from that file. A short read is
indistinguishable from a missing event.

---

## 2 · `top_score` stored rounded while the gate used the raw value — BUG-032

**The verdict: a real bug, and it was caught twice because the first test was
wrong.**

`evaluate()` computed `gated_in = top >= threshold` from the **raw** score but stored
`"top_score": round(top, 3)`. Two committed rows prove the artifact was not
self-consistent:

```
M1 @ 600/100: top_score 15.477, threshold 15.477, gated_in False
A8 @ 900/150: top_score 15.86,  threshold 15.86,  gated_in False
```

Both are correct arithmetic — the raw score sat a hair under and only *rounded* to
the threshold — but anyone recomputing the gate from the stored row gets the
opposite answer.

**Fix, as you directed:** `top_score` is the **raw float**; `top_score_display`
carries the rounded form for tables. Same defect as BUG-029 one layer down: that was
`sweep()` rounding a *threshold*, this is `evaluate()` rounding a *score*. Fixing one
did not fix the other.

**The false first pass.** The first regression test used a round threshold (2.5) and
restoring the rounding **did not fail it** — no score in that corpus sat in the gap
near 2.5. The test now asserts the corpus *has* such a gap and puts the threshold
strictly inside it (`disp0 < threshold <= raw0`). With that, restoring
`round(top, 3)` fails `test_stored_score_reproduces_the_gate_decision`.

Recorded deliberately: **a mutation check that passes is evidence about the test, not
the code.**

`sweep()` stores both `exact` (used for comparison) and `threshold` (display only,
3dp) for the same reason — two different thresholds printed as `"15.86"` with
different counts (5 vs 6 answerable refused).

---

## 3 · `evaluate()` scored ambiguous questions as false answers — BUG-027

`sweep()` had been corrected to split A / U / T; `evaluate()` had not, so an
ambiguous question reduced to "refused" was counted as a **false answer** — the most
damaging error class in the table. Fixed; ambiguous is now its own class.

**Test status: not run here** (needs the chunk index). The unit tests that drive
`evaluate()` with synthetic rows pass; the corpus-level assertion is PDF-blocked.

---

## 4 · Measured values had silent defaults — BUG-028, D-017

`pipeline` read `gate_threshold` as `cfg.get(..., 15.0)` against a committed
**15.86**. A missing key silently became a plausible number nobody chose, and the
report would have described a different system than the one that ran.

**Fix:** measured values have **no default**. A missing measured value raises; a
`null` means UNMEASURED and is handled explicitly at the call site. Enforced by a
lint rule in `tests/test_lint_rules.py` (77 lines) so it cannot regress quietly.

**Ran in sandbox:** `test_lint_rules.py` + `test_make_tables.py` + `test_flush_race.py`
→ **12 passed, 1 xfailed** (the xfail is intentional and marked).

---

## What ran, and what did not

| Evidence | Where |
|---|---|
| `test_flush_race` mutation → RED, fix → GREEN | **agent sandbox, re-run today** |
| `test_lint_rules`, `test_make_tables`, `test_flush_race` | **agent sandbox: 12 passed, 1 xfailed** |
| `top_score` / `sweep` stored fields inspected in source | **agent sandbox, today** |
| Corpus-level retrieval numbers | **NOT RUN — no PDFs in the sandbox** |
| The supervisor's 278-passed/1-failed run | **supervisor's machine (Python 3.14.8), not reproduced here** |

`data/papers/*.pdf` are absent in this sandbox and were **not** regenerated. Every
PDF-dependent test fails with an explicit "PDFs missing" error rather than skipping —
a suite that tests nothing must not report success.

## What can go in the report

- `flush()` was a dequeue-vs-write race, proven mechanistically, not by load.
- `top_score` is stored raw and `top_score_display` is display-only; the stored row
  now reproduces its own gate decision.
- Ambiguous questions are not false answers, in both `sweep()` and `evaluate()`.
- No measured threshold has a default; a missing value is an error, a null is
  UNMEASURED.

## What cannot

- Any retrieval metric from this sandbox — no corpus.
- The claim that the full suite is green. It is **not** here: 13 failed / 4 errors,
  all PDF-absence. The red test you told me not to loosen still fails only in the
  supervisor's full suite, and I have not touched it.
