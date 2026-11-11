"""Derive a verbatim GOLD QUOTE per gold chunk, so a hit is defined by evidence.

Why this exists: scoring a hit by chunk id only works inside one chunking. The same
passage is a different chunk id at 600/100 and at 1200/200, and two gold ids from the
900 index do not exist in the 1200 index at all -- so those questions were scored as
misses by construction, not by retrieval quality. That made the setting comparison
partly an artefact of the index it was scored in.

A quote-based hit asks the question we actually care about: **did a retrieved chunk
contain the evidence?** It is comparable across settings because the evidence is a
string, not an identifier.

The quote is chosen from the 900/150 chunk (where gold was eyeball-verified), taking
the sentence that best covers the answer tokens, then LONGEST up to a cap so it is
unlikely to be a coincidental substring.

    python -m scripts.gold_quotes            # writes data/eval/gold_quotes.json
    python -m scripts.gold_quotes --check    # verify every quote still resolves at 900

Every quote MUST appear in its own gold chunk after normalisation. A quote that does
not is a bug in this script, not a property of the corpus.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from relay.retrieval.text import contains_quote, normalize, tokenize

MAX_QUOTE_CHARS = 220
MIN_QUOTE_CHARS = 40


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _answer_pattern(answer: str) -> str:
    """A regex that matches the answer in raw text, tolerating layout whitespace.

    PDF text has hard line breaks in the middle of phrases ("Frame rate\n12.5 Hz"),
    so joining answer tokens with `\\s+` and escaping each is what makes the search
    robust. Numbers and symbols are escaped literally.
    """
    toks = [t for t in re.split(r"\s+", answer.strip()) if t]
    if not toks:
        return ""
    return r"\s+".join(re.escape(t) for t in toks)


def choose_quote(chunk_text: str, answer: str) -> str:
    """A window of `chunk_text` that CONTAINS the answer, so a hit means evidence.

    The first version of this scored sentences by token overlap with the answer.
    It picked sentences that did not contain the answer at all -- "For the base
    models, we used a single model" for the answer "28.4" -- because common words
    outvoted the one token that mattered. A quote that does not contain the answer
    cannot define a hit, so the answer is now the anchor and the quote is built
    around it.
    """
    pat = _answer_pattern(answer)
    if pat:
        m = re.search(pat, chunk_text, flags=re.IGNORECASE)
        if m:
            # Keep ~70 chars of lead-in and fill to the cap; never start mid-word.
            start = max(0, m.start() - 70)
            while start > 0 and chunk_text[start - 1].isalnum():
                start -= 1
            end = min(len(chunk_text), start + MAX_QUOTE_CHARS)
            if end < m.end():
                end = min(len(chunk_text), m.end() + 20)
            while end < len(chunk_text) and chunk_text[end - 1].isalnum() \
                    and chunk_text[end].isalnum():
                end += 1
            return chunk_text[start:end].strip()

    # The answer is paraphrased rather than quoted (cross-paper and some
    # single-paper questions). Fall back to the sentence richest in the answer's
    # distinctive tokens, and accept that such a quote is weaker evidence.
    want = {t for t in tokenize(answer) if len(t) > 3}
    best, best_score = "", -1.0
    for sent in split_sentences(chunk_text):
        if len(sent) > MAX_QUOTE_CHARS:
            continue
        got = set(tokenize(sent))
        if not want:
            continue
        score = len(want & got) / len(want) - len(sent) / 10_000.0
        if score > best_score and len(sent) >= MIN_QUOTE_CHARS:
            best, best_score = sent, score
    return best or chunk_text[:MAX_QUOTE_CHARS].strip()


def build(questions_path: str, chunks_path: str) -> dict:
    chunks = {c["chunk_id"]: c for c in
              (json.loads(l) for l in open(chunks_path, encoding="utf-8") if l.strip())}
    out: dict[str, dict] = {}
    for q in (json.loads(l) for l in open(questions_path, encoding="utf-8") if l.strip()):
        quotes = []
        for cid in q["gold"]:
            ch = chunks.get(cid)
            if ch is None:
                quotes.append({"chunk_id": cid, "quote": None,
                               "error": "gold chunk not in the 900 index"})
                continue
            qte = choose_quote(ch["text"], q["answer"])
            ok = contains_quote(ch["text"], qte)
            # Does the quote contain the ANSWER, or only paraphrase it? Only the
            # first kind makes "the retrieved chunk contains this quote" mean "the
            # retrieved chunk contains the evidence".
            pat = _answer_pattern(q["answer"])
            has_ans = bool(pat) and bool(
                re.search(pat, qte, flags=re.IGNORECASE))
            quotes.append({"chunk_id": cid, "quote": qte,
                           "chars": len(qte), "verified": ok,
                           "contains_answer": has_ans})
        if quotes:
            out[q["qid"]] = {"qid": q["qid"], "type": q["type"],
                             "answer": q["answer"], "quotes": quotes}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="data/eval/questions.jsonl")
    ap.add_argument("--chunks", default="data/chunks/exp900/chunks.jsonl")
    ap.add_argument("--out", default="data/eval/gold_quotes.json")
    ap.add_argument("--check", action="store_true",
                    help="verify the stored quotes instead of rebuilding")
    a = ap.parse_args(argv)

    if a.check:
        data = json.loads(Path(a.out).read_text(encoding="utf-8"))
        chunks = {c["chunk_id"]: c for c in
                  (json.loads(l) for l in open(a.chunks, encoding="utf-8") if l.strip())}
        bad = []
        for qid, rec in data.items():
            for q in rec["quotes"]:
                ch = chunks.get(q["chunk_id"])
                if ch is None or not q["quote"] or not contains_quote(ch["text"], q["quote"]):
                    bad.append(f"{qid}/{q['chunk_id']}")
        if bad:
            print(f"FAIL {len(bad)} quote(s) do not resolve: {bad}")
            return 1
        print(f"OK: all {sum(len(r['quotes']) for r in data.values())} gold quotes "
              f"appear verbatim in their gold chunks")
        return 0

    data = build(a.questions, a.chunks)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(data, indent=2), encoding="utf-8")

    n_q = len(data)
    n_qte = sum(len(r["quotes"]) for r in data.values())
    unverified = [f"{qid}/{q['chunk_id']}" for qid, r in data.items()
                  for q in r["quotes"] if not q.get("verified")]
    lens = [q["chars"] for r in data.values() for q in r["quotes"] if q.get("chars")]
    with_ans = sum(1 for r in data.values() for q in r["quotes"]
                   if q.get("contains_answer"))
    print(f"questions with gold {n_q}, quotes {n_qte}, "
          f"mean length {sum(lens)/len(lens):.0f} chars "
          f"(min {min(lens)}, max {max(lens)})")
    print(f"quotes containing the answer verbatim: {with_ans}/{n_qte} "
          f"({with_ans/n_qte:.0%}) -- the rest are paraphrase and are weaker evidence")
    if unverified:
        print(f"FAIL {len(unverified)} unverified: {unverified}")
        return 1
    print(f"every quote resolves in its own gold chunk. wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
