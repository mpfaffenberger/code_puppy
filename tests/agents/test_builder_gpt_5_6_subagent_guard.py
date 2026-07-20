from unittest.mock import MagicMock

import pytest

from code_puppy.agents import _builder


@pytest.mark.parametrize(
    "model_name",
    [
        "gpt-5.6",
        "gpt-5.6-sol",
        "codex-gpt-5.6-luna",
        "Codex-GPT-5.6-SOL",
    ],
)
def test_gpt_5_6_family_matches(model_name):
    assert _builder._is_gpt_5_6_family(model_name)


@pytest.mark.parametrize(
    "model_name",
    [None, "", "gpt-5.5", "claude-sonnet-4-5"],
)
def test_gpt_5_6_family_rejects_other_names(model_name):
    assert not _builder._is_gpt_5_6_family(model_name)


def _agent(tools):
    agent = MagicMock()
    agent.get_full_system_prompt.return_value = "BASE"
    agent.get_available_tools.return_value = tools
    agent.get_model_name.return_value = "gpt-5.6-sol"
    return agent


def _stub_prompt_build(monkeypatch):
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "")
    monkeypatch.setattr(
        "code_puppy.tools.has_extended_thinking_active", lambda _name: False
    )
    monkeypatch.setattr(
        "code_puppy.model_utils.prepare_prompt_for_model",
        lambda _name, prompt, _user, **_kwargs: MagicMock(instructions=prompt),
    )


@pytest.mark.parametrize(
    ("tools", "present", "absent"),
    [
        (["invoke_agent"], "Sub-Agent Delegation", "Shell Safety"),
        (["agent_run_shell_command"], "Shell Safety", "Sub-Agent Delegation"),
    ],
)
def test_prompt_guard_is_gated_by_tool(monkeypatch, tools, present, absent):
    _stub_prompt_build(monkeypatch)
    result = _builder._assemble_instructions(_agent(tools), "gpt-5.6-sol")
    assert present in result
    assert absent not in result


def test_prompt_guards_are_gated_by_model(monkeypatch):
    _stub_prompt_build(monkeypatch)
    tools = ["invoke_agent", "agent_run_shell_command"]
    result = _builder._assemble_instructions(_agent(tools), "gpt-5.5")
    assert "Sub-Agent Delegation" not in result
    assert "Shell Safety" not in result


def test_tool_detection_fails_closed():
    agent = MagicMock()
    agent.get_available_tools.side_effect = RuntimeError
    assert not _builder._agent_exposes_tool(agent, "invoke_agent")
