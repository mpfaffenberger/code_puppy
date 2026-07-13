from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_confirmation_lock_released_when_approval_raises(monkeypatch):
    from code_puppy.tools import command_runner

    # ensure unlocked before test begins
    if command_runner._CONFIRMATION_LOCK.locked():
        command_runner._CONFIRMATION_LOCK.release()

    async def _empty_callbacks(*_args, **_kwargs):
        return []

    async def _boom_approval(**_kwargs):
        raise RuntimeError("approval transport failed")

    monkeypatch.setattr("code_puppy.callbacks.on_run_shell_command", _empty_callbacks)
    monkeypatch.setattr("code_puppy.config.get_yolo_mode", lambda: False)
    monkeypatch.setattr("code_puppy.tools.command_runner.is_subagent", lambda: False)
    monkeypatch.setattr(
        "code_puppy.api.permission_plugin.get_websocket_context", lambda: None
    )
    monkeypatch.setattr(
        "code_puppy.tools.command_runner.get_user_approval_async",
        _boom_approval,
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    with pytest.raises(RuntimeError, match="approval transport failed"):
        await command_runner.run_shell_command(
            context=SimpleNamespace(),
            command="echo hi",
            cwd=".",
            timeout=5,
            background=False,
        )

    # lock should be free for future commands
    acquired = command_runner._CONFIRMATION_LOCK.acquire(blocking=False)
    assert acquired is True
    if acquired:
        command_runner._CONFIRMATION_LOCK.release()
