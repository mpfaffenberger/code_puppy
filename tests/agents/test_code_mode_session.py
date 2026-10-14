"""Code-mode REPL state survives across runs of the same session."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from code_puppy.agents._code_mode import build_speculative_code_mode, main_repl_path
from code_puppy.agents._code_mode_session import REPL_SUFFIX, repl_path_for
from code_puppy.session_storage import build_session_paths


@pytest.fixture
def run(monkeypatch):
    """Run one agent turn that makes a single ``run_code`` call; return its result."""
    monkeypatch.setattr(
        "code_puppy.agents._code_mode.get_speculative_code_mode_enabled", lambda: True
    )

    async def go(path: Path | None, **args: object) -> str:
        async def respond(
            messages: list[ModelMessage], info: AgentInfo
        ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
            for part in messages[-1].parts:
                if part.part_kind in ("tool-return", "retry-prompt"):
                    yield str(part.content)
                    return
            yield {0: DeltaToolCall(name="run_code", json_args=json.dumps(args))}

        # A new Agent per turn: nothing in memory can carry the state over.
        agent = Agent(
            FunctionModel(stream_function=respond),
            capabilities=build_speculative_code_mode([], repl_path=lambda: path),
        )
        return (await agent.run("go")).output

    return go


@pytest.mark.asyncio
async def test_state_carries_to_the_next_run_of_the_session(run, tmp_path):
    path = repl_path_for(tmp_path, "s1")
    await run(path, code="X = 41\ndef bump(a):\n    return a + 1")
    assert path.is_file()
    assert "42" in await run(path, code="bump(X)")


@pytest.mark.asyncio
async def test_sessions_do_not_share_state(run, tmp_path):
    await run(repl_path_for(tmp_path, "a"), code="X = 1")
    assert "NameError" in await run(repl_path_for(tmp_path, "b"), code="X")


@pytest.mark.asyncio
async def test_no_path_keeps_state_run_scoped(run, tmp_path):
    await run(None, code="X = 1")
    assert "NameError" in await run(None, code="X")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_run_without_code_keeps_the_saved_state(run, tmp_path):
    path = repl_path_for(tmp_path, "s1")
    await run(path, code="X = 5")
    await run(path, code="pass")
    assert "5" in await run(path, code="X")


@pytest.mark.asyncio
async def test_restart_clears_the_saved_state(run, tmp_path):
    path = repl_path_for(tmp_path, "s1")
    await run(path, code="X = 1")
    await run(path, code="Y = 2", restart=True)
    assert "NameError" in await run(path, code="X")
    assert "2" in await run(path, code="Y")


@pytest.mark.asyncio
async def test_unreadable_dump_starts_fresh_and_is_replaced(run, tmp_path):
    path = repl_path_for(tmp_path, "s1")
    path.write_bytes(b"not a monty dump")
    assert "7" in await run(path, code="3 + 4")
    assert path.read_bytes() != b"not a monty dump"


def test_main_session_dump_lives_beside_the_autosave(monkeypatch, tmp_path):
    monkeypatch.setattr("code_puppy.config.AUTOSAVE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "code_puppy.config.get_current_session_name", lambda: "auto_session_x"
    )
    assert main_repl_path() == build_session_paths(tmp_path, "auto_session_x").repl_path
    assert main_repl_path().name == f"auto_session_x{REPL_SUFFIX}"
