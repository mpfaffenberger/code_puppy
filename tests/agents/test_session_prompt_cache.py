"""Cache reuse follows the complete durable prompt contract, not identity alone."""

from copy import deepcopy

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart

from code_puppy.agents import _builder
from code_puppy.agents._session_state import SESSION_KEY
from tests.agents.test_session_state_identity import SessionAgent


@pytest.mark.parametrize(
    "change", [None, "prompt_body", "project_rules", "prepared_prompt", "legacy"]
)
def test_restore_invalidates_only_when_durable_state_changes(monkeypatch, change):
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "RULES")
    owner = SessionAgent(agent_id="same-id")
    owner.initialize_session(system_prompt="CONTRACT")
    _builder._assemble_instructions(owner, "test")
    state = deepcopy(owner.get_session_state())
    if change == "prepared_prompt":
        state[change]["instructions"] += " changed"
    elif change in ("prompt_body", "project_rules"):
        state[change] += " changed"
    metadata = None if change == "legacy" else {SESSION_KEY: state}
    history = [ModelRequest(parts=[UserPromptPart("restored")], metadata=metadata)]
    cached = owner._code_generation_agent = object()
    owner.set_message_history(history)
    assert owner.id == "same-id"
    assert owner.get_message_history() is history
    if change is None:
        assert owner._code_generation_agent is cached
    else:
        assert owner._code_generation_agent is None


def test_initialization_validates_all_inputs_before_mutating(monkeypatch):
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])
    owner = SessionAgent()
    original_id = owner.id
    owner.get_session_prompt_body()
    cached = owner._code_generation_agent = object()
    with pytest.raises(ValueError, match="Set system_prompt before"):
        owner.initialize_session(agent_id=original_id, system_prompt="replacement")
    assert owner._explicit_agent_id is None
    assert owner.id == original_id
    assert owner._initial_system_prompt is None
    assert owner._code_generation_agent is cached


def test_prompt_initialization_invalidates_cache_but_noop_does_not():
    owner = SessionAgent(agent_id="same-id")
    cached = owner._code_generation_agent = object()
    owner.initialize_session()
    assert owner._code_generation_agent is cached
    owner.initialize_session(system_prompt="contract")
    assert owner._code_generation_agent is None
