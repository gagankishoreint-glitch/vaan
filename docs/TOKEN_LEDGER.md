# TOKEN LEDGER

Real Groq tokens are a **daily** budget (about 200K TPD per the docs table, UNVERIFIED —
see OPEN_QUESTIONS Q-02). Nothing is spent without an entry here *before* the run.

Rules
1. Every run that touches the real API gets a row **before** it starts, with an estimate.
2. The estimate is `sum(tokens_in + tokens_out)` from a stand-in run of the same script.
3. After the run, the actual comes from `attempt.end` events and must be reconciled
   against the console's usage page. A mismatch > 5% is a BUGLOG entry.
4. Stand-in runs cost nothing and are logged in a separate section so the real-budget
   column stays honest.

## Budget

| Day | Cap (TPD) | Planned (80% rule) | Spent | Remaining |
|---|---|---|---|---|
| Day 1: probe (cheap modes) | UNVERIFIED ~200000 | 60000 | 0 | 60000 |
| Day 1 or 2: `bigctx` only | UNVERIFIED ~200000 | 60000 | 0 | 60000 |
| Day 2: eval (15 q x ~5K x 3 settings) | UNVERIFIED ~200000 | 160000 | 0 | (about 225K needed -> spans 2 days) |
| Day 3: eval cont. + final real runs | UNVERIFIED ~200000 | 160000 | 0 | 0 |

**The 80% rule.** Never plan more than 80% of the daily cap on any day; the 20% buffer
absorbs reasoning-token variance and the over-estimate on `est_tokens`. Until the limits
page is read, the cap itself is UNVERIFIED and these plans are provisional.

**Machine-readable block.** `scripts/probe.py` reads and rewrites the fenced
`LEDGER:DATA` JSON block below. Do not edit that block by hand; edit the tables.
The runner refuses to send when today's plan is exhausted.

## Real-API runs

| # | Date | Phase | Script | Purpose | Est. tokens | Actual tokens | Console reconciliation |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-11 | P1 | `scripts/probe.py` | **accidental**: `test_go_without_key_exits_2` reached the real API through a developer `.env` (BUG-024) | 0 | **117** | not reconciled against the console; header-only |

**Total real tokens charged so far: 117.** This row is a backfill: the run happened at
`2026-11-11T06:48:21Z` in `runs/probe_20261111T064821Z` and was recorded nowhere,
because the ledger write sat after an early `return` (BUG-023). It is recorded now, in
`finally`, and labelled so that it is never mistaken for a planned measurement.

> **Still missing from this table: the supervisor's 351-token probe session**, which
> they reported on their own machine. This workspace copy has no row for it and no
> `runs/` directory for it, so it cannot be backfilled from evidence here — only from
> their console usage page. Expected dashboard total once merged: **117 + 351 = 468**.

## Stand-in runs (free)

| # | Date | Phase | Run dir | Note |
|---|---|---|---|---|
| 1 | 2026-11-11 | P0 | `runs/p0_smoke` | contract smoke; **synthetic** token counts (512/64), not billable |

## Allocation plan (from PRD s15)

| Slice | Share | Gates |
|---|---|---|
| P1 probe | 10% | The 19 open questions; must fit in one day's cap or it spans two |
| Build/dev (P5–P7) | 0% | Stand-in only |
| Eval, real, final | 60% | The 20+ question set at the chosen setting |
| Retrieval experiment (P10) | 25% | >= 3 settings, real API only if the stand-in cannot rank them |
| Reserve | 5% | Re-runs after a bug |

The reserve exists because BUG-001 and BUG-002 both needed a re-run. Assume it will be used.

<!-- LEDGER:DATA -->
```json
{
  "probe_version": 1,
  "days": [
    {
      "date": "2026-11-11",
      "plan": 0,
      "cap_tpd_unverified": 200000,
      "spent": 117
    }
  ],
  "runs": [
    {
      "utc": "2026-11-11T06:48:21+00:00",
      "modes": [
        "single"
      ],
      "tokens": 117,
      "ceiling": 100,
      "labelled_source": "runs/probe_20261111T064821Z",
      "label": "accidental: pytest live call"
    }
  ]
}
```
<!-- /LEDGER:DATA -->
