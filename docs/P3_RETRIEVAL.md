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

## The finding that matters: the gate cannot be perfect, and the sweep says by how much

`python -m scripts.retrieval_eval --sweep-setting 900/150` evaluates **every**
achievable threshold (n_answerable=19, n_unanswerable=8, k=4):

| threshold | false abstain | false answer | total errors |
|---|---|---|---|
| 8.82 | 0/19 | 7/8 | 7 |
| 11.77 | 0/19 | 6/8 | 6 |
| 12.92 | 1/19 | 4/8 | 5 |
| **14.82** | **2/19** | **2/8** | **4** |
| 15.86 (committed) | 4/19 | 1/8 | 5 |
| 17.28 | 7/19 | 0/8 | 7 |
| 22.30 | 14/19 | 0/8 | 14 |

**Thresholds at which both errors are zero: 0.** The two distributions
interpenetrate — the highest-scoring unanswerable question (17.28) outscores
**7 of 19** answerable ones. So the claim supported by the sweep is:

> No single BM25 top-1 threshold admits all 19 answerable questions while
> refusing all 8 unanswerable ones. The best achievable operating point (14.82)
> misclassifies 4 of 27 questions: 2 answerable refused, 2 unanswerable admitted.

That is a real limitation but **not** the stronger claim I made earlier ("a single
threshold is not usable in either direction"). The gate is usable; it is simply
incapable of being correct. At its best point it is wrong on 4 of 27 questions,
which is why verification, not the gate, has to enforce H1.

**Caveat on the exact number.** n=27. The difference between the best point
(4 errors) and the committed 15.86 (5 errors) is **one question** — well inside
sampling noise. The committed threshold was not changed to 14.82 because the sweep
cannot distinguish them on this sample; changing it would be fitting to noise.
The report must say the operating point is known only to ±1 question.

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
