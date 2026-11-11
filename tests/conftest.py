"""Register the chunk-index fixtures for every test module.

The fixtures live in `tests/indexes.py` rather than here so the builder can also be
called directly (`write_index(tmp_path, 900, 150)`) from tests that want a specific
chunking rather than a fixture.
"""
from tests.indexes import index_900, index_1200, pdf_dir, repo_root  # noqa: F401
