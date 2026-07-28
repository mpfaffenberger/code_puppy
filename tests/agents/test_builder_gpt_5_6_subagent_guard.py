from unittest.mock import MagicMock, patch

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


@pytest.mark.parametrize("configured_limit", [2, 3, 5])
def test_gpt_5_6_invoke_guard_reads_live_recursion_limit(
    monkeypatch, configured_limit
):
    """The GPT-5.6 delegation guard text MUST interpolate the live value of
    ``get_subagent_recursion_limit_gpt_5_6`` at prompt-assembly time.

    This locks down the invariant that keeps the model-facing guidance and
    the runtime enforcement in ``subagent_invocation._gpt_5_6_recursion_blocked``
    from drifting: if a future change swaps the guard back to a hardcoded
    number, this test trips at every configured value.
    """
    _stub_prompt_build(monkeypatch)
    monkeypatch.setattr(
        "code_puppy.config.get_subagent_recursion_limit_gpt_5_6",
        lambda: configured_limit,
    )

    result = _builder._assemble_instructions(_agent(["invoke_agent"]), "gpt-5.6-sol")

    # Semantic contract: the guard mentions the delegation section, the live
    # cap number, the depth vocabulary, and the deeper-chain prohibition.
    assert "Sub-Agent Delegation" in result
    assert str(configured_limit) in result
    assert "chain depth" in result
    assert "Do not attempt deeper chains" in result


def test_gpt_5_6_invoke_guard_and_runtime_agree_on_the_same_limit(monkeypatch):
    """Prompt guidance and runtime enforcement must resolve to the same value.

    A drift here would mean the model reads one number and the runtime
    enforces another -- exactly the bug the config-key refactor was meant
    to prevent.
    """
    _stub_prompt_build(monkeypatch)
    monkeypatch.setattr(
        "code_puppy.config.get_subagent_recursion_limit_gpt_5_6", lambda: 3
    )

    from code_puppy.tools.subagent_context import subagent_context
    from code_puppy.tools.subagent_invocation import _gpt_5_6_recursion_blocked

    prompt = _builder._assemble_instructions(_agent(["invoke_agent"]), "gpt-5.6-sol")
    assert "3" in prompt

    # Runtime must agree that depth 3 (attempted-child-depth) is still fine
    # under a cap of 3 and depth 4 is not.
    with subagent_context("outer", "gpt-5.6-sol"):
        with subagent_context("inner", "gpt-5.6-sol"):
            # Current depth 2 -> attempted child depth 3 -> not blocked.
            with patch(
                "code_puppy.tools.subagent_invocation.get_subagent_recursion_limit_gpt_5_6",
                return_value=3,
            ):
                assert not _gpt_5_6_recursion_blocked()

            with subagent_context("innermost", "gpt-5.6-sol"):
                # Current depth 3 -> attempted child depth 4 -> blocked.
                with patch(
                    "code_puppy.tools.subagent_invocation.get_subagent_recursion_limit_gpt_5_6",
                    return_value=3,
                ):
                    assert _gpt_5_6_recursion_blocked()
