# P1 PROBE: run sheet

Read this top to bottom before running anything. The probe spends real tokens.

## 0. What I can and cannot do

I cannot reach `console.groq.com` or `api.groq.com` from this environment, so:

* **You** read the limits page and fill the values in `config/relay.yaml` (`# set by P1`).
* **You** run the probe and paste the artefacts back (they are key-scrubbed by design).
* **I** cannot verify a single Groq fact by running it. Everything in
  `docs/OPEN_QUESTIONS.md` stays OPEN until your paste lands.

## 1. Before the first real call

```bash
python -m scripts.probe --dry-run --plan-today 60000     # always first
```

Expect: `DRY RUN (no network)`, one line per planned request with `est≈N tokens`,
and `ledger not written`. **If any line says REFUSED, read why before continuing** —
that is the ceiling doing its job, not a bug.

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
