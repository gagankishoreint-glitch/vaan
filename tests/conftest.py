"""Shared test safety net and fixtures.

Three autouse guards live here, both of them consequences of real failures:

  * `_no_real_ledger`   -- a test wrote 234 fictional tokens to the real budget.
  * `_no_live_network`  -- a test spent 117 real Groq tokens through a .env file.
  * `_no_dotenv`        -- the suite must not read a developer's .env at all.
"""
from __future__ import annotations

import os

import pytest

from tests.indexes import index_900, index_1200, pdf_dir, repo_root  # noqa: F401


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    """The suite never loads a developer's .env.

    `test_go_without_key_exits_2` deletes GROQ_API_KEY and then ran the probe; the
    probe calls load_env(), which put the developer's real key straight back and the
    "no key" path became a live API call. Disarmed for every test rather than only
    for that one, because the next test to touch configuration would hit the same
    trap.
    """
    monkeypatch.setenv("RELAY_NO_DOTENV", "1")


@pytest.fixture(autouse=True)
def _no_real_ledger(tmp_path, monkeypatch):
    """No test may write the real token ledger.

    tests/test_probe_q06.py did exactly that: its first version patched the module
    constant while `Ledger.__init__` had already bound the path as a default
    argument, so the write landed in docs/TOKEN_LEDGER.md and charged 234 fictional
    tokens against the real budget. A test that can corrupt the budget is worse than
    no test, so the path is redirected for every test in the suite.
    """
    import scripts.probe as probe_mod
    monkeypatch.setattr(probe_mod, "LEDGER_PATH", tmp_path / "TOKEN_LEDGER.md",
                        raising=False)


# ------------------------------------------------------- no live network in tests

_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0"})


@pytest.fixture(autouse=True)
def _no_live_network(monkeypatch):
    """Any test that tries to open a socket to a non-localhost host fails loudly.

    This is the guard that was missing. A test on a developer machine reached the
    real Groq API because a .env file supplied a key and the loader reloaded it after
    the test deleted it; 117 tokens were charged and nothing objected. Absence of
    credentials is not a safety mechanism -- the failure mode has to be explicit.

    Localhost stays allowed: the stand-in suite legitimately talks to the local
    FastAPI stand-in on 127.0.0.1:8009.
    """
    import socket

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _check(sock, address, *a, **kw):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in _LOCAL_HOSTS:
            raise RuntimeError(
                f"test attempted a live network connection to {host!r}. "
                "Tests must not reach the internet: patch the transport, or point "
                "the client at the local stand-in. Set RELAY_ALLOW_NETWORK=1 to "
                "override deliberately (never in CI).")

    def connect(sock, address, *a, **kw):
        _check(sock, address)
        return real_connect(sock, address, *a, **kw)

    def connect_ex(sock, address, *a, **kw):
        _check(sock, address)
        return real_connect_ex(sock, address, *a, **kw)

    if os.environ.get("RELAY_ALLOW_NETWORK", "") in ("1", "true"):
        yield
        return
    monkeypatch.setattr(socket.socket, "connect", connect, raising=False)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex, raising=False)
    yield
