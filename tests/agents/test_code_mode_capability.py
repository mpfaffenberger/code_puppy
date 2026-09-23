"""Tests for the flag-switched speculative CodeMode wiring (`code_puppy.agents._code_mode`)."""

import ast
import importlib
import warnings
from unittest.mock import Mock, patch

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai_harness.code_mode import CodeMode

from code_puppy.agents import _code_mode
from code_puppy.agents._code_mode import (
    SANDBOXED_READ_ONLY_TOOLS,
    SilenceToolOutput,
    _sandbox_tool,
    build_speculative_code_mode,
)
from code_puppy.agents._code_mode_guidance import CODE_MODE_GUIDANCE, CodeModeGuidance
from code_puppy.agents._wire_tool_names import StreamedToolNameNormalizer
from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.capabilities.eager_timing import EagerTiming


def _leaves(capability):
    children = getattr(capability, "capabilities", None)
    if children is None:
        return [capability]
    out = []
    for child in children:
        out.extend(_leaves(child))
    return out


@pytest.fixture
def flag(monkeypatch):
    state = {"enabled": True}
    monkeypatch.setattr(
        "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
        lambda: state["enabled"],
    )
    return state


class TestBuildSpeculativeCodeMode:
    def test_only_creation_and_replacement_stay_native(self):
        ctx = Mock(spec=RunContext)
        for name in ("create_file", "replace_in_file"):
            assert not _sandbox_tool(ctx, ToolDefinition(name=name))
        for name in (
            *SANDBOXED_READ_ONLY_TOOLS,
            "delete_file",
            "delete_snippet",
            "agent_run_shell_command",
            "some_future_tool",
        ):
            assert _sandbox_tool(ctx, ToolDefinition(name=name))

    def test_disabled_by_config_returns_empty(self, flag):
        flag["enabled"] = False
        assert build_speculative_code_mode(list(SANDBOXED_READ_ONLY_TOOLS)) == []

    def test_no_agent_opt_in_is_required(self, flag):
        """The flag alone decides; there is no per-agent attribute to set."""
        tools = CodePuppyAgent().get_available_tools()

        code_mode, silencer, timing, normalizer, guidance = build_speculative_code_mode(
            tools
        )

        assert isinstance(code_mode, CodeMode)
        assert code_mode.tools is _sandbox_tool
        assert code_mode.eager is True
        assert code_mode.speculate == list(SANDBOXED_READ_ONLY_TOOLS)
        assert isinstance(silencer, SilenceToolOutput)
        assert isinstance(timing, EagerTiming)
        assert isinstance(normalizer, StreamedToolNameNormalizer)
        assert isinstance(guidance, CodeModeGuidance)

    def test_sandbox_gets_workspace_mount_and_os_access(self, flag):
        import os

        code_mode, *_ = build_speculative_code_mode(["read_file"])

        assert code_mode.mount is not None
        assert code_mode.mount.host_path == os.getcwd()
        assert code_mode.mount.virtual_path == os.getcwd()
        assert code_mode.mount.mode == "read-write"
        assert code_mode.os_access is not None

    def test_speculation_never_exceeds_the_read_only_trio(self, flag):
        """A tool the agent does not declare is never launched early."""
        capability, *_ = build_speculative_code_mode(
            ["read_file", "grep", "some_future_tool"]
        )

        assert capability.tools is _sandbox_tool
        assert capability.speculate == ["read_file", "grep"]


class TestCodeModeGuidance:
    def test_guidance_rides_as_capability_instructions(self):
        assert CodeModeGuidance().get_instructions() is CODE_MODE_GUIDANCE

    def test_guidance_teaches_the_native_write_contract(self):
        assert "run_code" in CODE_MODE_GUIDANCE
        assert "literal" in CODE_MODE_GUIDANCE
        assert "Use `create_file` and `replace_in_file` as\nnative tools" in (
            CODE_MODE_GUIDANCE
        )
        assert "Speculative Puppy" not in CODE_MODE_GUIDANCE


def test_only_generated_invalid_escape_warnings_are_suppressed():
    """Streaming AST probes must not flood the terminal with SyntaxWarnings."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        importlib.reload(_code_mode)

        for _ in range(3):
            ast.parse(r'pattern = "\("')
        assert not captured

        ast.parse(r'pattern = "\("', filename="project_file.py")
        warnings.warn("another syntax warning", SyntaxWarning)
        warnings.warn("runtime warning", RuntimeWarning)

    assert len(captured) == 3
    assert "invalid escape sequence" in str(captured[0].message)
    assert str(captured[1].message) == "another syntax warning"
    assert captured[2].category is RuntimeWarning


class TestBuilderIntegration:
    def _build(self, agent):
        from code_puppy.agents import _builder

        with (
            patch.object(
                _builder,
                "load_model_with_fallback",
                lambda *_args, **_kwargs: (TestModel(), "test-model"),
            ),
            patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
            patch.object(_builder, "load_mcp_servers", lambda **_kwargs: []),
            patch.object(
                _builder, "make_model_settings", lambda *_args, **_kwargs: None
            ),
            patch(
                "code_puppy.tools.register_tools_for_agent",
                lambda *_args, **_kwargs: None,
            ),
        ):
            return _builder.build_pydantic_agent(agent)

    def _code_modes(self, pydantic_agent):
        return [
            leaf
            for leaf in _leaves(pydantic_agent._root_capability)
            if isinstance(leaf, CodeMode)
        ]

    def test_any_agent_gets_code_mode_when_flag_is_on(self, flag):
        code_modes = self._code_modes(self._build(CodePuppyAgent()))

        assert len(code_modes) == 1
        # Name, not identity: the warnings test above reloads the module.
        assert code_modes[0].tools.__name__ == _sandbox_tool.__name__
        assert code_modes[0].speculate == list(SANDBOXED_READ_ONLY_TOOLS)

    def test_flag_off_keeps_native_tools(self, flag):
        flag["enabled"] = False
        assert not self._code_modes(self._build(CodePuppyAgent()))
