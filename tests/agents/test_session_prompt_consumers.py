"""Frozen prompts must agree with explicit project transitions and accounting."""

from pathlib import Path
from unittest.mock import Mock

from code_puppy import token_usage
from code_puppy.agents import _builder
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.command_line import core_commands
from code_puppy.model_utils import PreparedPrompt
from tests.agents.test_session_prompt_prefix import assembled_turn
from tests.agents.test_session_state_identity import SessionAgent


async def test_cd_refreshes_project_contract_without_losing_history(
    monkeypatch, tmp_path
):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.chdir(first)
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])
    monkeypatch.setattr(
        _builder, "load_puppy_rules", lambda: f"RULES:{Path.cwd().name}"
    )
    owner = SessionAgent(agent_id="same-owner")
    await assembled_turn(owner)
    history = owner.get_message_history()
    assert "RULES:first" in _builder._assemble_instructions(owner, "test").instructions
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent", lambda: owner
    )
    monkeypatch.setattr(
        "code_puppy.command_line.file_index.reindex", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        owner,
        "reload_code_generation_agent",
        lambda: _builder._assemble_instructions(owner, "test"),
    )
    assert core_commands.handle_cd_command(f'/cd "{second}"')
    assert Path.cwd() == second
    assert owner.get_message_history() is history
    assert owner.id == "same-owner"
    prepared = _builder._assemble_instructions(owner, "test")
    assert "RULES:second" in prepared.instructions
    assert "RULES:first" not in prepared.instructions
    await assembled_turn(owner)
    resumed = SessionAgent()
    resumed.set_message_history(owner.get_message_history())
    assert (
        "RULES:second" in _builder._assemble_instructions(resumed, "test").instructions
    )


async def test_overhead_and_ui_read_saved_system_without_hooks(monkeypatch):
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "ORIGINAL RULES")
    monkeypatch.setattr(
        "code_puppy.model_utils.prepare_prompt_for_model",
        lambda model, system, prompt, **kw: PreparedPrompt(
            system + "X" * 100_000, prompt, False, "STANDING"
        ),
    )
    owner = SessionAgent()
    await assembled_turn(owner)
    resumed = SessionAgent()
    resumed.set_message_history(owner.get_message_history())
    hook = Mock(side_effect=AssertionError("must not reprepare for accounting"))
    monkeypatch.setattr("code_puppy.model_utils.prepare_prompt_for_model", hook)
    monkeypatch.setattr(
        _builder, "load_puppy_rules", Mock(side_effect=AssertionError("no live rules"))
    )
    monkeypatch.setattr(
        token_usage,
        "_kennel_memory_block",
        Mock(side_effect=AssertionError("no live recall")),
    )
    monkeypatch.setattr(resumed, "_get_tool_probe", lambda: None)
    monkeypatch.setattr(token_usage, "_agent_tools", lambda agent: None)
    monkeypatch.setattr(token_usage, "_live_mcp_servers_for", lambda agent: None)
    estimate = Mock(return_value=123)
    monkeypatch.setattr(
        "code_puppy.agents.base_agent.estimate_context_overhead", estimate
    )
    with resumed.temporary_system_prompt_addition("TEMPORARY"):
        expected = _builder._assemble_instructions(resumed, "test").system_text
        assert BaseAgent._estimate_context_overhead(resumed) == 123
        assert estimate.call_args.args[0] == expected
        assert token_usage._resolved_system_prompt(resumed) == expected
        breakdown = token_usage.compute_overhead_breakdown(resumed)
        assert breakdown.total == token_usage._raw_estimate_tokens(expected)
        assert breakdown.agents_md_tokens == breakdown.kennel_memory_tokens == 0
    hook.assert_not_called()
