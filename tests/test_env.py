"""The .env loader, and the error text that has to match it.

The bug being pinned: the probe told the user to create .env and then never read it.
A tool that instructs a setup step must perform it.

Run:
    python -m pytest -q tests/test_env.py             -> 7 passed
"""
from __future__ import annotations

import os

import pytest

from relay.env import find_env_file, load_env, parse_env_text


def test_parses_the_shapes_found_in_real_dotenv_files():
    text = """
# a comment
GROQ_API_KEY=gsk_example
export GROQ_BASE_URL=https://api.groq.com/openai/v1
QUOTED="a value with spaces"
SINGLE='single quoted'
HASH_INSIDE=abc#def
HASH_COMMENT=abc # trailing comment
EMPTY=
not_a_pair_is_ignored
"""
    got = parse_env_text(text)
    assert got["GROQ_API_KEY"] == "gsk_example"
    assert got["GROQ_BASE_URL"] == "https://api.groq.com/openai/v1"
    assert got["QUOTED"] == "a value with spaces"
    assert got["SINGLE"] == "single quoted"
    assert got["HASH_INSIDE"] == "abc#def", "a # in a value must survive"
    assert got["HASH_COMMENT"] == "abc"
    assert got["EMPTY"] == ""
    assert "not_a_pair_is_ignored" not in got


def test_load_env_reads_a_file(tmp_path, monkeypatch):
    # This is the one module that tests the loader, so it must be able to exercise
    # it. Safe because every case here passes an explicit path inside tmp_path: an
    # explicit path cannot reach the developer's real .env. The autouse guard stays
    # on everywhere else, including the rest of this file.
    monkeypatch.delenv("RELAY_NO_DOTENV", raising=False)
    f = tmp_path / ".env"
    f.write_text("RELAY_TEST_KEY=from_file\n")
    monkeypatch.delenv("RELAY_TEST_KEY", raising=False)
    used = load_env(f)
    assert used == f
    assert os.environ["RELAY_TEST_KEY"] == "from_file"


def test_existing_environment_wins(tmp_path, monkeypatch):
    """An exported key must not be silently overridden by a stale .env."""
    monkeypatch.delenv("RELAY_NO_DOTENV", raising=False)
    f = tmp_path / ".env"
    f.write_text("RELAY_TEST_KEY=from_file\n")
    monkeypatch.setenv("RELAY_TEST_KEY", "from_env")
    load_env(f)
    assert os.environ["RELAY_TEST_KEY"] == "from_env"


def test_missing_file_returns_none_and_does_not_raise(tmp_path):
    assert load_env(tmp_path / "nope.env") is None


def test_find_env_file_prefers_cwd(tmp_path):
    (tmp_path / ".env").write_text("A=1\n")
    assert find_env_file(tmp_path) == tmp_path / ".env"


def test_example_file_lists_the_keys_the_probe_needs():
    from pathlib import Path
    example = Path(__file__).resolve().parent.parent / ".env.example"
    text = example.read_text()
    assert "GROQ_API_KEY" in text
    assert "GROQ_BASE_URL" in text


def test_probe_error_text_mentions_both_routes(capsys):
    """The message must match what the code actually does: export OR .env."""
    import scripts.probe as probe
    # `--env ""` resolves configuration against an empty mapping, so the message is
    # produced no matter what is in the process environment or in a real .env.
    rc = probe.main(["--go", "--max-tokens-total", "1000", "--timeout", "30",
                     "--env", ""])
    err = capsys.readouterr().err
    assert rc == 2
    assert "GROQ_API_KEY is not set" in err
    assert "export GROQ_API_KEY" in err
    assert ".env" in err
    assert "no .env file found" in err
