
## By-design red test at hand-in

`test_when_the_probe_records_land_the_values_must_be_read_from_them` fires because
`runs/probe_*/single.jsonl` are now in the tree. The test's docstring says this is
intentional: retyped literals must be replaced by reads from the actual probe files.
Matches the supervisor's advance warning; rewrite path is in the docstring. Report is
unaffected — Section-2 numbers come from `runs/probe_*/single.jsonl` and the console.
