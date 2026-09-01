"""Unit tests for the harness output-limit capability builders.

These capabilities replaced the hand-rolled ``filter_huge_messages`` pass;
see ``code_puppy/agents/_output_limits.py`` for the migration story.
"""

from pathlib import Path

from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel
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


def test_config_negative_passes_through_as_disable(monkeypatch):
    """Pin the negative-disables semantic: a cleanup that normalizes negatives
    back to the default would silently re-enable an explicit opt-out."""
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: "-5")
    assert get_tool_output_limit_chars() == -5


def test_config_whitespace_only_falls_back(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: "   ")
    assert get_tool_output_limit_chars() == TOOL_OUTPUT_LIMIT_CHARS_DEFAULT


# ---------- end-to-end: a real agent run spills losslessly --------------------


BIG_PAYLOAD = "needle-" + ("x" * 50_000)


def _spilling_agent(cap: ToolOutputLimits, tool_result: str) -> PydanticAgent:
    """One-tool agent: first model turn calls big_tool, second returns text."""
    calls = {"n": 0}

    def model_func(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="big_tool", args={}, tool_call_id="c1")]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = PydanticAgent(model=FunctionModel(model_func), capabilities=[cap])

    @agent.tool_plain
    def big_tool() -> str:
        return tool_result

    return agent


def _big_tool_returns(result) -> list[ToolReturnPart]:
    return [
        p
        for m in result.all_messages()
        for p in getattr(m, "parts", [])
        if isinstance(p, ToolReturnPart) and p.tool_name == "big_tool"
    ]


async def test_oversized_return_is_reduced_and_spilled_losslessly(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(_output_limits, "get_tool_output_limit_chars", lambda: 10_000)
    monkeypatch.setattr(_output_limits, "CONFIG_DIR", str(tmp_path))
    (cap,) = build_tool_output_limits()

    result = await _spilling_agent(cap, BIG_PAYLOAD).run("go")

    (ret,) = _big_tool_returns(result)
    persisted = ret.model_response_str()
    # Reduced at production time: the full payload never enters history.
    assert len(persisted) < len(BIG_PAYLOAD)
    assert BIG_PAYLOAD not in persisted

    # Lossless: the full payload is recoverable from the spill store.
    spill_root = tmp_path / _output_limits.SPILL_DIR_NAME
    spilled = [p for p in spill_root.rglob("*") if p.is_file()]
    assert spilled, "expected the oversized payload to be spilled to disk"
    assert any(BIG_PAYLOAD in p.read_text(errors="ignore") for p in spilled)


async def test_small_return_passes_through_untouched(monkeypatch, tmp_path):
    monkeypatch.setattr(_output_limits, "get_tool_output_limit_chars", lambda: 10_000)
    monkeypatch.setattr(_output_limits, "CONFIG_DIR", str(tmp_path))
    (cap,) = build_tool_output_limits()

    result = await _spilling_agent(cap, "tiny result").run("go")

    (ret,) = _big_tool_returns(result)
    assert ret.model_response_str() == "tiny result"
    spill_root = tmp_path / _output_limits.SPILL_DIR_NAME
    assert not spill_root.exists() or not any(
        p.is_file() for p in spill_root.rglob("*")
    )
