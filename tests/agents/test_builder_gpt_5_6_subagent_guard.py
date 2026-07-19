"""Tests for the GPT-5.6 tool-safety guardrails in _builder.

Covers two independent conditional guardrails that get appended to the
system prompt only when the resolved model is a GPT-5.6 family model AND
the agent exposes the relevant tool:

* ``_GPT_5_6_INVOKE_AGENT_GUARD_TEXT`` — fires when the agent exposes
  ``invoke_agent``. Tells the model to delegate sparingly and to never
  invoke ``planning-agent``.
* ``_GPT_5_6_RUN_SHELL_COMMAND_GUARD_TEXT`` — fires when the agent exposes
  ``agent_run_shell_command``. Tells the model to be cautious about
  commands or API calls that delete, overwrite, or make unrecoverable
  changes.

If either condition is false (model or tool gate) the corresponding
guardrail must be omitted.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_puppy.agents import _builder


# --------------------------------------------------------------------------- #
# _is_gpt_5_6_family classifier                                                #
# --------------------------------------------------------------------------- #


class TestIsGpt5Family:
    """The matcher must treat ``gpt-5.6`` as a delimited segment."""

    @pytest.mark.parametrize(
        "model_name",
        [
            "gpt-5.6",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
            "codex-gpt-5.6-sol",
            "codex-gpt-5.6-luna",
            "GPT-5.6",
            "Codex-GPT-5.6-SOL",
        ],
    )
    def test_matches_real_gpt_5_6_names(self, model_name):
        assert _builder._is_gpt_5_6_family(model_name) is True

    @pytest.mark.parametrize(
        "model_name",
        [
            # Adjacent alnum chars must not be part of the segment.
            "gpt-5.61",
            "gpt-5.61-foo",
            "xgpt-5.6",
            "xgpt-5.6-foo",
            "gpt-5.65-foo",
            # Completely unrelated families.
            "gpt-5.5",
            "gpt-5.5-mini",
            "gpt-5.4",
            "gpt-5",
            "claude-sonnet-4-5",
            "o3",
            "llama-3-70b",
        ],
    )
    def test_rejects_unrelated_names(self, model_name):
        assert _builder._is_gpt_5_6_family(model_name) is False

    @pytest.mark.parametrize("model_name", ["", None])
    def test_rejects_empty_or_none(self, model_name):
        assert _builder._is_gpt_5_6_family(model_name) is False


# --------------------------------------------------------------------------- #
# _agent_exposes_tool helper                                                    #
# --------------------------------------------------------------------------- #


class TestAgentExposesTool:
    """The detector must reflect the agent's tools list faithfully."""

    def test_returns_true_when_present(self):
        agent = MagicMock()
        agent.get_available_tools.return_value = [
            "list_files",
            "invoke_agent",
            "read_file",
        ]
        assert _builder._agent_exposes_tool(agent, "invoke_agent") is True

    def test_returns_false_when_absent(self):
        agent = MagicMock()
        agent.get_available_tools.return_value = ["list_files", "read_file"]
        assert _builder._agent_exposes_tool(agent, "invoke_agent") is False

    def test_returns_false_when_get_tools_raises(self):
        agent = MagicMock()
        agent.get_available_tools.side_effect = RuntimeError("boom")
        assert _builder._agent_exposes_tool(agent, "invoke_agent") is False

    def test_returns_false_when_get_tools_returns_none(self):
        agent = MagicMock()
        agent.get_available_tools.return_value = None
        assert _builder._agent_exposes_tool(agent, "invoke_agent") is False

    def test_honors_requested_tool_name(self):
        """The same helper must work for any tool we pass in."""
        agent = MagicMock()
        agent.get_available_tools.return_value = [
            "list_files",
            "agent_run_shell_command",
        ]
        assert _builder._agent_exposes_tool(agent, "agent_run_shell_command") is True
        assert _builder._agent_exposes_tool(agent, "invoke_agent") is False


# --------------------------------------------------------------------------- #
# Guardrail text sanity                                                        #
# --------------------------------------------------------------------------- #


class TestGuardrailTextContent:
    """Each guardrail string must actually convey its message."""

    def test_invoke_agent_text_mentions_relevant_tools(self):
        text = _builder._GPT_5_6_INVOKE_AGENT_GUARD_TEXT
        assert "invoke_agent" in text
        assert "planning-agent" in text
        assert "GPT-5.6" in text

    def test_run_shell_command_text_mentions_relevant_tools(self):
        text = _builder._GPT_5_6_RUN_SHELL_COMMAND_GUARD_TEXT
        assert "agent_run_shell_command" in text
        assert "GPT-5.6" in text
        # The user-supplied caution phrase must be embedded verbatim.
        assert "delete, overwrite" in text
        assert "unrecoverable changes" in text


# --------------------------------------------------------------------------- #
# _assemble_instructions guardrail integration                                #
# --------------------------------------------------------------------------- #


