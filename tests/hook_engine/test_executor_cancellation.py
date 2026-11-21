"""Cancelled command hooks cannot outlive their awaited owner."""

import asyncio
import os
import shlex
import signal
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from code_puppy.agents import _runtime
from code_puppy.callbacks import register_callback
from code_puppy.hook_engine import _process, executor
from code_puppy.hook_engine.models import EventData, HookConfig
from tests.agents.test_runtime_cancellation import (  # noqa: F401
    DummyAgent,
    isolated_runtime,
)
from tests.agents.test_runtime_consumed_cancellation import (  # noqa: F401
    RecordingAgent,
    repl_guard,
)


def python_command(script):
    args = [sys.executable, "-c", script]
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


def event():
    return EventData(event_type="UserPromptSubmit", tool_name="prompt", tool_args={})


async def wait_for_file(path):
    async def poll():
        while not path.exists():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), 5)


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX SIGINT integration; Windows mocked below"
)
@pytest.mark.parametrize("phase", ["user_prompt_submit", "agent_run_end"])
@pytest.mark.usefixtures("repl_guard")
async def test_cancelled_runtime_reaps_command_before_return(
    monkeypatch, tmp_path, phase
):
    ready = tmp_path / "ready"
    marker = tmp_path / "after-return"
    script = (
        "import pathlib,time; "
        f"pathlib.Path({str(ready)!r}).touch(); "
        f"time.sleep(0.4); pathlib.Path({str(marker)!r}).touch()"
    )
    hook = HookConfig(matcher="*", type="command", command=python_command(script))
    processes = []
    create = asyncio.create_subprocess_shell

    async def capture(*args, **kwargs):
        proc = await create(*args, **kwargs)
        processes.append(proc)
        return proc

    monkeypatch.setattr(executor.asyncio, "create_subprocess_shell", capture)

    async def command_hook(*args, **kwargs):
        return await executor.execute_hook(hook, event())

    implementation = RecordingAgent()
    register_callback(phase, command_hook)
    task = asyncio.create_task(
        _runtime.run_with_mcp(DummyAgent(implementation), "hello")
    )
    try:
        await wait_for_file(ready)
        os.kill(os.getpid(), signal.SIGINT)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        running_at_return = processes[0].returncode is None
        await asyncio.wait_for(processes[0].wait(), 5)
        assert not marker.exists()
        assert not running_at_return
        assert implementation.calls == (
            [] if phase == "user_prompt_submit" else ["hello"]
        )
        assert _runtime._active_run_depth == 0
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for proc in processes:
            if proc.returncode is None:
                proc.kill()
            await asyncio.wait_for(proc.wait(), 5)


