"""Tests for the opt-in speculative CodeMode wiring (`code_puppy.agents._code_mode`)."""

from unittest.mock import patch

from pydantic_ai.models.test import TestModel
from pydantic_ai_harness.code_mode import CodeMode

from code_puppy.agents._code_mode import (
    SANDBOXED_READ_ONLY_TOOLS,
    SilenceToolOutput,
    build_speculative_code_mode,
)
from code_puppy.agents.agent_monty import MontyAgent


def _leaves(capability):
    children = getattr(capability, "capabilities", None)
    if children is None:
        return [capability]
    out = []
    for child in children:
        out.extend(_leaves(child))
    return out


class _OrdinaryAgent:
    """An agent that never opted in; the attribute may not even exist."""


class TestBuildSpeculativeCodeMode:
    def test_agent_without_opt_in_gets_nothing(self):
        assert (
            build_speculative_code_mode(
                _OrdinaryAgent(), list(SANDBOXED_READ_ONLY_TOOLS)
            )
            == []
        )

    def test_disabled_by_config_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
            lambda: False,
        )
        assert (
            build_speculative_code_mode(MontyAgent(), list(SANDBOXED_READ_ONLY_TOOLS))
            == []
        )

    def test_opted_in_agent_folds_everything_and_speculates_the_read_only_trio(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
            lambda: True,
        )
        agent = MontyAgent()

        code_mode, silencer = build_speculative_code_mode(
            agent, agent.get_available_tools()
        )

        assert isinstance(code_mode, CodeMode)
        assert code_mode.tools == "all"
        assert code_mode.speculate == list(SANDBOXED_READ_ONLY_TOOLS)
        assert isinstance(silencer, SilenceToolOutput)

    def test_sandbox_gets_workspace_mount_and_os_access(self, monkeypatch):
        import os

        monkeypatch.setattr(
            "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
            lambda: True,
        )
        agent = MontyAgent()

        code_mode, _ = build_speculative_code_mode(agent, agent.get_available_tools())

        assert code_mode.mount is not None
        assert code_mode.mount.host_path == os.getcwd()
        assert code_mode.mount.virtual_path == os.getcwd()
        assert code_mode.mount.mode == "read-write"
        assert code_mode.os_access is not None

    def test_speculation_never_exceeds_the_read_only_trio(self, monkeypatch):
        """A tool added to an opted-in agent later is sandboxed but not launched early."""
        monkeypatch.setattr(
            "code_puppy.agents._code_mode.get_speculative_code_mode_enabled",
            lambda: True,
        )
        capability, _ = build_speculative_code_mode(
            MontyAgent(), ["read_file", "grep", "some_future_tool"]
        )

        assert capability.tools == "all"
        assert capability.speculate == ["read_file", "grep"]


class TestMontyAgent:
    def test_carries_the_full_code_puppy_toolkit(self):
        from code_puppy.agents.agent_code_puppy import CodePuppyAgent

        assert (
            MontyAgent().get_available_tools() == CodePuppyAgent().get_available_tools()
        )

    def test_toolkit_includes_the_speculatable_trio(self):
        tools = MontyAgent().get_available_tools()
        assert all(name in tools for name in SANDBOXED_READ_ONLY_TOOLS)

    def test_opts_into_speculative_code_mode(self):
        assert MontyAgent.speculative_code_mode is True

    def test_prompt_teaches_the_single_tool_contract(self):
        prompt = MontyAgent().get_system_prompt()
        assert "run_code" in prompt
        assert "literal" in prompt


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

    def test_monty_gets_code_mode(self):
        pydantic_agent = self._build(MontyAgent())

        code_modes = [
            leaf
            for leaf in _leaves(pydantic_agent._root_capability)
            if isinstance(leaf, CodeMode)
        ]
        assert len(code_modes) == 1
        assert code_modes[0].tools == "all"
        assert code_modes[0].speculate == list(SANDBOXED_READ_ONLY_TOOLS)

    def test_code_puppy_agent_does_not(self):
        from code_puppy.agents.agent_code_puppy import CodePuppyAgent

        pydantic_agent = self._build(CodePuppyAgent())

        assert not [
            leaf
            for leaf in _leaves(pydantic_agent._root_capability)
            if isinstance(leaf, CodeMode)
        ]