def _make_fake_agent(tools):
    """Build a minimal stand-in for ``BaseAgent`` with the right shape."""

    agent = MagicMock()
    agent.get_full_system_prompt.return_value = "BASE_PROMPT"
    agent.get_available_tools.return_value = tools
    agent.get_model_name.return_value = "gpt-5.6-sol"
    return agent


def _patch_collaborators(monkeypatch):
    """Stub every module-level collaborator ``_assemble_instructions`` touches.

    ``load_puppy_rules`` lives in this module; ``has_extended_thinking_active``
    is imported lazily from ``code_puppy.tools`` and
    ``prepare_prompt_for_model`` from ``code_puppy.model_utils``. We patch
    each at its source so the lazy imports resolve to our stubs.
    """

    def _stub_prepare(_name, prompt, _user, **_kwargs):
        return MagicMock(instructions=prompt, user_prompt="", is_claude_code=False)

    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "")
    monkeypatch.setattr(
        "code_puppy.tools.has_extended_thinking_active", lambda _name: False
    )
    monkeypatch.setattr(
        "code_puppy.model_utils.prepare_prompt_for_model", _stub_prepare
    )


class TestAssembleInstructionsInvokeAgentGuardrail:
    """The ``invoke_agent`` guardrail must fire only on gpt-5.6 + tool."""

    def test_fires_when_model_and_tool_both_match(self, monkeypatch):
        agent = _make_fake_agent(
            ["list_files", "invoke_agent", "read_file"],
        )
        _patch_collaborators(monkeypatch)

        result = _builder._assemble_instructions(agent, "gpt-5.6-sol")

        assert result.startswith("BASE_PROMPT")
        assert _builder._GPT_5_6_INVOKE_AGENT_GUARD_TEXT in result
        # The guardrail must explicitly forbid the planning-agent.
        assert "planning-agent" in result

    def test_silent_for_non_gpt_5_6_model(self, monkeypatch):
        agent = _make_fake_agent(
            ["list_files", "invoke_agent", "read_file"],
        )
        _patch_collaborators(monkeypatch)

        result = _builder._assemble_instructions(agent, "gpt-5.5")

        assert _builder._GPT_5_6_INVOKE_AGENT_GUARD_TEXT not in result


class TestAssembleInstructionsRunShellCommandGuardrail:
    """The ``agent_run_shell_command`` guardrail must also gate correctly."""

    def test_fires_when_model_and_tool_both_match(self, monkeypatch):
        agent = _make_fake_agent(
            [
                "list_files",
                "agent_run_shell_command",
                "read_file",
            ],
        )
        _patch_collaborators(monkeypatch)

        result = _builder._assemble_instructions(agent, "codex-gpt-5.6-sol")

        assert _builder._GPT_5_6_RUN_SHELL_COMMAND_GUARD_TEXT in result
        assert "delete, overwrite" in result

    def test_silent_when_agent_lacks_run_shell_command(self, monkeypatch):
        agent = _make_fake_agent(["list_files", "read_file"])
        _patch_collaborators(monkeypatch)

        result = _builder._assemble_instructions(agent, "gpt-5.6-luna")

        assert _builder._GPT_5_6_RUN_SHELL_COMMAND_GUARD_TEXT not in result

    def test_silent_for_non_gpt_5_6_model(self, monkeypatch):
        agent = _make_fake_agent(
            [
                "list_files",
                "agent_run_shell_command",
                "read_file",
            ],
        )
        _patch_collaborators(monkeypatch)

        result = _builder._assemble_instructions(agent, "gpt-5.5")

        assert _builder._GPT_5_6_RUN_SHELL_COMMAND_GUARD_TEXT not in result


class TestAssembleInstructionsGuardrailsIndependent:
    """Each guardrail fires on its own; they don't interfere with each other."""

    def test_both_guardrails_fire_when_both_tools_present(self, monkeypatch):
        # Agent with BOTH invoke_agent and agent_run_shell_command, on a
        # gpt-5.6 model — both guardrails should appear in the result.
        agent = _make_fake_agent(
            [
                "list_files",
                "invoke_agent",
                "agent_run_shell_command",
                "read_file",
            ],
        )
        _patch_collaborators(monkeypatch)

        result = _builder._assemble_instructions(agent, "gpt-5.6-sol")

        assert _builder._GPT_5_6_INVOKE_AGENT_GUARD_TEXT in result
        assert _builder._GPT_5_6_RUN_SHELL_COMMAND_GUARD_TEXT in result

    def test_neither_guardrail_fires_without_gpt_5_6(self, monkeypatch):
        agent = _make_fake_agent(
            [
                "list_files",
                "invoke_agent",
                "agent_run_shell_command",
                "read_file",
            ],
        )
        _patch_collaborators(monkeypatch)

        result = _builder._assemble_instructions(agent, "gpt-5.5")

        assert _builder._GPT_5_6_INVOKE_AGENT_GUARD_TEXT not in result
        assert _builder._GPT_5_6_RUN_SHELL_COMMAND_GUARD_TEXT not in result
