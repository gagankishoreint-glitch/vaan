"""One place that reads config/relay.yaml.

Rule 4: no magic numbers. Anything a component needs comes from here.
A `null` in the YAML means "unknown, set by a named measurement". Using it
without setting it is a bug, so `require()` fails loudly instead of guessing.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

DEFAULT_PATH = Path("config/relay.yaml")
_MISSING = object()


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, raw: dict, path: Path):
        self.raw = raw
        self.path = path

    # -- access
    def get(self, dotted: str, default: Any = _MISSING) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                if default is _MISSING:
                    raise ConfigError(f"missing config key: {dotted} in {self.path}")
                return default
            node = node[part]
        return node

    def require(self, dotted: str) -> Any:
        """Get a key that must be a measured, non-null value."""
        value = self.get(dotted)
        if value is None:
            raise ConfigError(
                f"config key {dotted} is null: it has not been measured yet. "
                f"See config/relay.yaml and docs/OPEN_QUESTIONS.md for the "
                f"measurement that sets it. Refusing to invent a value (rule 4)."
            )
        return value

    def null_paths(self) -> list[str]:
        """Every dotted key whose value is null. Used by tests and by the report."""
        out: list[str] = []

        def walk(node: Any, prefix: str) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{prefix}.{k}" if prefix else str(k))
            elif node is None:
                out.append(prefix)

        walk(self.raw, "")
        return sorted(out)


def load_config(path: Optional[str | Path] = None) -> Config:
    p = Path(path or os.environ.get("RELAY_CONFIG", DEFAULT_PATH))
    if not p.is_file():
        raise ConfigError(f"config file not found: {p}")
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping, got {type(raw).__name__}")
    return Config(raw, p)
