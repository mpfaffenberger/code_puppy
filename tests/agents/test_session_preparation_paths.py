"""Real provider-hook and subagent persistence regressions for prepared prompts."""

import pickle
from unittest.mock import MagicMock

import pytest

from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from code_puppy.agents import _builder, _runtime
from code_puppy.agents._compaction import make_history_processor
from code_puppy.model_utils import PreparedPrompt
from tests.agents.test_session_state_identity import SessionAgent


async def test_first_turn_hook_never_persists_temporary_policy(monkeypatch):
    def hook(model, system, prompt, prepend):
        return [
            {
                "handled": True,
                "instructions": system,
                "user_prompt": system + "\n" + prompt if prepend else prompt,
            }
        ]

    monkeypatch.setattr("code_puppy.callbacks.on_prepare_model_prompt", hook)
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "RULES")
    owner = SessionAgent(agent_id="fixed")
    owner.get_model_name = lambda: "test"
    with owner.temporary_system_prompt_addition("TEMPORARY POLICY"):
        prepared = _builder._assemble_instructions(owner, "test")
        prompt = _runtime._should_prepend_system_prompt(owner, "hello")
        agent = Agent(
            FunctionModel(
                lambda messages, info: ModelResponse(parts=[TextPart("done")])
            ),
            instructions=prepared.instructions,
            capabilities=[ProcessHistory(make_history_processor(owner))],
        )
        result = await agent.run(prompt)
    history = pickle.loads(pickle.dumps(result.all_messages()))
    resumed = SessionAgent()
    resumed.set_message_history(history)
    assert "TEMPORARY POLICY" in prepared.instructions
    user_parts = [
        p.content for m in history for p in m.parts if isinstance(p, UserPromptPart)
    ]
    assert all("TEMPORARY POLICY" not in text for text in user_parts)
    assert "RULES" in user_parts[0]
    assert "TEMPORARY POLICY" not in str(resumed.get_session_state())
    assert (
        "TEMPORARY POLICY"
        not in _builder._assemble_instructions(resumed, "test").instructions
    )


