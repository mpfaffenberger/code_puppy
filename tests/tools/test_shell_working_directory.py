"""Shell commands run in the active working-directory override (ACP session folder)."""

import asyncio
import os
import sys
import time
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from code_puppy.tools import command_runner, io_backends
from code_puppy.tools.common import reset_working_directory, set_working_directory

PRINT_CWD = f'"{sys.executable}" -c "import os;print(os.getcwd())"'


@pytest.fixture(autouse=True)
def _yolo_mode_skips_approval(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_yolo_mode", lambda: True)


@pytest.fixture(autouse=True)
def callback_cwds(monkeypatch):
    """Record the ``cwd`` each ``on_run_shell_command`` callback receives."""
    seen: list = []

    async def _record(context, command, cwd, timeout):
        seen.append(cwd)
        return []

    monkeypatch.setattr("code_puppy.callbacks.on_run_shell_command", _record)
    return seen


@pytest.fixture
def executor():
    fake = _RecordingExecutor()
    io_backends.set_command_executor(fake)
    yield fake
    io_backends.set_command_executor(None)


class _RecordingExecutor:
    def __init__(self):
        self.calls: list = []

    async def run(self, command, cwd, timeout):
        self.calls.append(cwd)
        return io_backends.ExecResult(exit_code=0, output="")


@contextmanager
def working_dir(path):
    token = set_working_directory(str(path))
    try:
        yield
    finally:
        reset_working_directory(token)


async def _run(command, cwd=None, background=False):
    return await command_runner.run_shell_command(
        MagicMock(), command, cwd, 30, background
    )


def _same_dir(printed, expected):
    return os.path.realpath(printed.strip()) == os.path.realpath(str(expected))


async def _read_log_when_written(path, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        if content.endswith("\n"):
            return content
        await asyncio.sleep(0.1)
    raise AssertionError(f"background output never written to {path}")


@pytest.mark.parametrize("cwd_arg", [None, "", "  ", "null", "None"])
async def test_missing_cwd_runs_in_override(tmp_path, callback_cwds, cwd_arg):
    folder = tmp_path / "A"
    folder.mkdir()
    with working_dir(folder):
        result = await _run(PRINT_CWD, cwd_arg)
    assert result.success
    assert _same_dir(result.stdout, folder)
    assert callback_cwds == [str(folder)]


@pytest.mark.parametrize("cwd_arg", ["sub", "absolute"])
async def test_explicit_cwd_resolves_against_override(tmp_path, callback_cwds, cwd_arg):
    base = tmp_path / "A"
    sub = base / "sub"
    sub.mkdir(parents=True)
    arg = "sub" if cwd_arg == "sub" else str(sub)
    with working_dir(base):
        result = await _run(PRINT_CWD, arg)
    assert result.success
    assert _same_dir(result.stdout, sub)
    assert callback_cwds == [str(sub)]


async def test_background_command_runs_in_override(tmp_path):
    folder = tmp_path / "A"
    folder.mkdir()
    with working_dir(folder):
        result = await _run(PRINT_CWD, None, background=True)
    try:
        assert result.success and result.background
        output = await _read_log_when_written(result.log_file)
        assert _same_dir(output, folder)
    finally:
        os.unlink(result.log_file)


async def test_executor_backend_receives_override_folder(tmp_path, executor):
    folder = tmp_path / "A"
    folder.mkdir()
    with working_dir(folder):
        result = await _run("echo hi")
    assert result.success
    assert executor.calls == [str(folder)]


async def test_executor_backend_receives_none_in_terminal_mode(executor):
    result = await _run("echo hi")
    assert result.success
    assert executor.calls == [None]


@pytest.mark.parametrize("override", ["none", "process_folder"])
@pytest.mark.parametrize(
    "cwd_arg, expected_seen, expected_subdir",
    [(None, None, ""), ("sub", "sub", "sub")],
)
async def test_terminal_mode_keeps_cwd_arg_unchanged(
    tmp_path,
    monkeypatch,
    callback_cwds,
    override,
    cwd_arg,
    expected_seen,
    expected_subdir,
):
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path)
    token = set_working_directory(os.getcwd()) if override == "process_folder" else None
    try:
        result = await _run(PRINT_CWD, cwd_arg)
    finally:
        if token is not None:
            reset_working_directory(token)
    assert result.success
    assert _same_dir(result.stdout, tmp_path / expected_subdir)
    assert callback_cwds == [expected_seen]


async def test_concurrent_tasks_keep_their_own_folder(tmp_path):
    folder_a = tmp_path / "A"
    folder_b = tmp_path / "B"
    folder_a.mkdir()
    folder_b.mkdir()

    async def _run_in(folder):
        with working_dir(folder):
            return await _run(PRINT_CWD)

    result_a, result_b = await asyncio.gather(_run_in(folder_a), _run_in(folder_b))
    assert _same_dir(result_a.stdout, folder_a)
    assert _same_dir(result_b.stdout, folder_b)
