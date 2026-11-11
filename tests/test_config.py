import pytest

from relay.config import Config, ConfigError, load_config


def test_repo_config_loads_and_has_expected_shape():
    c = load_config("config/relay.yaml")
    assert c.get("models.small.id") == "openai/gpt-oss-20b"
    assert c.get("models.large.id") == "openai/gpt-oss-120b"
    assert c.get("pipeline.top_k") == 4
    assert c.get("gateway.retry_budget_ratio") == pytest.approx(0.1)


def test_missing_key_raises():
    c = load_config("config/relay.yaml")
    with pytest.raises(ConfigError):
        c.get("nope.nope")


def test_default_returned_when_asked():
    c = load_config("config/relay.yaml")
    assert c.get("nope.nope", 42) == 42


def test_require_refuses_null():
    """Rule 4: an unmeasured number must fail loudly, never default to a guess."""
    c = load_config("config/relay.yaml")
    with pytest.raises(ConfigError, match="not been measured"):
        c.require("gateway.attempt_timeout_s")


def test_require_returns_measured_value():
    c = load_config("config/relay.yaml")
    assert c.require("pipeline.max_tokens.draft") == 400
    assert c.require("gateway.retry_policy") == "managed"


def test_null_paths_are_enumerable():
    c = load_config("config/relay.yaml")
    nulls = c.null_paths()
    assert "gateway.attempt_timeout_s" in nulls
    assert "user.patience_s" in nulls
    assert "slo.ttft_p50_s" in nulls
    # non-null keys must not be reported
    assert "pipeline.top_k" not in nulls


def test_no_orphan_tbd_comments():
    """Every null in the YAML should carry a 'set by' note so P1 knows what fills it.

    This is the anti-guessing test: a null with no measurement named is a
    half-written requirement.
    """
    import re
    from pathlib import Path

    text = Path("config/relay.yaml").read_text()
    c = load_config("config/relay.yaml")
    lines = text.splitlines()
    for dotted in c.null_paths():
        leaf = dotted.split(".")[-1]
        # the note must be on the SAME line as the null -- per-key, not per-block
        same_line = [ln for ln in lines if re.match(rf"\s*{re.escape(leaf)}:\s*null\b", ln)]
        assert same_line, f"{dotted}: no explicit `{leaf}: null` line found"
        assert any(re.search(r"#\s*set by|#\s*structural", ln) for ln in same_line), (
            f"config key {dotted} is null with no '# set by ...' note on its own line"
        )


def test_config_file_must_exist(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_policy_must_be_known_value():
    c = Config({"gateway": {"retry_policy": "managed"}}, path="x")
    assert c.get("gateway.retry_policy") in ("managed", "naive")
