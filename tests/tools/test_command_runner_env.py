"""Tests for the environment handed to child shell processes."""

from unittest.mock import MagicMock

from code_puppy.tools import command_runner


class _StopPopen(Exception):
    """Sentinel raised by the fake Popen once the env has been captured."""


async def test_shell_command_env_excludes_api_keys(monkeypatch):
    """Child shell processes run without the agent's credential env vars.

    A fake API key set on the parent environment must not appear in the env
    passed to the spawned process, while PATH and other non-secret variables
    are preserved so commands still work.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-leak")

    captured = {}

    def fake_popen(*args, **kwargs):
        captured["env"] = kwargs.get("env")
        raise _StopPopen()

    monkeypatch.setattr(command_runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        command_runner, "get_command_executor", lambda: None, raising=False
    )

    async def _no_callbacks(*args, **kwargs):
        return []

    monkeypatch.setattr("code_puppy.callbacks.on_run_shell_command", _no_callbacks)

    result = await command_runner.run_shell_command(
        MagicMock(), "echo hi", None, 5, False
    )

    assert result.success is False
    assert "env" in captured
    env = captured["env"]
    assert env is not None
    assert "ANTHROPIC_API_KEY" not in env
    assert "PATH" in env
