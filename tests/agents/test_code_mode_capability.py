"""Tests for the speculative CodeMode wiring (`code_puppy.agents._code_mode`)."""

from unittest.mock import patch

from pydantic_ai.models.test import TestModel
from pydantic_ai_harness.code_mode import CodeMode

from code_puppy.agents._code_mode import (
    SANDBOXED_READ_ONLY_TOOLS,
    build_speculative_code_mode,
)


def _leaves(capability):
    children = getattr(capability, "capabilities", None)
    if children is None:
        return [capability]
    out = []
    for child in children:
        out.extend(_leaves(child))
    return out


class TestBuildSpeculativeCodeMode:
    def test_disabled_by_config_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
            lambda: False,
        )
        assert build_speculative_code_mode(list(SANDBOXED_READ_ONLY_TOOLS)) == []

    def test_agent_without_read_only_tools_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
            lambda: True,
        )
        assert build_speculative_code_mode(["agent_run_shell_command"]) == []

    def test_folds_and_speculates_only_declared_read_only_tools(self, monkeypatch):
        monkeypatch.setattr(
            "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
            lambda: True,
        )
        built = build_speculative_code_mode(["read_file", "grep", "edit_file"])

        assert len(built) == 1
        capability = built[0]
        assert isinstance(capability, CodeMode)
        assert capability.tools == ["read_file", "grep"]
        assert capability.speculate == ["read_file", "grep"]

    def test_write_and_shell_tools_are_never_folded(self, monkeypatch):
        monkeypatch.setattr(
            "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
            lambda: True,
        )
        tools = [
            "list_files",
            "read_file",
            "grep",
            "edit_file",
            "delete_file",
            "agent_run_shell_command",
            "invoke_agent",
        ]
        (capability,) = build_speculative_code_mode(tools)
        assert set(capability.tools) == set(SANDBOXED_READ_ONLY_TOOLS)


class TestBuilderIntegration:
    def test_code_puppy_agent_gets_code_mode(self):
        """The built agent's capability tree contains the configured CodeMode leaf."""
        from code_puppy.agents import _builder
        from code_puppy.agents.agent_code_puppy import CodePuppyAgent

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
            pydantic_agent = _builder.build_pydantic_agent(CodePuppyAgent())

        leaves = _leaves(pydantic_agent._root_capability)
        code_modes = [leaf for leaf in leaves if isinstance(leaf, CodeMode)]
        assert len(code_modes) == 1
        assert code_modes[0].tools == list(SANDBOXED_READ_ONLY_TOOLS)
        assert code_modes[0].speculate == list(SANDBOXED_READ_ONLY_TOOLS)
