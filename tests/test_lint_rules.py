"""Mechanical checks for the working rules. These are the tests that stop *me*
from silently breaking rule 7 (monotonic time) or rule 1 (one mint site)."""
import ast
import re
from pathlib import Path

import pytest

from relay.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "relay"


def py_files(root=PKG):
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_mint_verified_only_called_from_verify_module():
    """H1: the ONLY call site of mint_verified() is pipeline/verify.py.

    P0: the file does not exist yet, so there must be no call sites at all.
    When P6 lands, this test pins the single allowed file.
    """
    allowed = {PKG / "pipeline" / "verify.py"}
    offenders = []
    for path in py_files(PKG):
        if path.name == "contracts.py":
            continue  # the definition itself
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if name == "mint_verified" and path not in allowed:
                    offenders.append((path.relative_to(ROOT), node.lineno))
    assert offenders == [], f"mint_verified called outside verify.py: {offenders}"


def test_no_direct_time_monotonic_outside_clock():
    """Rule 7: durations go through the injectable Clock."""
    # relay/standin/server.py is the SIMULATED PROVIDER: it must use raw time to
    # pretend to be a remote service. Rule 7 governs our own measurement of
    # durations, not a component whose job is to fabricate them (D-014).
    allowed = {PKG / "clock.py", PKG / "events.py", PKG / "standin" / "server.py"}
    offenders = []
    for path in py_files(PKG):
        if path in allowed:
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "time.monotonic(" in line and not line.strip().startswith("#"):
                offenders.append((path.relative_to(ROOT), i, line.strip()))
    assert offenders == [], offenders


def test_no_asyncio_sleep_outside_clock():
    """Rule 7 + testability: no bare asyncio.sleep in production code."""
    allowed = {PKG / "clock.py", PKG / "standin" / "server.py"}   # see D-014
    offenders = []
    for path in py_files(PKG):
        if path in allowed:
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if re.search(r"\basyncio\.sleep\(", s):
                offenders.append((path.relative_to(ROOT), i, s))
    assert offenders == [], offenders


def test_no_bare_except_in_package():
    """A bare `except:` swallows CancelledError (rule 8)."""
    offenders = []
    for path in py_files(PKG):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                offenders.append((path.relative_to(ROOT), node.lineno))
            if isinstance(node, ast.ExceptHandler):
                names = []
                t = node.type
                if isinstance(t, ast.Tuple):
                    names = [getattr(e, "id", "") for e in t.elts]
                elif isinstance(t, ast.Name):
                    names = [t.id]
                if "BaseException" in names:
                    offenders.append((path.relative_to(ROOT), node.lineno))
    assert offenders == [], offenders


def test_no_hardcoded_model_or_url_in_package():
    """Rule 4: model ids and endpoints come from config/.env, not literals."""
    bad = re.compile(r"gpt-oss-\d|api\.groq\.com|127\.0\.0\.1:\d+")
    offenders = []
    for path in py_files(PKG):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if bad.search(line):
                offenders.append((path.relative_to(ROOT), i, line.strip()))
    assert offenders == [], offenders


def test_contracts_module_is_a_leaf():
    """contracts.py must not import the rest of the package (keeps the contract honest)."""
    tree = ast.parse((PKG / "contracts.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    assert not any(m.startswith("relay") or m.startswith("httpx") for m in imported), imported


#: Config keys whose null is a REAL "not measured yet" (or a provisional stand-in
#: value), where a non-numeric fallback in code is legitimate and documented.
_PROVISIONAL = {
    "gateway.request_deadline_s",       # null until L5; *_standin_s is the fallback
    "gateway.request_deadline_standin_s",
    "user.patience_s",                  # null until measured; None = no timer
    "pipeline.max_tokens.draft",
    "pipeline.max_tokens.rewrite",
    "pipeline.top_k",
    "models.small.rpm",                 # UNVERIFIED docs-table value
    "retrieval.bm25_k1",
    "retrieval.bm25_b",
    "standin.seed",
}

#: Not config keys at all -- `dict.get` on parsed JSON. Listed so the rule stays
#: about CONFIG and does not turn into a ban on defensive coding.
_NOT_CONFIG = {"size", "t_mono", "fail_threshold", "open_s"}


def test_no_numeric_literal_fallback_for_measured_config_keys():
    """A MEASURED key must not carry a numeric literal default (BUG-028).

    `retrieval.gate_threshold` is committed as 15.86 *because it was measured*. The
    pipeline read it as `cfg.get(..., 15.0)`, so deleting or renaming the key would
    have moved every gate decision to 15.0 -- a number nobody measured -- silently.

    The rule is narrowed to keys whose value in `config/relay.yaml` is a NON-NULL
    number. Those are the ones a default can disagree with. A key that is itself
    null (or absent) is provisional by definition, and a documented default there is
    the intended design, not a hazard. An AST walk, so a call split across lines is
    still caught.
    """
    cfg = load_config(ROOT / "config" / "relay.yaml")

    def configured(dotted: str):
        try:
            return cfg.get(dotted)
        except ConfigError:
            return "absent"

    offenders = []
    for path in py_files(PKG) + py_files(ROOT / "scripts"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "get"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            key = node.args[0].value
            if not isinstance(key, str) or key in _PROVISIONAL or key in _NOT_CONFIG:
                continue
            default = node.args[1] if len(node.args) > 1 else None
            for kw in node.keywords:
                if kw.arg == "default":
                    default = kw.value
            if not (isinstance(default, ast.Constant)
                    and isinstance(default.value, (int, float))
                    and not isinstance(default.value, bool)):
                continue
            # only a hazard when config actually holds a different number
            v = configured(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool) \
                    and v != default.value:
                offenders.append((str(path.relative_to(ROOT)), node.lineno, key,
                                  default.value, v))
    assert offenders == [], (
        "measured config key(s) carry a numeric literal fallback that disagrees "
        f"with config/relay.yaml; use cfg.require(). (path, line, key, default, "
        f"configured) = {offenders}")
