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

Observed on the stand-in, 6 answered questions:

| req | first_delta | model_ttft | user_ttft | verification |
|---|---|---|---|---|
| A2 | 0.204 s | 0.215 s | 0.412 s | **0.197 s** |
| A3 | 0.184 s | 0.196 s | 0.453 s | **0.257 s** |
| A4 | 0.185 s | 0.197 s | 0.456 s | **0.259 s** |
| A5 | 0.185 s | 0.196 s | 0.408 s | **0.211 s** |
| M2 | 0.184 s | 0.196 s | 0.516 s | **0.320 s** |
| H1 | 0.184 s | 0.196 s | 0.294 s | **0.099 s** |

**Verification costs more than the model's time to first token.** The model produces
its first content token 196–215 ms after the request; the verified answer is not ready
until 294–516 ms. The user waits longer for us to check the answer than for the model
to start writing it.

This is the single most useful number P7 produced, and it is the argument for the
degradation ladder existing at all: the cheapest latency win available is not a
faster model, it is sending a verified-in-code answer sooner. (Which the pipeline
already does — verification here is code checks only, no LLM verify call. With an
LLM verify step enabled the gap would be larger still.)

**UNCALIBRATED.** The stand-in's token rate is a provisional 90 tok/s. The *shape* of
this result — verification dominating TTFT — is structural, because verification
runs strictly after generation. The magnitudes are not provider measurements.

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
