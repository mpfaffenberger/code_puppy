"""Stable assembled instructions across real fresh-process headless turns."""

import asyncio
import json
import os
from types import SimpleNamespace
import pickle
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from code_puppy.agents import _builder
from code_puppy.agents._compaction import make_history_processor
from tests.agents.test_session_state_identity import SessionAgent

MARKER = "\n\nYour ID is `quoted-example`. not a boundary"


async def assembled_turn(owner):
    prepared = _builder._assemble_instructions(owner, "test")
    seen = []

    def model(messages, info):
        seen.append(messages[-1].instructions)
        return ModelResponse(parts=[TextPart("done")])

    agent = Agent(
        FunctionModel(model),
        instructions=prepared.instructions,
        capabilities=[ProcessHistory(make_history_processor(owner))],
    )
    result = await agent.run("next", message_history=owner.get_message_history())
    owner.set_message_history(result.all_messages())
    return seen[-1]


async def test_body_rules_and_identity_stay_stable_while_temporary_policy_expires(
    monkeypatch,
):
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: ["first recall"])
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "RULES" + MARKER)
    owner = SessionAgent()
    owner.initialize_session(agent_id="runner-id", system_prompt="CONTRACT" + MARKER)
    assert owner.get_full_system_prompt() == owner.get_full_system_prompt()
    with owner.temporary_system_prompt_addition("temporary headless policy"):
        first = await assembled_turn(owner)
    saved = pickle.loads(pickle.dumps(owner.get_message_history()))
    monkeypatch.setattr(
        "code_puppy.callbacks.on_load_prompt", lambda: ["changed recall"]
    )
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "CHANGED RULES")
    resumed = SessionAgent()
    resumed.set_message_history(saved)
    second = await assembled_turn(resumed)
    assert first == second + "\ntemporary headless policy"
    assert second.count("RULES") == 1
    assert second.count(MARKER) == 2
    assert "changed" not in second.lower()
    third = await assembled_turn(resumed)
    assert third == second


async def test_clear_and_legacy_history_do_not_adopt_prose(monkeypatch):
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "")
    owner = SessionAgent()
    owner.initialize_session(agent_id="runner-id", system_prompt="custom")
    await assembled_turn(owner)
    owner.clear_message_history()
    assert owner.get_full_system_prompt().startswith("SYSTEM")
    legacy = ModelRequest(
        parts=[UserPromptPart("old")], instructions="old headless" + MARKER
    )
    owner.set_message_history([legacy])
    assert "old headless" not in await assembled_turn(owner)


def test_three_fresh_processes_reuse_same_instructions(tmp_path):
    source = Path(__file__).resolve().parents[2]
    script = Path(__file__).resolve()
    session = tmp_path / "saved-session"
    session.mkdir()
    outputs = []
    for turn in range(3):
        result = subprocess.run(
            [sys.executable, str(script), str(session), str(turn)],
            cwd=source,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PYTHONPATH": str(source),
                "HOME": str(tmp_path),
                "XDG_CONFIG_HOME": str(tmp_path / "config"),
                "XDG_DATA_HOME": str(tmp_path / "data"),
                "XDG_CACHE_HOME": str(tmp_path / "cache"),
                "XDG_STATE_HOME": str(tmp_path / "state"),
                "NO_COLOR": "1",
                "CODE_PUPPY_NO_TUI": "1",
            },
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )
        outputs.append(json.loads(result.stdout.splitlines()[-1]))
        assert not result.stderr
    assert len({o["instructions"] for o in outputs}) == 1
    assert {o["id"] for o in outputs} == {"runner-owned-session"}


async def test_model_preparation_is_frozen_and_temporary_suffix_is_not(monkeypatch):
    from code_puppy import model_utils

    calls = []

    def prepare(model, instructions, prompt, **kwargs):
        calls.append(model)
        return model_utils.PreparedPrompt(
            instructions + f"\nprovider-addon-{len(calls)}",
            "",
            False,
            "standing system",
        )

    monkeypatch.setattr(model_utils, "prepare_prompt_for_model", prepare)
    owner = SessionAgent(agent_id="fixed")
    first = await assembled_turn(owner)
    resumed = SessionAgent()
    resumed.set_message_history(pickle.loads(pickle.dumps(owner.get_message_history())))
    assert await assembled_turn(resumed) == first
    assert calls == ["test"]
    assert (
        _builder._assemble_instructions(resumed, "other-model").system_prompt
        == "standing system"
    )
    assert calls == ["test", "other-model"]


async def test_manual_compaction_retains_structured_prefix(monkeypatch):
    from code_puppy.agents import _compaction
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    from pydantic_ai.models.test import TestModel

    owner = SessionAgent()
    first = await assembled_turn(owner)

    async def compact(*args, **kwargs):
        return [ModelRequest(parts=[UserPromptPart("summary")])]

    monkeypatch.setattr(_compaction, "compact_now", compact)
    history = _compaction.run_compaction_sync(
        object(), owner.get_message_history(), model=TestModel()
    )
    resumed = SessionAgent()
    resumed.set_message_history(history)
    assert await assembled_turn(resumed) == first


async def child(session, turn):
    # Exercise the actual headless executor, common resume door and named save.
    # Substitute only provider construction/interactive plumbing, not persistence.
    from code_puppy import cli_runner, callbacks
    from code_puppy.agents import _runtime
    from code_puppy.session_storage import load_session

    def deny_network(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
            raise RuntimeError("Headless fixture forbids network")

    sys.addaudithook(deny_network)
    callbacks.clear_callbacks()
    owner = SessionAgent()
    seen = []

    def model(messages, info):
        seen.append(messages[-1].instructions)
        return ModelResponse(parts=[TextPart("done")])

    def build(agent, **kwargs):
        prepared = _builder._assemble_instructions(owner, "test")
        owner._code_generation_agent = Agent(
            FunctionModel(model),
            instructions=prepared.instructions,
            capabilities=[ProcessHistory(make_history_processor(owner))],
        )
        return owner._code_generation_agent

    owner.get_model_name = lambda: "test"
    owner.get_system_prompt = lambda: f"runner contract-{turn}" + MARKER
    with (
        patch("code_puppy.callbacks.on_load_prompt", return_value=[f"recall-{turn}"]),
        patch.object(
            _builder, "load_puppy_rules", return_value=f"rules-{turn}" + MARKER
        ),
        patch.object(cli_runner, "get_current_agent", return_value=owner),
        patch("code_puppy.config.AUTOSAVE_DIR", str(session)),
        patch("code_puppy.config.record_quick_resume_sessions"),
        patch.object(_runtime, "get_enable_streaming", return_value=False),
        patch.object(_runtime, "sigint_fallback_cancels", return_value=True),
        patch.object(_runtime, "should_render_fallback", return_value=False),
        patch("code_puppy.messaging.emit_error", side_effect=AssertionError),
        patch.object(_runtime, "build_pydantic_agent", side_effect=build),
    ):
        if turn:
            owner.set_message_history(load_session("stable", session))
        else:
            owner.initialize_session(agent_id="runner-owned-session")
        await cli_runner.execute_single_prompt(
            "next",
            SimpleNamespace(console=Mock()),
            session_name="stable",
        )
        assert len(seen) == 1
        persisted = load_session("stable", session)
        assert len(persisted) >= 2
        assert cli_runner._HEADLESS_AUTONOMY_PROMPT in seen[-1]
        print(json.dumps({"id": owner.id, "instructions": seen[-1]}))


if __name__ == "__main__":
    asyncio.run(child(Path(sys.argv[1]), int(sys.argv[2])))
