# P3: RETRIEVAL MEASUREMENT (zero tokens)

**This is the first real number in the project, and it cost 0 tokens.**
27 questions, **20** with verified gold chunks, 3 chunk settings, BM25.

> **Re-measured a third time after two methodological fixes.** (1) M3 gained the
> gold chunk it was missing, and the 3 ambiguous questions no longer sit in the
> answerable pool. (2) A HIT is now decided by *quote containment* rather than by
> chunk id — see "How a hit is decided" below. Every earlier recall figure in this
> document was scored by id and is superseded.

## Reproducing the table from a fresh clone

`data/chunks/**/*.jsonl` is **git-ignored** — the chunk files are generated, not
source. A fresh clone therefore has no indexes at all and must build them. The three
settings the table compares:

```bash
python -m scripts.ingest --chunk-size 600  --overlap 100 --out data/chunks/exp600
python -m scripts.ingest --chunk-size 900  --overlap 150 --out data/chunks/exp900
python -m scripts.ingest --chunk-size 1200 --overlap 200 --out data/chunks/exp1200
python -m scripts.retrieval_eval
```

Expected chunk counts, so a drift shows up immediately:

| setting | chunks | command |
|---|---|---|
| 600/100 | **744** | `python -m scripts.ingest --chunk-size 600 --overlap 100 --out data/chunks/exp600` |
| 900/150 | **500** | `python -m scripts.ingest --chunk-size 900 --overlap 150 --out data/chunks/exp900` |
| 1200/200 | **379** | `python -m scripts.ingest --chunk-size 1200 --overlap 200 --out data/chunks/exp1200` |

If a count differs, the ingest changed and **every number below is stale** — the
gold ids are index-specific. The PDFs are also git-ignored; restore them per
`data/papers/SHA256SUMS` (committed) and verify with
`(cd data/papers && sha256sum -c SHA256SUMS)` before ingesting.

`python -m scripts.retrieval_eval --no-sweep` reproduces just the table; without the
flag it also runs the threshold sweep, which takes a couple of seconds.

```bash
python -m scripts.check_questions       # every gold id resolves; 20 carry gold
python -m scripts.gold_quotes --check   # every quote still verbatim in its chunk
```

## Results

| setting | chunks | recall@4 (quote) | recall@4 (by id) | MRR | false-abstain | gate threshold |
|---|---|---|---|---|---|---|
| 600/100 | 744 | 40.0% | 40.0% | 0.30 | 30.0% | 15.48 |
| **900/150** | **500** | **50.0%** | 50.0% | **0.41** | 30.0% | 15.86 |
| 1200/200 | 379 | **55.0%** | 50.0% | 0.42 | 25.0% | 15.88 |

n_answerable=20, n_unanswerable=4, n_ambiguous=3.

### How a hit is decided (and why it changed)

**A hit is: some retrieved chunk contains a gold quote.** Not "the retrieved chunk
id is in the gold list".

Chunk ids are not comparable across chunkings. The same passage is a different id
at 600/100 and at 1200/200, and **2 of the 15 gold ids from the 900 index do not
exist in the 1200 index at all**. Under id matching those questions were scored as
misses *by construction* — the retrieval had not failed, the scoring had.

The `(by id)` column exists only to keep that flaw visible. At 1200/200 the two
definitions disagree on exactly one question, **N4**: the quote-based test finds the
evidence at rank 0, the id test scores a miss. Verified by hand — the 1200 chunk
`moshi-v1:s3.2.2:c0001` contains the identical table text including both `4096` and
`11264`. It is the same table split at a different boundary, and the id test could
not see it.

**The gold quotes themselves.** `python -m scripts.gold_quotes` derives a quote per
gold chunk from the 900 index, anchored on the answer where the answer appears
verbatim. Only **7 of 25 quotes contain their answer as a contiguous string**; the
other 18 are the best paraphrase available (often table dumps, where the answer
spans cells rather than appearing in one run of text). Those 18 are **weaker
evidence** and a hit on them means "this chunk contains the passage the answer was
drawn from", not "this chunk contains the answer". Any claim resting on them should
be discounted accordingly.