@pytest.mark.parametrize("fork_main", [False, True])
async def test_subagent_resume_freezes_preparation_but_model_change_reprepares(
    monkeypatch,
    fork_main,
):
    from code_puppy.tools import subagent_invocation as invocation
    from tests.test_subagent_invocation_usage import _capture_invoke_with_model

    saved = {}
    seen = []
    user_inputs = []
    generation = [0]

    async def model(messages, info):
        seen.append(messages[-1].instructions)
        user_inputs.append(
            [p.content for p in messages[-1].parts if isinstance(p, UserPromptPart)]
        )
        yield "done"

    def prepare(model, system, prompt, prepend_system_to_user=True):
        return PreparedPrompt(
            system + f"\nprovider-{generation[0]}",
            f"user-{generation[0]}:{prompt}",
            False,
            f"standing-{generation[0]}",
        )

    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.load_agent", lambda name: SessionAgent()
    )
    monkeypatch.setattr(
        "code_puppy.model_factory.ModelFactory.load_config",
        lambda: {"test": {}, "other": {}},
    )
    monkeypatch.setattr(
        "code_puppy.model_factory.ModelFactory.get_model",
        lambda *a: FunctionModel(stream_function=model),
    )
    monkeypatch.setattr(
        "code_puppy.model_factory.make_model_settings", lambda *a, **kw: {}
    )
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])
    monkeypatch.setattr("code_puppy.model_utils.prepare_prompt_for_model", prepare)
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "MAIN-ONLY-RULES")
    monkeypatch.setattr(
        "code_puppy.config.get_value",
        lambda key, *a, **kw: "true" if key == "disable_mcp_servers" else None,
    )
    monkeypatch.setattr("code_puppy.config.get_output_level", lambda: "medium")
    monkeypatch.setattr(
        "code_puppy.tools.register_tools_for_agent", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        invocation, "on_wrap_pydantic_agent", lambda cfg, agent, **kw: agent
    )
    monkeypatch.setattr(invocation, "on_agent_run_context", lambda *a: [])
    monkeypatch.setattr(
        invocation,
        "_load_session_history",
        lambda sid: pickle.loads(saved[sid]) if sid in saved else [],
    )
    monkeypatch.setattr(
        invocation,
        "_save_session_history",
        lambda session_id, message_history, **kw: saved.update(
            {session_id: pickle.dumps(message_history)}
        ),
    )
    monkeypatch.setattr(
        invocation, "get_subagent_chain", lambda: (f"parent-{generation[0]}",)
    )
    invoke = _capture_invoke_with_model()
    session = "prepared-resume"
    if fork_main:
        from code_puppy.agents._session_state import stamp_session_state
        from pydantic_ai.messages import ModelRequest

        main = SessionAgent()
        _builder._assemble_instructions(main, "test")
        saved[session] = pickle.dumps(
            stamp_session_state(
                main,
                [
                    ModelRequest(parts=[UserPromptPart("main task")]),
                    ModelResponse(parts=[TextPart("main answer")]),
                ],
            )
        )
    for index, model_name in enumerate(["test", "test", "other"]):
        generation[0] = index
        result = await invoke(
            MagicMock(),
            agent_name="test-agent",
            prompt="hello",
            model_name=model_name,
            session_id=session,
        )
        assert not result.error, result.error
        session = result.session_id
        checkpoint = SessionAgent()
        checkpoint.set_message_history(pickle.loads(saved[session]))
        snapshot = checkpoint.get_session_state()["prepared_prompt"]
        assert snapshot["system_prompt"] == (
            "standing-0" if index < 2 else "standing-2"
        )
    assert user_inputs == [["user-0:hello"], ["user-1:hello"], ["user-2:hello"]]
    durable = [text.split("\n\n## Sub-agent execution context")[0] for text in seen]
    assert durable[0] == durable[1]
    for index, text in enumerate(seen):
        assert f"parent-{index}" in text
    assert "Sub-agent execution context" not in str(snapshot)
    assert "provider-2" in seen[2]
    assert all("MAIN-ONLY-RULES" not in text for text in seen)
    resumed = SessionAgent()
    resumed.set_message_history(pickle.loads(saved[session]))
    assert resumed.get_session_state()["prepared_prompt"]["model_name"] == "other"


def test_first_turn_uses_builder_resolved_model_and_frozen_source(monkeypatch):
    calls = []

    def prepare(model_name, system_prompt, user_prompt, prepend_system_to_user=True):
        calls.append((model_name, system_prompt, prepend_system_to_user))
        return PreparedPrompt(
            system_prompt,
            system_prompt + user_prompt if prepend_system_to_user else user_prompt,
            False,
        )

    monkeypatch.setattr("code_puppy.model_utils.prepare_prompt_for_model", prepare)
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "ORIGINAL RULES")
    owner = SessionAgent()
    owner.get_model_name = lambda: "unavailable-requested-model"
    _builder._assemble_instructions(owner, "resolved-fallback")
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "CHANGED RULES")
    _runtime._should_prepend_system_prompt(owner, "hello")
    assert calls[0][:2] == calls[1][:2]
    assert calls[1][0] == "resolved-fallback"
    assert calls[1][2] is True


@pytest.mark.parametrize("source", [None, "valid source", 123])
def test_preparation_source_metadata_compatibility(source):
    from code_puppy.agents._session_state import SESSION_KEY
    from pydantic_ai.messages import ModelRequest

    prepared = {
        "model_name": "test",
        "instructions": "saved",
        "system_prompt": "",
        "is_claude_code": False,
    }
    if source is not None:
        prepared["source_prompt"] = source
    history = [
        ModelRequest(
            parts=[UserPromptPart("hello")],
            metadata={SESSION_KEY: {"agent_id": "fixed", "prepared_prompt": prepared}},
        )
    ]
    owner = SessionAgent()
    if source == 123:
        with pytest.raises(ValueError, match="prepared_prompt"):
            owner.set_message_history(history)
        assert owner.get_message_history() == []
    else:
        owner.set_message_history(history)
        assert _builder._assemble_instructions(owner, "test").instructions == "saved"
