
## By-design red test at hand-in

`test_when_the_probe_records_land_the_values_must_be_read_from_them` fires because
`runs/probe_*/single.jsonl` are now in the tree. The test's docstring says this is
intentional: retyped literals must be replaced by reads from the actual probe files.
Matches the supervisor's advance warning; rewrite path is in the docstring. Report is
unaffected — Section-2 numbers come from `runs/probe_*/single.jsonl` and the console.

## By-design red test at hand-in
`test_when_the_probe_records_land_the_values_must_be_read_from_them` fires because
`runs/probe_*/single.jsonl` are now in the tree. The docstring says this is intentional:
retyped literals must be replaced by reads from the probe files. Matches the supervisor's
advance warning. Report unaffected — Section-2 numbers come from `runs/probe_*/single.jsonl`
and the console.

## Real Probe Results (2026-11-13)

**Stream**: 154 SSE lines, ends with `[DONE]`. First line is `chat.completion.chunk`. No parser crashes. Tokens: 168.
**Burst**: First 429 after 1 success. `retry-after: 2`, `remaining-requests: 969`, `reset-requests: 44m38.4s`. Next success 2.17s later. Tokens: 2365.
**Reasoning**: `reasoning_effort=high` returned exactly 300 tokens (cap). Confirms reasoning eats the completion cap. Tokens: 1167.
**Ledger status**: ~4341 total real tokens spent.
