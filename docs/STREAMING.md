# Streaming and the three timestamps

**(f).** What "TTFT" means depends on where you measure it, and conflating the three
practical definitions makes latency numbers incomparable between reports. Streaming
exists here to *measure*, not yet to reduce latency: the pipeline still buffers the
whole draft and verifies it before sending anything.

```bash
.venv/bin/uvicorn relay.standin.server:app --port 8009      # has a streaming mode
python -m scripts.run_queries --limit 12 --stream --run-dir runs/stream
```

## The three stamps

| stamp | when | measured from |
|---|---|---|
| `first_delta` | first SSE frame of ANY kind, including a role-only frame with no content | request sent |
| `model_ttft` | first frame carrying non-empty CONTENT | request sent |
| `user_ttft` | first byte of the **verified** answer | request sent |

Ordering always holds: `first_delta ≤ model_ttft ≤ user_ttft`.

- `first_delta → model_ttft` is connection setup plus the model's own warm-up.
- `model_ttft → user_ttft` is **what verification costs the user**.

Observed on the stand-in, streamed drafts, 4 answered questions:

| req | model_ttft | generation_end | **generating** | **verifying** | user_ttft |
|---|---|---|---|---|---|
| A2 | 0.224 s | 0.420 s | **0.196 s** | **0.0006 s** | 0.421 s |
| A3 | 0.196 s | 0.455 s | **0.259 s** | **0.0003 s** | 0.455 s |
| A4 | 0.196 s | 0.454 s | **0.258 s** | **0.0004 s** | 0.454 s |
| A5 | 0.196 s | 0.404 s | **0.208 s** | **0.0003 s** | 0.404 s |

### A correction: verification is ~0.3 ms, not 0.1–0.3 s

An earlier version of this document said *"verification costs 0.10–0.32 s, more
than the model's TTFT"*. **That was wrong by roughly 300×.** It attributed the whole
`model_ttft → user_ttft` gap to verification, but that gap also contains the rest of
generation — and it must, because H1 forbids showing anything unverified, so the
pipeline cannot observe the user-facing answer until the draft is complete.

With `generation_end` stamped, the gap splits:

| phase | duration | share of user_ttft |
|---|---|---|
| first content token | 0.196–0.224 s | ~50% |
| **generating the rest** | **0.196–0.259 s** | **~50%** |
| **verifying (code only)** | **0.0003–0.0006 s** | **~0.1%** |

The user waits about half their time for the model to start, and about half for the
model to finish. Verification is free. So the latency lever is **generating fewer
tokens or streaming a partial answer sooner**, not making the verifier faster.

This also means the previous claim's *conclusion* was wrong even though the arithmetic
was right: "verification is the argument for a degradation ladder" is a
non-argument when verification is 0.3 ms. The real argument is that generation
dominates and H1 forces the user to wait for all of it.

**UNCALIBRATED.** The stand-in's 90 tok/s is an invented provisional value, so the
*split* is structural (verification runs after generation, and is pure CPU on a few
hundred characters) while the generation share is not a Groq measurement. Verification
cost does not depend on the provider at all; generation time does entirely.

## Where `user_ttft` lives, and why it is a separate event

`attempt.end` is emitted by the gateway **before** verification runs, and the event
log is append-only, so a value written to the `Attempt` afterwards would never reach
the log. `user_ttft` is therefore its own event:

```json
{"type":"reply.ready","req_id":"A2","attempt_id":"A2-draft-2",
 "t_sent":..., "first_delta_s":0.2036, "model_ttft_s":0.2151,
 "user_ttft_s":0.4122, "verify_cost_s":0.1971, "reply":"VerifiedAnswer"}
```

It is emitted only on the verified path. **Its absence is the correct value on any
other reply** — a `passages_only` response never had a verified answer, so it has no
`user_ttft`. Writing 0 there would be a lie.

## The bug this found (BUG-018) — worth more than the feature

Streaming changed nothing about the model's output, but it **broke verification**:
6/12 answered buffered, 1/12 streamed, on identical questions.

Cause: the verification loop tested `sentence in chunk.text` **raw**. A streamed
draft joins words with spaces where the PDF chunk has a newline (`4.5 million
sentence pairs` vs `4.5 million\nsentence pairs`), because SSE deltas are word-shaped
and the newline between two PDF lines belongs to no delta. The raw substring test
failed, the answer was discarded as unverifiable, and a **correct answer was thrown
away**.

The verifier itself already normalised (NFKC + de-hyphenation, BUG-006). This loop
bypassed it. Fixed by routing the quote test through `contains_quote`.

The lesson is not "streaming is hard". A buffered draft happened to preserve the
source's newline, so the fault was invisible for two phases and would have stayed
invisible until a real model wrapped a line differently — which is every model. The
stand-in accidentally produced byte-identical layout.

**Parity is now pinned by a test**: `test_streamed_and_buffered_pipelines_agree`
asserts the two modes reach the same terminal on the same question.
