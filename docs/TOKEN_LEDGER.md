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

| Day | Cap (TPD) | Planned | Spent | Remaining |
|---|---|---|---|---|
| (fill at P1) | UNVERIFIED ~200000 | probe | 0 | – |

## Real-API runs

| # | Date | Phase | Script | Purpose | Est. tokens | Actual tokens | Console reconciliation |
|---|---|---|---|---|---|---|---|
| – | – | – | – | no real runs yet (P0 touches no API) | 0 | 0 | n/a |

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