### Chosen: 900/150 — and the reason is now weaker than before

Quote-based scoring puts **1200/200 ahead on both recall (11/20 vs 10/20) and MRR
(0.417 vs 0.412)**. The committed setting is still 900/150, for one reason:

| | 900/150 finds | 1200/200 finds |
|---|---|---|
| difference | A3 | A1, H1 |

One question lost, two gained, on n=20. **That is noise**, and MRR differs by .005.
Switching the committed chunking on a two-question margin would be the same error as
retuning the gate threshold to the argmin of a 27-point sweep — fitting to a sample
too small to support the choice. The honest statement is that **1200/200 is probably
better and we cannot show it**; a larger eval set settles it, not a different table.

If the pipeline is re-run after the eval set grows, switch to 1200/200 and re-measure
`gate_threshold`, which is derived from the chosen index.

## Per-type recall at 900/150

| type | recall | note |
|---|---|---|
| single-paper | 7/12 | the bulk of the set |
| numeric/table | 3/4 | **the contamination risk did not bite at chunk level** |
| cross-paper | 1/4 | **the clear weakness** |

Cross-paper questions need one chunk to rank for a question whose evidence spans
two papers; BM25 has no notion of that. 1/4 is the number to quote, not a rounded
"most questions work".

## The finding that matters: the gate cannot be perfect, and the sweep says by how much

`python -m scripts.retrieval_eval --sweep-setting 900/150` evaluates **every**
achievable threshold on the committed index (n_answerable=20, **n_unanswerable=4**,
n_ambiguous=3, k=4):

| threshold | A refused | U admitted | T admitted | errors |
|---|---|---|---|---|
| 12.40 | 0/20 | 4/4 | 1/3 | 4 |
| 12.92 | 1/20 | 2/4 | 1/3 | 3 |
| **14.82** | **2/20** | **1/4** | 0/3 | **3** |
| 15.86 (committed) | 5/20 | 1/4 | 0/3 | 6 |
| 17.28 | 8/20 | 0/4 | 0/3 | 8 |
| 22.30 | 15/20 | 0/4 | 0/3 | 15 |

### The three no-gold kinds are not one pool

This is a correction to the previous version of this document, which reported
`false_answer` against **7** non-answerable questions. Three of those were
**ambiguous (T)** — questions with several defensible answers. A high score on them
is *correct behaviour*, not a false answer, and folding them into the denominator
scored the system wrong for being right.

| kind | n | what a high score means |
|---|---|---|
| answerable (A) | 20 | good (evidence found) |
| unanswerable (U) | **4** | bad (false answer) |
| ambiguous (T) | **3** | neither — not an error |

They are now reported as three separate columns. `false_answer` is measured against
**4**, not 7, so the committed 15.86 admits 1 of 4 genuinely unanswerable questions
rather than 1 of 7. The old figure understated the rate by 75%.

At 1200/200 the split changes the picture further: the best point is **14.04 with 2
total errors** (1/20 refused, 1/4 admitted) — better than 900/150's best of 3.

**Thresholds at which both errors are zero: 0 at either setting.** The
distributions interpenetrate: the highest-scoring unanswerable question outscores
**11 of 20** answerable ones at 1200/200.

> No single BM25 top-1 threshold admits all 20 answerable questions while refusing
> all 4 unanswerable ones. The best point misclassifies 2–3 of 24 scored questions.

That is a real limitation but **weaker than the claim originally made** ("a single
threshold is not usable in either direction"). The gate is usable; it cannot be made
correct. H1 therefore cannot rest on it, and does not: `verify.py` is the guarantee.

**Caveat.** n=24 scored. The gap between the best point and the committed 15.86 is
three or four individual questions. The threshold was left at 15.86 rather than
retuned: choosing the argmin of a sweep over 24 questions is fitting to noise. The
operating point is known only to within a few questions; a larger eval set is the
fix, not a better threshold.

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
