"""Build chunk indexes for tests, from the PDFs, into a temporary directory.

Why this file exists: `data/chunks/**/*.jsonl` is git-ignored (the generated chunk
files are large and reproducible), so a fresh clone has NO chunk indexes. Tests that
read `data/chunks/exp900/chunks.jsonl` pass on a machine where someone has run
`scripts.ingest` and fail on a clean clone. That is the worst kind of test: it is
green where the author works and red everywhere else.

So tests build what they need from the PDFs, through the same ingest function the
CLI uses, into pytest's `tmp_path`. Nothing is read from a path that git ignores.

**When the PDFs are absent this FAILS, it does not skip.** A skip would quietly
reduce coverage to zero on exactly the machine least likely to notice, and a suite
that reports "passed" while testing nothing is worse than one that fails.
`data/papers/SHA256SUMS` is committed and names the files, so the fix is always the
same on every machine: restore the three PDFs there. See docs/P2_INGEST.md.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import pytest

from relay.ingest import PAPERS, ingest_paper

REPO = Path(__file__).resolve().parent.parent
PDF_DIR = REPO / "data" / "papers"

#: The settings the report compares. 900/150 is the committed one; 600/100 and
#: 1200/200 exist so the retrieval table can be reproduced from a fresh clone.
SETTINGS = {(600, 100), (900, 150), (1200, 200)}


def _require_pdfs() -> None:
    missing = [PDF_DIR / meta["file"] for meta in PAPERS.values()
               if not (PDF_DIR / meta["file"]).is_file()]
    if missing:
        pytest.fail(
            "PDFs missing, so the chunk index cannot be built:\n  "
            + "\n  ".join(str(m) for m in missing)
            + "\n\nThese tests do NOT skip when the corpus is absent: a suite that "
              "tests nothing must not report success.\nRestore the files named in "
              "data/papers/SHA256SUMS (committed) and verify with:\n"
              "    (cd data/papers && sha256sum -c SHA256SUMS)\n"
              "See docs/P2_INGEST.md.\n"
              f"Looked in: {PDF_DIR}",
            pytrace=False)


@functools.lru_cache(maxsize=None)
def _build(chunk_size: int, overlap: int) -> tuple[dict, ...]:
    """Ingest all three papers at one setting. Cached across tests in a session.

    ~2 s for all three papers at 1200/200, so building three settings costs ~6 s.
    That is cheaper than the confusion of a test whose result depends on whether
    someone remembered to run the ingest CLI.
    """
    _require_pdfs()
    out: list[dict] = []
    for key in PAPERS:
        records, _manifest, _pages = ingest_paper(key, PDF_DIR, chunk_size, overlap)
        for r in records:
            c = r.chunk          # ChunkRecord wraps a frozen Chunk
            out.append({"chunk_id": c.chunk_id, "paper": c.paper,
                        "section": c.section, "page": c.page, "text": c.text})
    return tuple(out)


def write_index(tmp_path: Path, chunk_size: int, overlap: int) -> Path:
    """Write a chunks.jsonl for one setting and return its path."""
    rows = _build(chunk_size, overlap)
    path = Path(tmp_path) / f"exp{chunk_size}" / "chunks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO


@pytest.fixture(scope="session")
def pdf_dir() -> Path:
    _require_pdfs()
    return PDF_DIR


@pytest.fixture
def index_900(tmp_path) -> "object":
    from relay.retrieval.bm25 import Retriever
    return Retriever.from_jsonl(write_index(tmp_path, 900, 150))


@pytest.fixture
def index_1200(tmp_path) -> "object":
    from relay.retrieval.bm25 import Retriever
    return Retriever.from_jsonl(write_index(tmp_path, 1200, 200))
