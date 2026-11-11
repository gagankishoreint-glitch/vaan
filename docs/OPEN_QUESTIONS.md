# OPEN QUESTIONS

Every claim about Groq in this repo that is **not yet observed** lives here. Rule 5: nothing
in this list may be asserted as fact in code comments, docs, or the report until the P1 probe
replaces it with a measured value. `UNVERIFIED` markers in the source point back to these IDs.

Status values: `OPEN` (no evidence), `PROBED` (measured, see evidence), `WONTFIX` (accepted).

---

## A. Model inventory and limits

| ID | Question | Why it blocks | Probe | Status |
|---|---|---|---|---|
| Q-01 | Which model IDs exist for this key (`openai/gpt-oss-20b`, `openai/gpt-oss-120b`)? | Every gateway call | `GET /openai/v1/models`; record the list verbatim | OPEN |
| Q-02 | Are the limits in `config/relay.yaml` (`rpm/rpd/tpm/tpd`) correct for this key and tier? | Admission and the ladder | `console.groq.com/settings/limits` + first response headers | OPEN |
| Q-03 | Are small and large **separate buckets** or one shared bucket? | `models.buckets_separate_per_model`; if shared, the ladder's cascade saves nothing | Exhaust one model's TPD deliberately with 1-token calls, observe the other's headers | OPEN |
| Q-04 | Do `x-ratelimit-limit-requests` / `remaining-requests` / `reset-requests` really describe a **day**? | 429 minute-vs-day classification | Compare `reset-requests` magnitude against a known minute boundary | OPEN |
| Q-05 | Is there any per-minute **request** header at all? | The PRD budget model assumes RPM is local-only | Dump all headers on 20 requests | OPEN |

## B. The three cost-and-latency unknowns

| ID | Question | Why it blocks | Probe | Status |
|---|---|---|---|---|
| Q-06 | Does `max_tokens` **reserve TPM up front**, or is TPM charged on actual usage? | `pipeline.max_tokens` and the L1 trigger | Send a request with `max_tokens` 10x the prompt, watch `remaining-tokens` before/after | OPEN |
| Q-07 | Does reasoning output (if any) count toward `completion_tokens` and toward TTFT? | `slo.*`, `max_tokens.draft` | Compare `usage` against visible text length | OPEN |
| Q-08 | What is the TPM refill shape — sliding window, fixed minute bucket, or token bucket? | `l1_tpm_remaining_frac` and retry timing | Sample `remaining-tokens` at 1 s intervals across a minute boundary | OPEN |

## C. Failure modes (these decide retry safety)

| ID | Question | Why it blocks | Probe | Status |
|---|---|---|---|---|
| Q-09 | What does a **day-limit** 429 look like: status, body text, `retry-after` magnitude? And when does the daily counter reset (UTC hour)? | `RATE_LIMITED_DAY` vs `_MIN`; retrying a day 429 wastes the whole day | Deliberate exhaustion with a scripted ledger entry | OPEN |
| Q-10 | What does a **minute-limit** 429 look like? | Same | Burst past TPM in one minute | OPEN |
| Q-11 | Is `retry-after` always present on a 429, and in what format (seconds int vs duration string)? | `parse_duration` already accepts both, but the *absence* case decides the policy | Record every 429 verbatim | OPEN |
| Q-12 | Status code for **context too large**; is it 400 or 413? Does the body name the limit? | `Outcome.TOO_LARGE` and the pipeline's chunk budget | Send an oversized prompt once | OPEN |

## D. Cost levers

| ID | Question | Why it blocks | Probe | Status |
|---|---|---|---|---|
| Q-13 | Which models support **prompt caching**, and do cache hits appear in `usage` (field name)? | The PRD claims cached tokens do not count toward limits; that claim is load-bearing for "cheap" | Repeated long prefix, diff the `usage` object | OPEN |
| Q-14 | Does the stable-prefix ordering actually produce cache hits at these model sizes? | Cost lever only; safe to be wrong | Same as Q-13 | OPEN |
| Q-15 | Is streaming SSE chunk shape `data: {...}` + `data: [DONE]`, and are usage numbers in the final chunk? | Stand-in must mirror it (§8) | Capture a raw stream to a file | OPEN |

## E. Product decisions I need from you (not measured)

| ID | Question | Default if you say nothing |
|---|---|---|
| Q-16 | `user.patience_s` — is abandonment driven by a real user trace, or do we define it and report it as an assumption? | I will treat it as a **stated assumption**, not a measurement, and label it as such in the report |
| Q-17 | PRD s12 asks for **two** non-goals. My picks: distributed shared limiter (Redis) and durable workflow engine. | Confirming these two |
| Q-18 | Do we want `retry_policy: naive` runs committed as artifacts (they are the "harm" evidence), or regenerated at report time? | Regenerate at report time, keep one run committed |
| Q-19 | For H2, is `section` allowed to be a coarse heading (e.g. "3.2") when the paper has no stable numbering? | Yes, plus page number, which is unambiguous by construction |

---

## How a question gets closed

1. Run the probe for that ID, save the artifact under `runs/probe_<id>/`.
2. Replace the value in `config/relay.yaml` (`# set by P1 probe: Q-0x`) and remove the
   `UNVERIFIED` marker from the code that depended on it.
3. Update this table: `Status = PROBED`, with a one-line evidence pointer.
4. Add a DECISIONS entry only if a *design* choice follows from the answer.
