# P3: RETRIEVAL MEASUREMENT (zero tokens)

**This is the first real number in the project, and it cost 0 tokens.**
27 questions, **20** with verified gold chunks, 3 chunk settings, BM25.

> **Numbers below were re-measured after two gold fixes** (M3 gained a gold chunk;
> the 3 ambiguous questions are now excluded from the answerable pool). Earlier
> figures of 52.6% / MRR .43 were computed on a corrupted denominator and are
> superseded. `python -m scripts.check_questions` is what caught it.

```bash
python -m scripts.ingest --chunk-size 900 --overlap 150 --out data/chunks/exp900
python -m scripts.retrieval_eval
```

## Results

| setting | chunks | recall@4 | MRR | false-abstain | false-answer | gate threshold |
|---|---|---|---|---|---|---|
| 600/100 | 734 | 40.0% | 0.27 | 30.0% | 0.0% | 15.48 |
| **900/150** | **500** | **50.0%** | **0.40** | 30.0% | 14.3% | 15.86 |
| 1200/200 | 388 | 50.0% | 0.33 | 25.0% | 14.3% | 15.88 |

n_answerable=20, n_unanswerable=7. **Chosen: 900/150.** Recall ties with 1200/200
but MRR is better (0.40 vs 0.33), meaning the right chunk is not merely present but
ranked nearer the top. That matters more than raw recall because `top_k=4` and the
gate reads top-1. The gap is narrower than it first appeared and 600/100 remains
clearly dominated.

## Per-type recall at 900/150

| type | recall | note |
|---|---|---|
| single-paper | 6/12 | the bulk of the set |
| numeric/table | 3/4 | **the contamination risk did not bite at chunk level** |
| cross-paper | 1/4 | **the clear weakness** |

Cross-paper questions need one chunk to rank for a question whose evidence spans
two papers; BM25 has no notion of that. 1/4 is the number to quote, not a rounded
"most questions work".

## The finding that matters: the gate cannot be perfect, and the sweep says by how much

`python -m scripts.retrieval_eval --sweep-setting 900/150` evaluates **every**
achievable threshold (n_answerable=20, n_unanswerable=7, k=4):

| threshold | false abstain | false answer | total errors |
|---|---|---|---|
| 8.82 | 0/20 | 6/7 | 6 |
| 11.77 | 0/20 | 5/7 | 5 |
| 12.92 | 1/20 | 3/7 | 4 |
| **14.82** | **2/20** | **1/7** | **3** |
| 15.86 (committed) | 5/20 | 1/7 | 6 |
| 17.28 | 8/20 | 0/7 | 8 |
| 22.30 | 15/20 | 0/7 | 15 |

**Thresholds at which both errors are zero: 0.** The distributions interpenetrate:
the highest-scoring unanswerable question (17.28) outscores **8 of 20** answerable
ones. The claim the sweep actually supports is:

> No single BM25 top-1 threshold admits all 20 answerable questions while refusing
> all 7 unanswerable ones. The best achievable operating point (14.82)
> misclassifies 3 of 27 questions: 2 answerable refused, 1 unanswerable admitted.

That is a real limitation, but **weaker than the claim I originally made** ("a
single threshold is not usable in either direction"). The gate is usable; it
simply cannot be made correct. At its best point it is wrong on 3 of 27 questions.
H1 therefore cannot rest on it, and does not: `verify.py` is the guarantee.

**Caveat on the exact number.** n=27. The gap between the best point (3 errors) and
the committed 15.86 (6 errors) is **three questions**; at this n that is one or two
individual flips, not a stable ordering. The committed threshold was left at 15.86
rather than retuned to 14.82: choosing the argmin of a 27-point sweep is fitting to
noise. The honest statement is that the operating point is known only to within a
couple of questions, and that a larger eval set is the fix — not a better threshold.

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
