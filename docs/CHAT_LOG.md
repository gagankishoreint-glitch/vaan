# CHAT LOG

Compressed record of supervisor <-> architect decisions. Not a transcript: only what
changed the design, plus the reasoning that is not captured in DECISIONS.

---

## 2026-11-11 · P0

**Given.** PRD v0.1, the repo layout, `.env.example`, `.gitignore`, `config/relay.yaml`,
`relay/clock.py`, `relay/contracts.py`, `relay/events.py`, `relay/ratelimit_headers.py`,
`tests/test_headers.py`, and the task to reach "pytest -q green" plus a complete event log.

**Confirmed before writing code.** The three PDFs are the exact versions required. Stamps read
from page 1, not from the filename: `arXiv:1706.03762v7 [cs.CL] 2 Aug 2023` (15 pp),
`arXiv:2410.00037v1 [eess.AS] 17 Sep 2024` (66 pp), `arXiv:2507.07955v2 [cs.LG] 15 Jul 2025`
(39 pp). Hashes in `data/papers/SHA256SUMS`.

**Deviations from the spec, each with a reason.**
1. *I can run code here.* The role brief says to label everything UNTESTED and hand over
   commands. In this environment I ran the suite instead. Where something could only be
   reasoned about (the Groq header semantics, the probe results), it is still labelled
   UNVERIFIED and pointing at an OPEN_QUESTIONS ID.
2. *`Chunk` left byte-identical.* I wanted a `title` field for citation rendering. Changing a
   frozen contract on day one is exactly the thing rule 1 says to announce first, so paper
   titles go in a module-level registry at P2 instead, keyed by `Chunk.paper`. Contract
   change avoided, question logged as Q-19.
3. *Added three modules not in the spec*: `relay/config.py` (so "no magic numbers" is
   enforceable and a null raises), `scripts/check_events.py` (invariants derived from the
   written file), `scripts/smoke_p0.py` (the vertical slice for P0: log -> file -> verdict).
4. *Added `finish()` to `RequestScope`* after BUG-001. Announced here because it extends a
   shared contract (`relay/events.py`) — it is additive, no caller changes.
5. *Added `RetryPolicy` and `is_reply()` to contracts.* Additive; `is_reply()` is the single
   runtime test of H1 so the send boundary cannot drift from the type definition.

**Rejected on purpose.**
- Any default for a null in `config/relay.yaml`. `Config.require()` raises instead.
- A `Chunk.title` field (see 2).
- Implementing queue/breaker/budget skeletons now. P5 owns them; writing them early is the
  phase-skipping the working rules forbid, and every one of them needs a measured threshold
  that does not exist until P1.

**Found by running, not reviewing.** BUG-001 (terminal before `request.end`) and BUG-002
(`flush()` after `close()`). Both are in the BUGLOG with regression tests.

**Awaiting your call.** Q-16 (`patience_s` as assumption vs measurement) and Q-17 (which two
non-goals) are the two answers that change what P5 and P8 build.

**Next.** P1 probe: 19 questions, one script, artifacts under `runs/probe_*`. I will not write
the probe runner until you say the ledger allocation in `docs/TOKEN_LEDGER.md` is acceptable,
because the probe is the first thing that spends real tokens.
