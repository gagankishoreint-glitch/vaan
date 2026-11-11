"""P2 CLI: build data/chunks/ from the three PDFs.

    python -m scripts.ingest                 # uses config chunk_size/overlap
    python -m scripts.ingest --chunk-size 900 --overlap 150 --out data/chunks/exp900

Chunk ids embed the size-independent section path, so re-running with a different
size changes the id only via the c-index. The manifest records size, overlap, the
ingest timestamp and the sha256 of each PDF, so chunk ids are reproducible.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from relay.config import ConfigError, load_config
from relay.ingest import PAPERS, ingest_all, ingest_paper, write_outputs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scripts.ingest")
    ap.add_argument("--config", default="config/relay.yaml")
    ap.add_argument("--pdf-dir", default="data/papers")
    ap.add_argument("--out", default="data/chunks")
    ap.add_argument("--chunk-size", type=int, default=None)
    ap.add_argument("--overlap", type=int, default=None)
    a = ap.parse_args(argv)

    try:
        cfg = load_config(a.config)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    size = a.chunk_size if a.chunk_size is not None else cfg.get("retrieval.chunk_size")
    overlap = a.overlap if a.overlap is not None else cfg.get("retrieval.chunk_overlap")
    if size is None:
        print("error: retrieval.chunk_size is null in config and --chunk-size was not "
              "given. It is set by the P2/P10 retrieval experiment; pass --chunk-size "
              "explicitly for now.", file=sys.stderr)
        return 2
    if overlap is None:
        overlap = int(size * 0.15)
        print(f"note: retrieval.chunk_overlap is null; using 15% ({overlap}) for now. "
              f"It is set by P10.", file=sys.stderr)
    if overlap >= size:
        print(f"error: overlap {overlap} must be < chunk_size {size}", file=sys.stderr)
        return 2

    try:
        paths = ingest_all(cfg, Path(a.pdf_dir), Path(a.out),
                           chunk_size=size, overlap=overlap)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for k, p in paths.items():
        print(f"  {k:<9} {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
