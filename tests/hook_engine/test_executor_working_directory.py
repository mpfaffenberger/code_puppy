"""Hook execution must use the active chat working directory, not the process cwd."""

import contextlib
import json
import shlex
import sys
from pathlib import Path
from typing import Iterator, Optional

import pytest

from code_puppy.hook_engine.executor import _build_stdin_payload, execute_hook
from code_puppy.hook_engine.models import EventData, HookConfig
from code_puppy.tools.common import reset_working_directory, set_working_directory

PY = shlex.quote(sys.executable)


@pytest.fixture
def folders(tmp_path, monkeypatch) -> tuple[Path, Path]:
    """Return (process_dir, chat_dir); the process cwd is process_dir."""
    process_dir = (tmp_path / "process").resolve()
    chat_dir = (tmp_path / "chat").resolve()
    process_dir.mkdir()
    chat_dir.mkdir()
    monkeypatch.chdir(process_dir)
    return process_dir, chat_dir


@contextlib.contextmanager
def _chat_override(path: Optional[Path]) -> Iterator[None]:
    if path is None:
        yield
        return
    token = set_working_directory(str(path))
    try:
        yield
    finally:
        reset_working_directory(token)


def _hook(command: str) -> HookConfig:
    return HookConfig(matcher="*", type="command", command=command, timeout=10_000)


def _event() -> EventData:
    return EventData(event_type="PreToolUse", tool_name="Edit", tool_args={})


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [True, False], ids=["chat", "terminal"])
async def test_hook_subprocess_cwd_follows_chat_folder(folders, override):
    process_dir, chat_dir = folders
    expected = chat_dir if override else process_dir
    hook = _hook(f'{PY} -c "import os;print(os.getcwd())"')

    with _chat_override(chat_dir if override else None):
        result = await execute_hook(hook, _event())

    assert result.stdout.strip() == str(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [True, False], ids=["chat", "terminal"])
async def test_project_dir_env_and_placeholder_follow_chat_folder(folders, override):
    process_dir, chat_dir = folders
    expected = chat_dir if override else process_dir
    hook = _hook(
        'echo "${CLAUDE_PROJECT_DIR}"; '
        f"{PY} -c \"import os;print(os.environ['CLAUDE_PROJECT_DIR'])\""
    )

    with _chat_override(chat_dir if override else None):
        result = await execute_hook(hook, _event())

    assert result.stdout.splitlines() == [str(expected), str(expected)]


@pytest.mark.parametrize("override", [True, False], ids=["chat", "terminal"])
def test_stdin_payload_cwd_follows_chat_folder(folders, override):
    process_dir, chat_dir = folders
    expected = chat_dir if override else process_dir

    with _chat_override(chat_dir if override else None):
        payload = json.loads(_build_stdin_payload(_event()))

    assert payload["cwd"] == str(expected)
