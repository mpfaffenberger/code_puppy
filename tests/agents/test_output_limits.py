"""Unit tests for the harness output-limit capability builders.

These capabilities replaced the hand-rolled ``filter_huge_messages`` pass;
see ``code_puppy/agents/_output_limits.py`` for the migration story.
"""

from pathlib import Path

from pydantic_ai_harness.compaction import ClampOversizedMessages
from pydantic_ai_harness.tool_output_limits import Spill, ToolOutputLimits, Truncate

from code_puppy.agents import _output_limits
from code_puppy.agents._output_limits import (
    CLAMP_MAX_PART_TOKENS,
    build_response_clamp,
    build_tool_output_limits,
)
from code_puppy.config import (
    TOOL_OUTPUT_LIMIT_CHARS_DEFAULT,
    get_tool_output_limit_chars,
)


def test_default_threshold_builds_lossless_spill_band(monkeypatch):
    monkeypatch.setattr(_output_limits, "get_tool_output_limit_chars", lambda: 10_000)
    (cap,) = build_tool_output_limits()
    assert isinstance(cap, ToolOutputLimits)
    (band,) = list(cap.bands)
    assert band.over == 10_000
    assert isinstance(band.action, Spill)
    assert isinstance(band.action.then, Truncate)


def test_custom_threshold_is_honoured(monkeypatch):
    monkeypatch.setattr(_output_limits, "get_tool_output_limit_chars", lambda: 42)
    (cap,) = build_tool_output_limits()
    (band,) = list(cap.bands)
    assert band.over == 42


def test_zero_threshold_disables(monkeypatch):
    monkeypatch.setattr(_output_limits, "get_tool_output_limit_chars", lambda: 0)
    assert build_tool_output_limits() == []


def test_negative_threshold_disables(monkeypatch):
    monkeypatch.setattr(_output_limits, "get_tool_output_limit_chars", lambda: -5)
    assert build_tool_output_limits() == []


def test_spill_store_lives_under_config_dir(monkeypatch):
    monkeypatch.setattr(_output_limits, "get_tool_output_limit_chars", lambda: 123)
    (cap,) = build_tool_output_limits()
    base = cap.store.base_dir
    assert base is not None
    assert base.name == _output_limits.SPILL_DIR_NAME
    assert str(base).startswith(str(Path(_output_limits.CONFIG_DIR)))


def test_spill_store_has_ttl(monkeypatch):
    monkeypatch.setattr(_output_limits, "get_tool_output_limit_chars", lambda: 123)
    (cap,) = build_tool_output_limits()
    assert cap.store.cleanup_after == _output_limits.SPILL_TTL


def test_response_clamp_budget_matches_legacy_filter():
    clamp = build_response_clamp()
    assert isinstance(clamp, ClampOversizedMessages)
    assert clamp.max_part_tokens == CLAMP_MAX_PART_TOKENS == 50_000


def test_config_default_when_unset(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: None)
    assert get_tool_output_limit_chars() == TOOL_OUTPUT_LIMIT_CHARS_DEFAULT


def test_config_non_numeric_falls_back(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: "many")
    assert get_tool_output_limit_chars() == TOOL_OUTPUT_LIMIT_CHARS_DEFAULT


def test_config_explicit_zero_means_disabled(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: "0")
    assert get_tool_output_limit_chars() == 0
