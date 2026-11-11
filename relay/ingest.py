"""P2: PDF -> sections -> chunks, with a reproducible manifest.

Two problems in these specific PDFs drive the design, both found by actually
reading the extracted text rather than by imagining what PDFs look like:

1. **Headings are split across lines.** In attention, `3.1` and
   `Encoder and Decoder Stacks` arrive as two separate lines, so a line-oriented
   heading regex finds nothing. Headings are detected from *span font* (bold /
   heavier weight) and a two-line lookahead.
2. **Some pages are one character per line.** hnet page 3 is a TikZ figure that
   extracts as 'n','d','o','f','t','o','k','e','s'. A naive splitter emits
   hundreds of one-character chunks. Lines below a threshold are dropped before
   chunking, and the loss is counted.

Nothing here is a magic number: chunk size, overlap and the drop threshold come
from config/relay.yaml. Values still null raise rather than default.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pymupdf

from relay.config import Config
from relay.contracts import Chunk

#: Registry keyed on `Chunk.paper`, as agreed (supervisor Q-19 / D-006 area).
#: `Chunk` stays frozen and untitled; display names live here.
PAPERS: dict[str, dict] = {
    "attention": {
        "file": "1706.03762v7.pdf",
        "title": "Attention Is All You Need",
        "arxiv": "1706.03762v7",
        "stamp": "arXiv:1706.03762v7  [cs.CL]  2 Aug 2023",
        "label": "attn-v7",
    },
    "moshi": {
        "file": "2410.00037v1.pdf",
        "title": "Moshi: a speech-text foundation model for real-time dialogue",
        "arxiv": "2410.00037v1",
        "stamp": "arXiv:2410.00037v1  [eess.AS]  17 Sep 2024",
        "label": "moshi-v1",
    },
    "hnet": {
        "file": "2507.07955v2.pdf",
        "title": "Dynamic Chunking for End-to-End Hierarchical Sequence Modeling",
        "arxiv": "2507.07955v2",
        "stamp": "arXiv:2507.07955v2  [cs.LG]  15 Jul 2025",
        "label": "hnet-v2",
    },
}

#: A chunk is never emitted shorter than this many visible characters. The
#: char-per-line figure pages produce strings like "ndoftokes"; dropping only
#: genuinely tiny fragments keeps real table cells if they matter later.
_MIN_VISIBLE_CHARS = 3


# ------------------------------------------------------------------ text quality

_MOSTLY_DIGITS = re.compile(r"^[\s\d.,:%()\[\]+\-–—/=]*$")
_REFERENCE_HINT = re.compile(r"^(references|bibliography)\s*$", re.I)


def digit_ratio(text: str) -> float:
    visible = [c for c in text if not c.isspace()]
    if not visible:
        return 0.0
    return sum(c.isdigit() for c in visible) / len(visible)


def is_mostly_digits(text: str) -> bool:
    """True for table rows / number soup: a chunk the retriever must not love."""
    stripped = text.strip()
    if len(stripped) < 20:
        return False
    return bool(_MOSTLY_DIGITS.match(stripped)) or digit_ratio(stripped) > 0.5


def looks_like_figure_junk(lines: Iterable[str]) -> bool:
    """A run of very short lines is a diagram, not prose (hnet page 3)."""
    lines = [ln for ln in lines if ln.strip()]
    if len(lines) < 10:
        return False
    short = sum(1 for ln in lines if len(ln.strip()) <= 3)
    return short / len(lines) > 0.6


# --------------------------------------------------------------------- sections

@dataclass
class Section:
    paper: str
    number: str          # "3.2" or "" when unnumbered
    title: str           # "Attention"
    page: int            # 1-based page the heading starts on
    text: str = ""

    @property
    def path(self) -> str:
        return f"{self.number} {self.title}".strip()


@dataclass
class PageReport:
    page: int
    n_lines: int
    n_dropped_short: int
    figure_junk: bool
    chars: int


_NUM = re.compile(r"^(\d+(?:\.\d+){0,3})\.?$")
_NUM_AND_TITLE = re.compile(r"^(\d+(?:\.\d+){0,3})\s+(\S.{1,80})$")


def _is_bold(span: dict) -> bool:
    font = (span.get("font") or "").lower()
    return "bold" in font or "medi" in font or "black" in font or "heavy" in font


def extract_pages(pdf_path: Path) -> list[dict]:
    """Raw per-page structure: lines, their spans, and whether a line is bold.

    Kept separate from section assembly so the ink-level facts can be dumped and
    eyeballed (the supervisor's instruction: look at the text, not the tests).
    """
    doc = pymupdf.open(pdf_path)
    pages = []
    try:
        for pno in range(doc.page_count):
            blocks = doc[pno].get_text("dict")["blocks"]
            lines: list[dict] = []
            for block in blocks:
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    text = "".join(s.get("text", "") for s in spans)
                    if not text.strip():
                        continue
                    sizes = [s.get("size", 0.0) for s in spans]
                    lines.append({
                        "text": text,
                        "bold": any(_is_bold(s) for s in spans),
                        "size": max(sizes) if sizes else 0.0,
                        "bbox": line.get("bbox"),
                    })
            pages.append({"page": pno + 1, "lines": lines})
    finally:
        doc.close()
    return pages


def _body_size(pages: list[dict]) -> float:
    """The modal font size of the document = body text size."""
    counts: dict[float, int] = {}
    for p in pages:
        for ln in p["lines"]:
            counts[round(ln["size"], 1)] = counts.get(round(ln["size"], 1), 0) + 1
    if not counts:
        return 0.0
    return max(counts.items(), key=lambda kv: kv[1])[0]


# NOTE the characters here are U+2217 (∗), U+2020 (†), U+2021 (‡), U+00B0 etc. --
# NOT ASCII '*' (U+002A). The PDFs use the Unicode forms, so an ASCII-only class
# silently matched nothing and author names became sections.
_AUTHOR_HINT = re.compile(r"[\u2217*\u2020\u2021\u00a7\u00b6@]|^\d+$")
_AFFILIATION = re.compile(
    r"^(google|brain|research|university|institute|kyutai|cartesia|cmu|"
    r"carnegie|deepmind|meta|microsoft|openai|allen|mit|stanford|berkeley)\b", re.I)
_ABSTRACT = re.compile(r"^abstract\b[\s—:-]*", re.I)


def _is_heading_line(ln: dict, body: float) -> bool:
    """Bold OR clearly larger than body text. BOTH papers' headings are 12pt and
    NOT bold -- requiring bold found zero headings in hnet (found by eyeballing)."""
    if ln["bold"]:
        return True
    return bool(body) and ln["size"] > body + 0.8


#: A numbered line followed by a unit or a dot-product-ish symbol is a measurement
#: in a table cell, not a section: `12.5 Hz`, `1.0 · 1020`, `3.4 ms`.
_MEASUREMENT_TAIL = re.compile(
    r"^(hz|khz|mhz|ghz|ms|sec|s|min|kbps|gb|mb|tb|%|\\times|x|\u00b7)\b", re.I)
_MEASUREMENT_VALUE = re.compile(r"^[\d.\u00b7\u00d7\s]+$")

#: A line that begins with a section number is a heading candidate EVEN IF it is
#: body-sized and not bold. In moshi every sub-heading (3.2, 3.2.1, ...) is exactly
#: body-sized regular text, so font alone finds none of them. The numbering pattern
#: is the structural signal; the false positives it invites (`12.5 Hz`, `1.0 . 1020`,
#: `3.4 describes ...`) are rejected explicitly above.
_NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(\S.*)$")


_WORD_CAP = re.compile(r"\b[A-Z][a-z]{2,}|\b[A-Z]{2,}\b")


def _looks_like_title(t: str) -> bool:
    """A section title contains a Capitalised word (or an acronym).

    This single structural test replaces a pile of string-specific patches. It
    accepts "Encoder and Decoder Stacks" (the second word is lowercase, which is
    why a 'next word must be capitalised' rule wrongly deleted it) and rejects
    "seconds", "10 - 16, 2023, ..." and ". 10-5" -- none of which contain one.
    """
    if not t or len(t) > 90:
        return False
    if t.endswith(".") and len(t.split()) > 3:
        return False
    if len(t.split()) > 14:
        return False
    # A title is not a sentence fragment: a bare comma plus a lower-case opener
    # after it marks prose that happens to contain an acronym ("bits, using
    # integer scalar PTQ..."). Restored narrowly after the structure test alone
    # let this leak through -- the two tests disagree in public, which is why both
    # exist.
    if "," in t and not t[:1].isupper():
        return False
    return bool(_WORD_CAP.search(t))


def _reject_heading_candidate(text: str) -> bool:
    """Front-matter and table noise that is heading-shaped but is not a heading.

    Every rule here is grounded in a real false positive observed in these three
    PDFs (listed in docs/P2_INGEST.md), not in a guess about what PDFs look like.
    """
    t = text.strip()
    if not t or len(t) > 90:
        return True
    if _AUTHOR_HINT.search(t):
        return True                       # "Ashish Vaswani∗"
    if _AFFILIATION.match(t):
        return True                       # "Google Brain"
    if t.endswith(".") and len(t.split()) > 3:
        return True                       # "3.4 describes this architecture."
    words = t.split()
    if len(words) >= 2 and _MEASUREMENT_TAIL.match(words[1]):
        return True                       # "12.5 Hz"  /  "10 seconds"
    if len(words) >= 2 and t[:1].isdigit() and any(c in t for c in "\u00b7\u00d7"):
        return True                       # "5 · 10-5"
    if _MEASUREMENT_VALUE.match(t) and any(c in t for c in "\u00b7\u00d7"):
        return True                       # "1.0 · 1020"
    if t.endswith(":"):
        return True                       # a sub-label is handled by its own branch
    return False


#: A heading title never contains a URL, an ellipsis, an equation, or a comma-run.
_TITLE_REJECT = re.compile(
    r"(https?://|www\.|\bdoi\b|\.\.\.|\u2026|[=<>\u2264\u2265\u2211\u221a]|^[\d\s,.\-\u2212]+$)",
    re.I)


def _section_number_plausible(number: str, seen: set[str], last: Optional[str]) -> bool:
    """Does this number ADVANCE the outline?

    The decisive property is monotonicity: a real outline visits 1, 2, 3, 3.1, 3.2,
    3.2.1 ... in order. Footnotes (`4 https://...`), table values (`2 . 10-6`),
    enumerations (`1 Deduplication of source content`) and examples (`4 How to
    identify ...`) all break that order, which is why this rule removes them
    wholesale instead of chasing each pattern.
    """
    try:
        nums = tuple(int(x) for x in number.split("."))
    except ValueError:
        return False
    if not nums or nums[0] > 20:            # no 41.29 in a 7-section paper
        return False
    if last is None:
        return True                          # first numbered heading of the document
    try:
        prev = tuple(int(x) for x in last.split("."))
    except ValueError:
        return False
    if nums == prev:
        return False
    # a new top-level chapter must be greater than the last one
    if len(nums) == 1:
        return nums[0] > prev[0] or (nums[0] == prev[0] + 1)
    # a child must extend a chapter at or above the last chapter, or be the next
    # sibling/deeper number within the current chapter
    if nums[0] < prev[0]:
        return False
    if nums[0] == prev[0]:
        # sibling (3.3 after 3.2) or child of something already seen (3.2.1 after 3.2)
        return (nums > prev) if len(nums) == len(prev) else (
            nums[:len(prev)] == prev or len(nums) > len(prev))
    return len(nums) > 1 and nums[0] == prev[0] + 1


def build_sections(pages: list[dict], paper: str) -> tuple[list[Section], list[PageReport]]:
    """Assemble sections, handling the extracted-text quirks.

    A heading is one of:
      * `N.N Title` on one line, bold or larger than body;
      * `N.N` on one line followed by a title line (attention splits these);
      * a bold, body-sized, title-shaped line ("Encoder:") -- a sub-label;
      * the word Abstract.
    Front matter (authors, affiliations) is rejected explicitly, because an author
    list is bold and body-sized and every rule above matches it.
    """
    body = _body_size(pages)
    sections: list[Section] = []
    reports: list[PageReport] = []
    current: Optional[Section] = None
    buf: list[str] = []
    seen_content = False        # has real body text appeared yet?
    seen: set[str] = set()      # section numbers already emitted
    last_number: Optional[str] = None   # the previous numbered heading

    def flush() -> None:
        nonlocal current, buf
        if current is not None:
            current.text = "\n".join(buf).strip()
            sections.append(current)
        current, buf = None, []

    for page in pages:
        kept = 0
        dropped = 0
        lines = page["lines"]
        junk = looks_like_figure_junk([ln["text"] for ln in lines])
        i = 0
        while i < len(lines):
            ln = lines[i]
            text = ln["text"].strip()
            heading_like = _is_heading_line(ln, body)

            number, title = "", ""
            m = _NUM_AND_TITLE.match(text) or _NUMBERED.match(text)
            cand = m.group(2).strip() if m else ""
            if (m and len(text) <= 90
                    and not _reject_heading_candidate(cand)
                    and not _TITLE_REJECT.search(cand)
                    and _looks_like_title(cand)
                    and (heading_like or _section_number_plausible(
                        m.group(1), seen, last_number))):
                number, title = m.group(1), cand
            elif _NUM.match(text) and heading_like:
                # split heading: "3.1" then "Encoder and Decoder Stacks".
                # The title line need NOT be bold: in moshi/hnet it is 12pt regular.
                if i + 1 < len(lines):
                    nxt = lines[i + 1]["text"].strip()
                    if (nxt and not _NUM.match(nxt) and len(nxt) <= 90
                            and not _reject_heading_candidate(nxt)
                            and (nxt[0].isupper() or nxt[0].isdigit())):
                        number, title = _NUM.match(text).group(1), nxt
                        i += 1
            elif _ABSTRACT.match(text):
                title = "Abstract"
            elif (heading_like and body and abs(ln["size"] - body) < 0.3
                  and 3 <= len(text) <= 60 and text[0].isupper()
                  and len(text.split()) <= 5
                  and not _reject_heading_candidate(text)
                  and not _NUM_AND_TITLE.match(text)):
                # A body-sized bold label such as "Encoder:". Only promote it to a
                # section when it carries a colon; otherwise it is a paragraph lead-in
                # and stays inside the current section's text.
                if text.endswith(":"):
                    title = text.rstrip(":")

            if title:
                flush()
                if number:
                    seen.add(number)
                    last_number = number
                current = Section(paper=paper, number=number, title=title,
                                  page=page["page"])
                seen_content = False
                i += 1
                continue

            if len(text) >= _MIN_VISIBLE_CHARS and not junk:
                buf.append(text)
                kept += 1
                seen_content = True
            else:
                dropped += 1
            i += 1
        reports.append(PageReport(page=page["page"], n_lines=len(lines),
                                  n_dropped_short=dropped, figure_junk=junk,
                                  chars=kept))
    flush()
    return sections, reports


# ----------------------------------------------------------------------- chunks

@dataclass
class ChunkRecord:
    chunk: Chunk
    flags: list[str] = field(default_factory=list)
    digit_ratio: float = 0.0

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id


def _slug(section: Section) -> str:
    return section.number if section.number else "s0"


def split_section(section: Section, chunk_size: int, overlap: int,
                  label: str) -> list[ChunkRecord]:
    """Character-window split with paragraph alignment and overlap.

    Deliberately NOT paragraph-only: a paper has single 5K-character paragraphs,
    and one chunk per paragraph would defeat retrieval.
    """
    text = section.text
    if not text.strip():
        return []
    out: list[ChunkRecord] = []
    start = 0
    n = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            # do not cut mid-word: back off to the last space within 15% of the end
            window = text[max(start, end - int(chunk_size * 0.15)):end]
            space = window.rfind(" ")
            if space > 0:
                end = max(start, end - int(chunk_size * 0.15)) + space
        piece = text[start:end].strip()
        if piece:
            cid = f"{label}:s{_slug(section)}:c{n:04d}"
            chunk = Chunk(chunk_id=cid, paper=section.paper,
                          section=section.path, page=section.page, text=piece)
            flags: list[str] = []
            if is_mostly_digits(piece):
                flags.append("mostly_digits")
            if len(piece) < 200:
                flags.append("short")
            if _REFERENCE_HINT.match(section.title.strip()):
                flags.append("references")
            # tables/equations: heavy numeric or symbol content relative to words
            if digit_ratio(piece) > 0.15 and not is_mostly_digits(piece):
                flags.append("numeric_dense")
            if _looks_like_equation(piece):
                flags.append("equation")
            if has_embedded_caption(piece):
                # Not a defect to hide: these are the chunks the retrieval section
                # cites as evidence that PDF tables damage a text retriever.
                flags.append("caption")
            if _CAPTION.match(piece.strip()):
                flags.append("caption_lead")
            out.append(ChunkRecord(chunk=chunk, flags=flags if flags else ["ok"],
                                   digit_ratio=round(digit_ratio(piece), 3)))
            n += 1
        if end >= len(text):
            break
        # Snap the next start forward to a word boundary. Without this the overlap
        # starts mid-word, so a quote spanning the boundary is not a verbatim
        # substring of EITHER chunk -- an H2 failure that only surfaces later, as
        # an inexplicable verify() rejection.
        nxt = max(start + 1, end - overlap)
        while nxt < len(text) and not text[nxt - 1].isspace():
            nxt += 1
        start = nxt if nxt < len(text) else end
    return out


_EQ_HINT = re.compile(r"[=≈≤≥∑∏√∫]|\bsoftmax\b|\bsigmoid\b|\\frac|\balpha\b|\bbeta\b")

#: A table or figure caption embedded in running text. Measured on the real corpus:
#: 50 of 449 otherwise-clean chunks (11%) contain one, and the chunk that holds a
#: caption usually also holds the mangled table itself -- half prose, half numbers.
_CAPTION = re.compile(r"\b(Table|Figure|Algorithm)\s+\d+[:.]")


def has_embedded_caption(text: str) -> bool:
    return bool(_CAPTION.search(text))


def _looks_like_equation(text: str) -> bool:
    hits = len(_EQ_HINT.findall(text))
    words = max(1, len(text.split()))
    return hits >= 3 and hits / words > 0.03


# ---------------------------------------------------------------------- ingest

@dataclass
class PaperManifest:
    paper: str
    title: str
    arxiv: str
    stamp: str
    file: str
    sha256: str
    n_pages: int
    n_sections: int
    n_chunks: int
    n_flagged: int
    chunk_size: int
    overlap: int
    ingest_utc: str
    warnings: list[str] = field(default_factory=list)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ingest_paper(key: str, pdf_dir: Path, chunk_size: int, overlap: int
                 ) -> tuple[list[ChunkRecord], PaperManifest, list[PageReport]]:
    meta = PAPERS[key]
    path = pdf_dir / meta["file"]
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing; see docs/P2_INGEST.md for how to restore")
    pages = extract_pages(path)
    sections, reports = build_sections(pages, key)
    label = meta["label"]
    records: list[ChunkRecord] = []
    for sec in sections:
        records.extend(split_section(sec, chunk_size, overlap, label))

    warnings = []
    junk_pages = [r.page for r in reports if r.figure_junk]
    if junk_pages:
        warnings.append(f"{len(junk_pages)} figure-junk pages skipped: {junk_pages[:8]}")
    if not sections:
        warnings.append("no sections detected")
    if any(r.n_dropped_short for r in reports):
        tot = sum(r.n_dropped_short for r in reports)
        warnings.append(f"{tot} sub-{_MIN_VISIBLE_CHARS}-char lines dropped")

    manifest = PaperManifest(
        paper=key, title=meta["title"], arxiv=meta["arxiv"], stamp=meta["stamp"],
        file=meta["file"], sha256=sha256_of(path), n_pages=len(pages),
        n_sections=len(sections), n_chunks=len(records),
        n_flagged=sum(1 for r in records if "ok" not in r.flags),
        chunk_size=chunk_size, overlap=overlap,
        ingest_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        warnings=warnings,
    )
    return records, manifest, reports


def write_outputs(records: list[ChunkRecord], manifests: list[PaperManifest],
                  out_dir: Path, samples_per_paper: int = 10,
                  seed: int = 7) -> dict[str, Path]:
    """Write chunks.jsonl plus three human-review artefacts.

    The review files exist because the supervisor's instruction is to eyeball the
    text: tests can prove a chunker is self-consistent, not that it is useful.
    """
    import random

    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    paths: dict[str, Path] = {}

    chunks_path = out_dir / "chunks.jsonl"
    with open(chunks_path, "w", encoding="utf-8") as f:
        for rec in records:
            row = asdict(rec.chunk)
            row["flags"] = rec.flags
            row["digit_ratio"] = rec.digit_ratio
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    paths["chunks"] = chunks_path

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chunk_size": manifests[0].chunk_size if manifests else None,
        "overlap": manifests[0].overlap if manifests else None,
        "papers": [asdict(m) for m in manifests],
        "total_chunks": len(records),
    }, indent=2), encoding="utf-8")
    paths["manifest"] = manifest_path

    # 1) random chunks per paper
    by_paper: dict[str, list[ChunkRecord]] = {}
    for r in records:
        by_paper.setdefault(r.chunk.paper, []).append(r)
    sample_path = out_dir / "review_random.md"
    with open(sample_path, "w", encoding="utf-8") as f:
        f.write("# Random chunks per paper (eyeball these)\n")
        for paper, recs in sorted(by_paper.items()):
            f.write(f"\n## {paper} ({len(recs)} chunks)\n")
            for rec in rng.sample(recs, min(samples_per_paper, len(recs))):
                c = rec.chunk
                f.write(f"\n### `{c.chunk_id}` p.{c.page} §{c.section} "
                        f"[{','.join(rec.flags)}]\n```\n{c.text[:1200]}\n```\n")
    paths["random"] = sample_path

    # 2) every flagged chunk (mostly digits / short / references)
    flagged = [r for r in records if "ok" not in r.flags]
    flag_path = out_dir / "review_flagged.md"
    with open(flag_path, "w", encoding="utf-8") as f:
        f.write(f"# Flagged chunks ({len(flagged)} of {len(records)})\n")
        for rec in flagged:
            c = rec.chunk
            f.write(f"\n## `{c.chunk_id}` p.{c.page} [{','.join(rec.flags)}] "
                    f"digit_ratio={rec.digit_ratio}\n```\n{c.text[:800]}\n```\n")
    paths["flagged"] = flag_path

    # 3) worst numeric rows, with page numbers, for the library-misleads-retriever
    worst = sorted(
        [r for r in records if r.digit_ratio > 0.15 or "caption" in r.flags],
        key=lambda r: (-r.digit_ratio, r.chunk.chunk_id))[:40]
    worst_path = out_dir / "review_numeric_worst.md"
    with open(worst_path, "w", encoding="utf-8") as f:
        f.write("# Worst numeric regions (table/equation damage)\n")
        f.write("\nBroken table rows are the concrete evidence for the "
                "'library misleads the retriever' section.\n")
        for rec in worst:
            c = rec.chunk
            f.write(f"\n## `{c.chunk_id}` p.{c.page} §{c.section} "
                    f"digit_ratio={rec.digit_ratio}\n```\n{c.text[:800]}\n```\n")
    paths["worst"] = worst_path
    return paths


def load_chunks(path: Path) -> list[Chunk]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            out.append(Chunk(chunk_id=row["chunk_id"], paper=row["paper"],
                             section=row["section"], page=row["page"],
                             text=row["text"]))
    return out


def ingest_all(cfg: Config, pdf_dir: Path = Path("data/papers"),
               out_dir: Path = Path("data/chunks"),
               chunk_size: Optional[int] = None,
               overlap: Optional[int] = None) -> dict[str, Path]:
    """Build every paper's chunks.

    Explicit sizes win over config: an experiment (P10) must be able to sweep sizes
    without editing the committed config, and a null config value must still raise
    when no explicit size is given (rule 4).
    """
    if chunk_size is None:
        chunk_size = cfg.require("retrieval.chunk_size")
    if overlap is None:
        overlap = cfg.require("retrieval.chunk_overlap")
    if overlap >= chunk_size:
        raise ValueError(f"overlap {overlap} must be < chunk_size {chunk_size}")
    all_records: list[ChunkRecord] = []
    manifests: list[PaperManifest] = []
    for key in PAPERS:
        records, manifest, _ = ingest_paper(key, pdf_dir, chunk_size, overlap)
        all_records.extend(records)
        manifests.append(manifest)
    return write_outputs(all_records, manifests, out_dir,
                         seed=cfg.get("standin.seed", 7))
