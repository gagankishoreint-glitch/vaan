# P3: RETRIEVAL MEASUREMENT (zero tokens)

**This is the first real number in the project, and it cost 0 tokens.**
27 questions, 19 with verified gold chunks, 3 chunk settings, BM25.

```bash
python -m scripts.ingest --chunk-size 900 --overlap 150 --out data/chunks/exp900
python -m scripts.retrieval_eval
```

## Results

| setting | chunks | recall@4 | MRR | false-abstain | false-answer | gate threshold |
|---|---|---|---|---|---|---|
| 600/100 | 734 | 42.1% | 0.28 | 26.3% | 0.0% | 15.48 |
| **900/150** | **500** | **52.6%** | **0.43** | 26.3% | 12.5% | 15.86 |
| 1200/200 | 388 | 52.6% | 0.35 | 21.1% | 12.5% | 15.88 |

**Chosen: 900/150.** Recall ties with 1200/200 but MRR is materially better
(0.43 vs 0.35), meaning the right chunk is not merely present but ranked near the
top. That matters more than raw recall because `top_k=4` and the gate reads top-1.

## Per-type recall at 900/150

| type | recall | note |
|---|---|---|
| single-paper | 6/11 | the bulk of the set |
| numeric/table | 3/4 | **the contamination risk did not bite at chunk level** |
| cross-paper | 1/4 | **the clear weakness** |

## The finding that matters: the score cannot separate classes

At the measured threshold (15.86 = 25th percentile of answerable top-1 scores),
**26.3% of answerable questions are refused and 12.5% of unanswerable ones are
accepted.** A single BM25-score threshold is not a usable evidence gate in either
direction. This is a limitation to report, not a parameter to tune: there is no
threshold that fixes both simultaneously, because the two distributions overlap.

**Consequence for P6: the gate is deliberately permissive** (it admits, then
verification catches bad answers) rather than strict. H1 is enforced by
`verify.py`, not by the gate.

## The eval-set bug I found in my own data

The first run reported `false_answer = 46.2%`. That was wrong, and the cause was
mine: I had used `gold: []` as a placeholder for "not verified yet", so six
answerable questions were counted as unanswerable. After locating and verifying
the real gold chunks, the true figure is 12.5%.

Recorded because it is the same class of error as BUG-003/004: a value that means
"unknown" silently behaving as a value that means "none".

## Why 900/150 is still not a measurement of chunk size

It was chosen from three candidates on 19 questions, with no dev/test split (as
agreed: state this). The 600/100 column is clearly dominated and can be dropped
with confidence; the 900 vs 1200 distinction is within noise on this sample.
`retrieval.chunk_size` stays `null` in config; `gate_threshold: 15.86` is
committed because the pipeline needs *some* measured value to run.
