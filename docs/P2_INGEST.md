# P2: INGEST AND CHUNKING

Status: working, 500 chunks over three papers at 900/150. **900 and 150 are a
starting point, not a measurement** — `retrieval.chunk_size` and
`retrieval.chunk_overlap` stay `null` in config until the P10 experiment.

```bash
python -m scripts.ingest --chunk-size 900 --overlap 150 --out data/chunks/exp900
```

## Outputs

| File | Purpose |
|---|---|
| `chunks.jsonl` | one chunk per line, with `flags` and `digit_ratio` |
| `manifest.json` | chunk size, overlap, ingest timestamp, **sha256 per PDF**, warnings |
| `review_random.md` | 10 random chunks per paper — **eyeball this** |
| `review_flagged.md` | every chunk not flagged `ok` |
| `review_numeric_worst.md` | worst 40 numeric/caption regions, for the retrieval section |

Chunk ids are `{label}:s{section}:c{index}` (e.g. `attn-v7:s3.2:c0004`), so they are
reproducible from the manifest's size + sha256.

## What the real PDFs do (measured, not assumed)

Two quirks made a naive ingester fail outright, and both were found by reading
extracted text rather than by imagining what a PDF looks like.

**1. Headings are split across lines.** In attention, `3.1` and
`Encoder and Decoder Stacks` arrive as separate lines. A line-oriented regex finds
zero headings.

**2. Some pages are one character per line.** hnet page 3 is a TikZ figure that
extracts as `n d o f t o k e s`. Pages 3, 15 and 39 of hnet and page 34 of moshi are
skipped wholesale; 1,583 sub-3-char lines are dropped in hnet alone.

**3. Headings are not bold.** In moshi and hnet every heading is 12pt *regular*; in
moshi the sub-headings are body-sized *and* regular. Font alone yields 7 sections in
moshi and 0 chunks in hnet. The numbering pattern is the only structural signal.

## Section counts (start `900/150`)

| Paper | Sections | Chunks | Notes |
|---|---|---|---|
| attention | 22 | 59 | complete and clean |
| moshi | 30 | 256 | complete to the sub-sub-section level |
| hnet | 13 | 185 | complete |

**Known gap (honest):** a few moshi headings have a lowercase second word
(`3 Model` is fine, but `3.2 The Helium Text Language Model` is accepted while
`3 The...`-shaped variants are not) and a handful of unnumbered headings are missed.
They land inside the preceding section's text rather than being lost, so retrieval
still sees the words; only the section label is coarser.

## Every rejection rule, and the real string that caused it

Each line below is a false positive observed in these three PDFs. This table is the
justification for the heuristics — none of them are guesses.

| Rule | Real string it rejects |
|---|---|
| Unicode author marker (`\u2217 \u2020 \u2021`) | `Ashish Vaswani\u2217` |
| Affiliation prefix | `Google Brain`, `Kyutai` |
| Trailing period + >3 words | `3.4 describes this architecture.` |
| Second word is a unit | `12.5 Hz`, `10 seconds` |
| Number + `\u00b7`/`\u00d7` | `1.0 \u00b7 1020`, `5 \u00b7 10-5` |
| URL or DOI | `4 https://openai.com/index/chatgpt...` |
| All digits/punctuation | `2 \u00b7 10\u22126` |
| Sentence fragment (comma, lowercase opener) | `8 bits, using integer scalar PTQ...` |
| No capitalised word | `seconds`, `. 10-5` |
| Number does not advance the outline | `41.29`, `1019.2` |

**The rule that mattered most** was none of the above: it was *monotonicity*. A real
outline visits 1, 2, 3, 3.1, 3.2 in order. Footnotes, table values and examples all
break that order, which removed most junk at once. The single-string rules only
cleaned up the stragglers.

**And the rule that was wrong:** "the word after the number must be capitalised"
deleted `3.1 Encoder and Decoder Stacks` (second word *and*), `3.4 Embeddings and
Softmax`, `5.2 Hardware and Schedule`. The correct test is *any* capitalised word in
the title, not the second one.

## Chunk boundaries and H2

Chunks end **and start** on word boundaries. The first implementation snapped only
the end, so the overlap window began mid-word; a quote spanning that boundary would
not be a verbatim substring of either chunk, and the failure would surface much later
as an inexplicable `verify()` rejection. `test_no_chunk_starts_or_ends_mid_word`
pins it.

The weaker assertion — "every word appears in some chunk" — **cannot fail**: a
splitter that hard-cuts mid-word loses no characters. That test was written first,
passed, and proved nothing. It was replaced.

## Captions: the number that matters for the retrieval section

**88 of 500 chunks (17.6%) contain an embedded Table/Figure/Algorithm caption.**
Before flagging, 50 of these were marked `ok` — a chunk holding `Table 1: Maximum
path lengths...` followed by `Layer Type / Complexity per Layer / Self-Attention /
O(n2` looks like clean prose to every heuristic and is poison for a text retriever.

These chunks are **kept, not removed**: the report needs them as evidence, and a
retriever that cannot cope with them is the finding. They are flagged `caption`
(and `caption_lead` when the caption starts the chunk).

## Reproducibility

`manifest.json` records chunk size, overlap, ingest UTC and the sha256 of each PDF.
`data/papers/SHA256SUMS` is committed; the PDFs are not (8 MB of binaries, D-005).
`test_real_pdf_manifest_hashes_match_committed_sums` fails loudly if the PDFs ever
change, which is the "exact versions" rule enforced by test rather than by trust.

## Next

P3: BM25 over `chunks.jsonl`, the 20+ question eval set, and the retrieval-only
experiment (recall@k, false-abstain and false-answer rates) that the supervisor asked
for **before** any setting touches Groq.
