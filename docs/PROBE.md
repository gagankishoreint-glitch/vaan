# P1 PROBE: run sheet

Read this top to bottom before running anything. The probe spends real tokens.

## 0. What I can and cannot do

I cannot reach `console.groq.com` or `api.groq.com` from this environment, so:

* **You** read the limits page and fill the values in `config/relay.yaml` (`# set by P1`).
* **You** run the probe and paste the artefacts back (they are key-scrubbed by design).
* **I** cannot verify a single Groq fact by running it. Everything in
  `docs/OPEN_QUESTIONS.md` stays OPEN until your paste lands.

## 1. Before the first real call

### Credentials: `.env` is now actually read

`scripts/probe.py` used to say "copy `.env.example` to `.env`" while reading only
`os.environ`, so following that instruction changed nothing. `relay/env.py` now loads
`.env` (working directory first, then the repo root) before anything is read.

```bash
cp .env.example .env
# edit .env: set GROQ_API_KEY and GROQ_BASE_URL
python -m scripts.probe --dry-run --plan-today 60000     # always first
```

Existing environment variables win over `.env`, so `GROQ_API_KEY=... python -m
scripts.probe` behaves as expected. `.env` is git-ignored.

Expect: `DRY RUN (no network)`, one line per planned request naming the cap field
(`max_completion_tokens=80 est≈88 tokens`), and `ledger not written`. **If any line
says REFUSED, read why before continuing** — that is the ceiling doing its job, not a
bug. A cap of 1 (the default when no plan is given) refuses everything, which is
correct.

## 2. Order (supervisor's, which is also the cheap-to-expensive order)

| # | Mode | ~tokens | Answers | Note |
|---|---|---|---|---|
| 1 | `models` | 0 | Q-01 | `GET /models`; no generation |
| 2 | `single` | ~300 | Q-02, Q-05, Q-06, Q-11 | 3 calls |
| 3 | `stream` | ~800 | Q-15 | verifies the SSE parser on real bytes |
| 4 | `reasoning` | ~3K | Q-07 | **UNVERIFIED param name** — see §4 |
| 5 | `bigctx` | up to ~240K | Q-12 | **own day**, see §5 |
| 6 | `cache` | ~1.2K | Q-13, Q-14 | same long prefix twice |
| 7 | `burst` | ~2K | Q-08, Q-10, Q-11 | provokes the per-minute 429 |
| 8 | `buckets` | ~1K | Q-03 | needs #7 to have 429'd |
| 9 | `rpd` | ~2K | Q-04, Q-09 | **last, deliberate, may end the day** |

Days 1-2 run modes 1-4 and 6-8. `bigctx` and `rpd` are separate, deliberate runs.

## 3. The commands

```bash
# day 1: cheap modes, hard ceiling 60K
python -m scripts.probe --go --max-tokens-total 60000 --timeout 30 --plan-today 60000 \
    --mode models --mode single --mode stream --mode reasoning --mode cache \
    --mode burst --mode buckets
```

Artifacts land in `runs/probe_<UTC>/`: one `<mode>.jsonl` per mode with every header,
full body on non-200, TTFT and inter-chunk gaps; `raw/` for verbatim bodies
(`models.json`, `burst_first_429.json`, `rpd_first_429.json`).

The run prints, per mode, which of Q-01..Q-19 it answered **with the evidence line**:

```
--- burst: open questions ---
  Q-10 ANSWERED  first 429 after 17 successes; headers={...}
      evidence: raw/burst_first_429.json
  Q-08 NOT answered -- no raw log line produced by this mode
```

`NOT answered` is a normal outcome. It means the mode did not produce evidence, and
the question stays open. I will not mark a question answered without a log line.

## 4. The one parameter I cannot name for you

`reasoning` needs a parameter name I do not know. Candidates, in the order the probe
tries them (`--reasoning-param`):

1. `reasoning_effort` with `low|medium|high`
2. `reasoning` with the same values
3. `reasoning.effort` (some APIs use a nested object; if so, the probe's flat key will
   400 and the body will say so)

**Where to confirm:** the chat-completions request schema in the API reference — look
for a field controlling reasoning/thinking depth, and its accepted values. **UNVERIFIED
until then.** The probe records a 400 verbatim in `raw/reasoning_<v>_error.txt` rather
than guessing again.

## 4a. `--token-param`: Q-06 must use the field the gateway sends

