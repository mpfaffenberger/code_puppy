"""Identity round trips through the same message list consumed by headless runners."""

import pickle

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from code_puppy.agents._compaction import make_history_processor
from code_puppy.agents._session_state import SESSION_KEY
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.session_storage import load_session, save_session


class SessionAgent(BaseAgent):
    name = "test-agent"
    display_name = "Test Agent"
    description = "Synthetic session agent"

    def get_system_prompt(self):
        return "SYSTEM"

    def get_available_tools(self):
        return []

    def _get_model_context_length(self):
        return 1_000_000

    def _estimate_context_overhead(self):
        return 0


async def run_turn(owner, prompt="hello"):
    agent = Agent(
        FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("done")])),
        instructions=owner.get_full_system_prompt(),
        capabilities=[ProcessHistory(make_history_processor(owner))],
    )
    result = await agent.run(prompt, message_history=owner.get_message_history())
    owner.set_message_history(result.all_messages())
    return result.all_messages()


@pytest.mark.parametrize("encoding", ["pickle", "named"])
async def test_runner_initialized_identity_survives_turns(tmp_path, encoding):
    owner = SessionAgent()
    owner.initialize_session(agent_id="runner-owned-identity")
    initial_prompt = owner.get_identity_prompt()
    for _ in range(3):
        history = await run_turn(owner)
        if encoding == "pickle":
            history = pickle.loads(pickle.dumps(history))
        else:
            save_session(
                session_name="session",
                history=history,
                base_dir=tmp_path,
                timestamp="2026-01-01T00:00:00",
                token_estimator=lambda m: 1,
            )
            history = load_session("session", tmp_path)
        owner = SessionAgent()
        owner.set_message_history(history)
        assert owner.id == "runner-owned-identity"
        assert owner.get_identity_prompt() == initial_prompt


async def test_explicit_matching_id_allowed_but_conflict_is_atomic():
    owner = SessionAgent(agent_id="original")
    history = await run_turn(owner)
    resumed = SessionAgent(agent_id="other")
    with pytest.raises(ValueError, match="conflicts"):
        resumed.set_message_history(history)
    assert resumed.id == "other" and resumed.get_message_history() == []
    resumed = SessionAgent(agent_id="original")
    resumed.set_message_history(history)
    with pytest.raises(ValueError, match="Cannot change"):
        resumed.initialize_session(agent_id="other")


@pytest.mark.parametrize("bad", ["", "new\nrule", "`inject`", "x" * 129, 123])
def test_invalid_identity_rejected(bad):
    with pytest.raises(ValueError):
        SessionAgent(agent_id=bad)


async def test_real_quick_resume_restores_identity(tmp_path, monkeypatch):
    from code_puppy.command_line import session_commands
    from code_puppy.agents import agent_manager

    owner = SessionAgent(agent_id="from-runner")
    history = await run_turn(owner)
    save_session(
        session_name="saved",
        history=history,
        base_dir=tmp_path,
        timestamp="2026-01-01T00:00:00",
        token_estimator=lambda m: 1,
    )
    resumed = SessionAgent()
    monkeypatch.setattr(
        "code_puppy.config.resolve_quick_resume_pickle",
        lambda *a: tmp_path / "saved.json",
    )
    monkeypatch.setattr(agent_manager, "get_current_agent", lambda: resumed)
    session_commands.handle_quick_resume_command("/quick-resume saved")
    assert resumed.id == owner.id


async def test_existing_metadata_and_legacy_history():
    owner = SessionAgent(agent_id="explicit")
    owner.set_message_history(
        [ModelRequest(parts=[UserPromptPart("old")], metadata={"external": 1})]
    )
    history = await run_turn(owner)
    assert history[0].metadata == {"external": 1}
    requests = [m for m in history if isinstance(m, ModelRequest)]
    assert requests[-1].metadata[SESSION_KEY]["agent_id"] == "explicit"
    resumed = SessionAgent()
    resumed.set_message_history(history)
    assert resumed.id == "explicit"
