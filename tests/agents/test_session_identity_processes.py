"""Resume real message history in fresh processes without caller identity repair."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CHILD = r"""
import asyncio
import json
import pickle
import sys
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from code_puppy.agents._compaction import make_history_processor
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.callbacks import clear_callbacks
from code_puppy.session_storage import load_session, save_session


def deny_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
        raise RuntimeError("Session fixture forbids network")


sys.addaudithook(deny_network)
clear_callbacks()


class Owner(BaseAgent):
    name = "session-test"
    display_name = "Session test"
    description = "Local model fixture"

    def get_system_prompt(self):
        return "Test instructions"

    def get_available_tools(self):
        return []

    def _get_model_context_length(self):
        return 1_000_000

    def _estimate_context_overhead(self):
        return 0


async def main():
    directory, encoding, turn = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
    owner = Owner()
    path = directory / "history.pkl"
    if turn:
        history = (
            pickle.loads(path.read_bytes())
            if encoding == "pickle"
            else load_session("saved", directory)
        )
        owner.set_message_history(history)
    agent = Agent(
        FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("done")])),
        capabilities=[ProcessHistory(make_history_processor(owner))],
    )
    result = await agent.run("next", message_history=owner.get_message_history())
    owner.set_message_history(result.all_messages())
    if encoding == "pickle":
        path.write_bytes(pickle.dumps(owner.get_message_history()))
    else:
        save_session(
            session_name="saved", history=owner.get_message_history(),
            base_dir=directory, timestamp="2026-01-01T00:00:00",
            token_estimator=lambda message: 1,
        )
    print(json.dumps({"id": owner.id, "messages": len(owner.get_message_history())}))


asyncio.run(main())
"""


@pytest.mark.parametrize("encoding", ["pickle", "named"])
def test_fresh_process_resume_keeps_identity_without_caller_repair(tmp_path, encoding):
    source = Path(__file__).resolve().parents[2]
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(source),
        "HOME": str(tmp_path),
        "NO_COLOR": "1",
        "CODE_PUPPY_NO_TUI": "1",
        **{
            key: str(tmp_path / key)
            for key in (
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
                "XDG_CACHE_HOME",
                "XDG_STATE_HOME",
            )
        },
    }
    outputs = []
    for turn in range(3):
        result = subprocess.run(
            [sys.executable, "-c", CHILD, str(tmp_path), encoding, str(turn)],
            cwd=source,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )
        assert not result.stderr
        outputs.append(json.loads(result.stdout.splitlines()[-1]))
    assert [item["messages"] for item in outputs] == [2, 4, 6]
    assert len({item["id"] for item in outputs}) == 1