@pytest.mark.parametrize("shell_exits", [False, True], ids=["tree", "exited-shell"])
async def test_cancel_kills_descendant_even_when_shell_has_exited(
    tmp_path, monkeypatch, shell_exits
):
    ready = tmp_path / "descendant-ready"
    marker = tmp_path / "descendant-marker"
    child_script = (
        "import pathlib,time; "
        f"pathlib.Path({str(ready)!r}).touch(); "
        f"time.sleep(0.5); pathlib.Path({str(marker)!r}).touch()"
    )
    parent_script = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
        + ("sys.exit(0)" if shell_exits else "time.sleep(0.5)")
    )
    hook = HookConfig(
        matcher="*", type="command", command=python_command(parent_script)
    )
    processes = []
    create = asyncio.create_subprocess_shell

    async def capture(*args, **kwargs):
        proc = await create(*args, **kwargs)
        processes.append(proc)
        return proc

    monkeypatch.setattr(executor.asyncio, "create_subprocess_shell", capture)
    task = asyncio.create_task(executor.execute_hook(hook, event()))
    try:
        await wait_for_file(ready)
        if shell_exits:

            async def exited():
                while processes[0].returncode is None:
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(exited(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        await asyncio.sleep(0.6)
        assert not marker.exists()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        # A broken implementation's deliberately short-lived children finish here.
        await asyncio.sleep(0.6)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group branch")
@pytest.mark.parametrize("cancel_during", ["creation", "reaping"])
async def test_repeated_cancel_waits_for_owned_cleanup(monkeypatch, cancel_during):
    spawning = asyncio.Event()
    allow_spawn = asyncio.Event()
    communicating = asyncio.Event()
    reaping = asyncio.Event()
    allow_reap = asyncio.Event()
    proc = SimpleNamespace(
        pid=123,
        returncode=None,
        stdout=SimpleNamespace(read=AsyncMock(return_value=b"")),
        stderr=SimpleNamespace(read=AsyncMock(return_value=b"")),
    )

    async def communicate(**kwargs):
        communicating.set()
        await asyncio.Event().wait()

    async def wait():
        reaping.set()
        await allow_reap.wait()
        proc.returncode = -1

    proc.communicate = communicate
    proc.wait = wait
    proc.kill = Mock()

    async def spawn(*args, **kwargs):
        spawning.set()
        await allow_spawn.wait()
        return proc

    kill_group = Mock()
    monkeypatch.setattr(_process, "IS_WINDOWS", False)
    monkeypatch.setattr(_process.os, "killpg", kill_group)
    monkeypatch.setattr(_process.asyncio, "create_subprocess_shell", spawn)
    task = asyncio.create_task(
        _process.communicate_command(
            "synthetic", payload=b"", timeout=10, cwd=None, env={}
        )
    )
    try:
        await asyncio.wait_for(spawning.wait(), 5)
        if cancel_during == "reaping":
            allow_spawn.set()
            await asyncio.wait_for(communicating.wait(), 5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        allow_spawn.set()
        await asyncio.wait_for(reaping.wait(), 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        allow_reap.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        kill_group.assert_called_once_with(proc.pid, signal.SIGKILL)
        assert proc.returncode == -1
    finally:
        allow_spawn.set()
        allow_reap.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("cancel", [True, False], ids=["cancel", "timeout"])
async def test_windows_job_and_tree_cleanup_reaps_and_releases(monkeypatch, cancel):
    ready = asyncio.Event()
    popen = object()
    proc = SimpleNamespace(
        pid=123,
        returncode=None,
        stdout=SimpleNamespace(read=AsyncMock(return_value=b"")),
        stderr=SimpleNamespace(read=AsyncMock(return_value=b"")),
        _transport=SimpleNamespace(get_extra_info=Mock(return_value=popen)),
        kill=Mock(),
    )

    async def communicate(**kwargs):
        ready.set()
        if cancel:
            await asyncio.Event().wait()
        raise asyncio.TimeoutError

    async def wait():
        proc.returncode = -1

    proc.communicate = communicate
    proc.wait = AsyncMock(side_effect=wait)
    spawn = AsyncMock(return_value=proc)
    killer = SimpleNamespace(wait=AsyncMock(return_value=0))
    kill_tree = AsyncMock(return_value=killer)
    attach, terminate, release = Mock(), Mock(), Mock()
    log = Mock()
    monkeypatch.setattr(_process, "log_error", log)
    monkeypatch.setattr(_process, "IS_WINDOWS", True)
    monkeypatch.setattr(
        _process.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False
    )
    monkeypatch.setattr(_process.asyncio, "create_subprocess_shell", spawn)
    monkeypatch.setattr(_process.asyncio, "create_subprocess_exec", kill_tree)
    monkeypatch.setattr(_process, "attach_job", attach)
    monkeypatch.setattr(_process, "terminate_job", terminate)
    monkeypatch.setattr(_process, "release_job", release)
    task = asyncio.create_task(
        _process.communicate_command(
            "synthetic", payload=b"", timeout=10, cwd=None, env={}
        )
    )
    await asyncio.wait_for(ready.wait(), 5)
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else asyncio.TimeoutError):
        await task
    assert spawn.call_args.kwargs["creationflags"] == 512
    assert "start_new_session" not in spawn.call_args.kwargs
    attach.assert_called_once_with(popen)
    terminate.assert_called_once_with(popen)
    release.assert_called_once_with(popen)
    assert kill_tree.call_args.args == ("taskkill", "/F", "/T", "/PID", "123")
    proc.kill.assert_called_once()
    proc.wait.assert_awaited_once()
    log.assert_not_called()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group branch")
async def test_cleanup_error_is_logged_once_without_swallowing_cancel(monkeypatch):
    ready = asyncio.Event()

    async def communicate(**kwargs):
        ready.set()
        await asyncio.Event().wait()

    proc = SimpleNamespace(
        communicate=communicate,
        wait=AsyncMock(),
        returncode=0,
        pid=123,
        stdout=SimpleNamespace(read=AsyncMock(return_value=b"")),
        stderr=SimpleNamespace(read=AsyncMock(return_value=b"")),
    )
    monkeypatch.setattr(_process, "IS_WINDOWS", False)
    monkeypatch.setattr(
        _process.asyncio, "create_subprocess_shell", AsyncMock(return_value=proc)
    )
    monkeypatch.setattr(
        _process.os, "killpg", Mock(side_effect=PermissionError("synthetic"))
    )
    log = Mock(side_effect=RuntimeError("logger unavailable"))
    monkeypatch.setattr(_process, "log_error", log)
    task = asyncio.create_task(
        _process.communicate_command(
            "synthetic", payload=b"", timeout=10, cwd=None, env={}
        )
    )
    await asyncio.wait_for(ready.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    log.assert_called_once()
    assert isinstance(log.call_args.args[0], PermissionError)
    proc.wait.assert_awaited_once()


async def test_cancel_reaps_hook_with_full_output_pipes(tmp_path):
    ready = tmp_path / "output-ready"
    script = (
        "import pathlib,sys,time; "
        f"pathlib.Path({str(ready)!r}).touch(); "
        "sys.stdout.write('x' * 1000000); sys.stdout.flush(); time.sleep(2)"
    )
    hook = HookConfig(matcher="*", type="command", command=python_command(script))
    task = asyncio.create_task(executor.execute_hook(hook, event()))
    try:
        await wait_for_file(ready)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_timeout_reaps_tree_and_preserves_block_verdict(tmp_path):
    marker = tmp_path / "after-timeout"
    script = (
        f"import pathlib,time; time.sleep(0.5); pathlib.Path({str(marker)!r}).touch()"
    )
    hook = HookConfig(
        matcher="*", type="command", command=python_command(script), timeout=200
    )
    result = await executor.execute_hook(hook, event())
    await asyncio.sleep(0.6)
    assert result.blocked and result.exit_code == -1
    assert "timed out" in result.error
    assert not marker.exists()
