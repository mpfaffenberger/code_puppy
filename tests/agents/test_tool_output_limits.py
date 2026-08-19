"""Tests for code_puppy.agents._tool_output_limits (pydantic-ai-harness backed).

Covers:
- get_tool_output_limit_chars() — config parsing, defaults, the 0-disables
  contract, and garbage tolerance
- build_tool_output_limits() — config → ToolOutputLimits wiring: band
  threshold, Spill-then-Truncate action shape, store rooted under CONFIG_DIR
- end-to-end reduction — an agent whose tool returns an oversized payload
  persists a reduced ToolReturnPart and can read the full payload back
  through the capability's read_tool_result tool
"""

from __future__ import annotations

from unittest.mock import patch

from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai_harness.tool_output_limits import (
    LocalFileStore,
    Spill,
    ToolOutputLimits,
    Truncate,
)

from code_puppy.agents import _tool_output_limits
from code_puppy.agents._tool_output_limits import (
    OVERFLOW_DIR_NAME,
    build_tool_output_limits,
)
from code_puppy.config import (
    TOOL_OUTPUT_LIMIT_CHARS_DEFAULT,
    get_tool_output_limit_chars,
)

# ---------- get_tool_output_limit_chars() ------------------------------------


class TestGetToolOutputLimitChars:
    def _with_value(self, value):
        return patch("code_puppy.config.get_value", return_value=value)

    def test_unset_returns_default(self):
        with self._with_value(None):
            assert get_tool_output_limit_chars() == TOOL_OUTPUT_LIMIT_CHARS_DEFAULT

    def test_empty_string_returns_default(self):
        with self._with_value("   "):
            assert get_tool_output_limit_chars() == TOOL_OUTPUT_LIMIT_CHARS_DEFAULT

    def test_zero_is_explicit_opt_out(self):
        with self._with_value("0"):
            assert get_tool_output_limit_chars() == 0

    def test_positive_value_honoured_without_upper_clamp(self):
        with self._with_value("250000"):
            assert get_tool_output_limit_chars() == 250_000

    def test_garbage_returns_default(self):
        with self._with_value("many chars pls"):
            assert get_tool_output_limit_chars() == TOOL_OUTPUT_LIMIT_CHARS_DEFAULT

    def test_negative_returns_default(self):
        with self._with_value("-5"):
            assert get_tool_output_limit_chars() == TOOL_OUTPUT_LIMIT_CHARS_DEFAULT


# ---------- build_tool_output_limits() ----------------------------------------


class TestBuildToolOutputLimits:
    def test_disabled_returns_none(self):
        with patch(
            "code_puppy.agents._tool_output_limits.get_tool_output_limit_chars",
            return_value=0,
        ):
            assert build_tool_output_limits() is None

    def test_default_shape(self, tmp_path):
        with (
            patch(
                "code_puppy.agents._tool_output_limits.get_tool_output_limit_chars",
                return_value=12_345,
            ),
            patch(
                "code_puppy.agents._tool_output_limits.CONFIG_DIR",
                str(tmp_path),
            ),
        ):
            capability = build_tool_output_limits()

        assert isinstance(capability, ToolOutputLimits)
        assert len(capability.bands) == 1
        band = capability.bands[0]
        assert band.over == 12_345
        # Lossless spill with a bounded truncation fallback — never a
        # silent drop.
        assert isinstance(band.action, Spill)
        assert isinstance(band.action.then, Truncate)
        # Store rooted under the config dir, not the shared temp default,
        # with a TTL so the overflow dir cannot grow forever.
        assert isinstance(capability.store, LocalFileStore)
        assert capability.store.base_dir == tmp_path / OVERFLOW_DIR_NAME
        assert capability.store.cleanup_after == _tool_output_limits.SPILL_TTL

    def test_fresh_instance_per_build(self):
        with patch(
            "code_puppy.agents._tool_output_limits.get_tool_output_limit_chars",
            return_value=10_000,
        ):
            assert build_tool_output_limits() is not build_tool_output_limits()


# ---------- end-to-end reduction ----------------------------------------------


BIG_PAYLOAD = "needle-" + ("x" * 50_000)


def _make_agent(capability: ToolOutputLimits) -> PydanticAgent:
    call_count = {"n": 0}

    def model_func(messages, info):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="big_tool", args={}, tool_call_id="call_1")
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = PydanticAgent(
        model=FunctionModel(model_func),
        capabilities=[capability],
    )

    @agent.tool_plain
    def big_tool() -> str:
        return BIG_PAYLOAD

    return agent


class TestEndToEndReduction:
    async def test_oversized_return_is_reduced_and_readable(self, tmp_path):
        with (
            patch(
                "code_puppy.agents._tool_output_limits.get_tool_output_limit_chars",
                return_value=10_000,
            ),
            patch(
                "code_puppy.agents._tool_output_limits.CONFIG_DIR",
                str(tmp_path),
            ),
        ):
            capability = build_tool_output_limits()
        assert capability is not None

        agent = _make_agent(capability)
        result = await agent.run("go")

        returns = [
            part
            for message in result.all_messages()
            for part in getattr(message, "parts", [])
            if isinstance(part, ToolReturnPart) and part.tool_name == "big_tool"
        ]
        assert len(returns) == 1
        persisted = returns[0].model_response_str()
        # Reduced at production time: the full payload never persists.
        assert len(persisted) < len(BIG_PAYLOAD)
        assert BIG_PAYLOAD not in persisted

        # The full payload was spilled to the store under the config dir.
        overflow_root = tmp_path / OVERFLOW_DIR_NAME
        spilled = [p for p in overflow_root.rglob("*") if p.is_file()]
        assert spilled, "expected the oversized payload to be spilled to disk"
        assert any(BIG_PAYLOAD in p.read_text(errors="ignore") for p in spilled), (
            "spill must be lossless"
        )

    async def test_small_return_passes_through(self, tmp_path):
        with (
            patch(
                "code_puppy.agents._tool_output_limits.get_tool_output_limit_chars",
                return_value=10_000,
            ),
            patch(
                "code_puppy.agents._tool_output_limits.CONFIG_DIR",
                str(tmp_path),
            ),
        ):
            capability = build_tool_output_limits()
        assert capability is not None

        call_count = {"n": 0}

        def model_func(messages, info):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name="small_tool", args={}, tool_call_id="call_1"
                        )
                    ]
                )
            return ModelResponse(parts=[TextPart(content="done")])

        agent = PydanticAgent(
            model=FunctionModel(model_func),
            capabilities=[capability],
        )

        @agent.tool_plain
        def small_tool() -> str:
            return "tiny result"

        result = await agent.run("go")
        returns = [
            part
            for message in result.all_messages()
            for part in getattr(message, "parts", [])
            if isinstance(part, ToolReturnPart) and part.tool_name == "small_tool"
        ]
        assert len(returns) == 1
        assert returns[0].model_response_str() == "tiny result"
        # Nothing spilled for an under-threshold return.
        overflow_root = tmp_path / OVERFLOW_DIR_NAME
        assert not overflow_root.exists() or not any(
            p.is_file() for p in overflow_root.rglob("*")
        )
