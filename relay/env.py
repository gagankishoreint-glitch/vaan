"""Minimal .env loader. No dependency, no magic.

`scripts/probe.py` told the user to "copy .env.example to .env" and then read only
`os.environ`, so following that instruction changed nothing and the probe failed with
the very message that had just been followed. A tool that instructs a setup step must
perform it.

Scope is deliberately tiny, because a config loader that guesses is worse than none:

  * `KEY=value`, whitespace stripped around both.
  * `export KEY=value` accepted (people paste from shell snippets).
  * `#` starts a comment only at the start of a line or after whitespace, so a `#`
    inside a value survives -- API keys and URLs contain `#` more often than you
    would like.
  * Single or double quotes around the value are stripped.
  * A line with no `=` is ignored rather than raising: .env files in the wild have
    blank banner lines.

Existing environment variables ALWAYS win. A developer who exported GROQ_API_KEY
for one command must not have it silently overridden by a stale .env file.

    load_env()                      # .env in cwd, then next to the repo root
    load_env("/path/to/.env")       # explicit

Set `RELAY_NO_DOTENV=1` to disarm the loader entirely. That exists for the test suite:
a developer machine with a real .env full of credentials must not be able to turn a
unit test into a live API call. Tests are about code, not about whichever secrets
happen to be sitting next to the checkout.

    python -m pytest -q tests/test_env.py                    -> 7 passed
    RELAY_NO_DOTENV=1 python -c "from relay.env import load_env; print(load_env())"
                                                             -> None, .env or not
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Optional


def parse_env_text(text: str) -> dict[str, str]:
    """Parse .env content into a dict. Pure, so it can be tested without files."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        # Strip an inline comment only when it follows whitespace.
        hash_at = value.find(" #")
        if hash_at >= 0:
            value = value[:hash_at].rstrip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[key] = value
    return out


def dotenv_disabled() -> bool:
    """True when RELAY_NO_DOTENV is set to a truthy value.

    Read from the live environment on every call rather than cached at import: a test
    that sets the flag must take effect even though relay.env was imported long ago.
    """
    return os.environ.get("RELAY_NO_DOTENV", "").strip().lower() in (
        "1", "true", "yes", "on")


def find_env_file(start: Optional[Path] = None,
                  extra: Iterable[Path] = ()) -> Optional[Path]:
    """First existing .env: cwd, then this repo's root, then any `extra` paths."""
    here = Path(start) if start else Path.cwd()
    repo_root = Path(__file__).resolve().parent.parent
    for cand in (here / ".env", repo_root / ".env", *extra):
        if cand.is_file():
            return cand
    return None


def load_env(path: Optional[str | Path] = None, *, override: bool = False,
             environ: Optional[MutableMapping[str, str]] = None
             ) -> Optional[Path]:
    """Load .env into `environ` (default os.environ). Returns file used or None.

    `override=False` (the default, and what every script should use) keeps any
    variable that is already set.

    `environ` is injectable so callers can resolve configuration against a mapping
    they own. `scripts/probe.py` uses it to answer "is there a key?" against a dict
    the caller supplied, which makes that path testable without the process
    environment -- and therefore without a real key -- ever being consulted.
    """
    if dotenv_disabled():
        return None
    target = os.environ if environ is None else environ
    env_file = Path(path) if path else find_env_file()
    if env_file is None or not env_file.is_file():
        return None
    for key, value in parse_env_text(env_file.read_text(encoding="utf-8")).items():
        if override or key not in target:
            target[key] = value
    return env_file