```
--token-param {max_completion_tokens,max_tokens}    default: max_completion_tokens
```

The generation cap can be sent as either field. **The gateway sends
`max_completion_tokens`**, so the probe defaults to it: Q-06 asks whether TPM is
charged on the cap up front, and that answer depends on which field the service
honours. Running Q-06 with `max_tokens` would describe a request shape the product
never makes.

Every planned line and every recorded `Result` logs `token_param` and the cap it
sent, so the artifact says which field produced the number.

**Q-06 must be re-confirmed with `max_completion_tokens`.** Any earlier Q-06 result
was produced with `max_tokens` and is provisional for that reason alone, on top of
the measurement problem below.

### Q-06 will refuse to answer on a bad measurement

The earlier Q-06 verdict was **invalid**. It compared the TPM `remaining_tokens`
between two responses and picked whichever of two candidate costs was closer — and
it was seen reporting a verdict from a drop of **-50**, which means the bucket
refilled between the two reads and no consumption was measured at all. Both candidate
costs were also built on a `len/3` token estimate (88 estimated against 117 actual).

It now requires all three:

1. the two reads are **under 1 s apart**;
2. the drop is **positive** (a negative or zero drop means refill, not consumption);
3. a **measured** prompt overhead exists, taken from the first real
   `usage.prompt_tokens` rather than estimated.

If any condition fails it prints `INCONCLUSIVE (refill confound)` and names the
failing condition. **Treat `INCONCLUSIVE` as the expected outcome** unless the probe
was able to read the header immediately around a single call — that is a property of
how the service reports, not of how hard the probe tries.

## 5. `bigctx` is its own run

The dry run computed ~240K tokens for `--bigctx-repeat 400`, because the estimate
deliberately assumes 3 chars/token. That is 4x the day plan, so it was refused before
spending — correct, but it means:

```bash
# its own day, own ceiling, smallest useful size
python -m scripts.probe --go --max-tokens-total 60000 --timeout 60 --plan-today 60000 \
    --mode bigctx --bigctx-repeat 40
```

Start at `--bigctx-repeat 40` and double until it 400s. `--bigctx-repeat 40` is ~24K at
the over-estimate.

## 6. `rpd` last, and read this twice

`rpd` sends `max_tokens<=3` requests at `60/rpm` intervals until a 429 or the ceiling.
Two unknowns make it risky:

* **Reasoning tokens may be emitted even with a tiny `max_tokens`.** If this model
  family does that, each "tiny" call could cost hundreds of tokens, not 15. The ceiling
  is the only thing standing between that and the day's budget, which is why it is a
  hard abort and not a warning.
* **30 RPM means ~35 minutes** to make 1,000 requests. The probe sleeps between calls;
  do not run it in a terminal you need back.

```bash
python -m scripts.probe --go --max-tokens-total 30000 --timeout 20 --plan-today 30000 \
    --mode rpd --rpd-max-requests 1200
```

It saves `raw/rpd_first_429.json` with the status, all headers, the body, and the
**wall-clock UTC time**. That timestamp is the answer to "when does the daily reset
happen" (Q-09): the first request that succeeds after a day-limit 429 dates the reset.

**Which limit trips first is itself a finding.** RPD at ~15 tokens/request costs ~18K
for 1,000 requests; TPD at 200K costs 200K. If TPD trips first, the binding constraint
on this account is tokens, not requests, and the whole budget model changes.

## 7. What to paste back

1. `runs/probe_<UTC>/<mode>.jsonl` — already key-scrubbed, but skim it anyway.
2. `raw/models.json` — the model IDs.
3. `raw/burst_first_429.json` and `raw/rpd_first_429.json` — the two most valuable files.
4. The limits-page values you read by hand.

Do not paste your key. Do not paste `.env`. If a header or body ever contains it,
`relay/scripts` scrub it, but the scrub only knows the key from the environment — an
artefact from a different shell would not be scrubbed.

## 8. What I will do with it

Fill `config/relay.yaml` (`models.*`, `standin.*`, `slo.*`, `gateway.attempt_timeout_s`),
close Q-01..Q-15 in `docs/OPEN_QUESTIONS.md` with evidence pointers, and calibrate the
P4 stand-in from the measured TTFT and token-rate distributions. P2 (ingest + chunk)
does not depend on any of this and can proceed in parallel.
