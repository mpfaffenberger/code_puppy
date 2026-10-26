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


async def test_shell_command_env_keeps_non_agent_tokens(monkeypatch):
    """Tokens the agent does not authenticate with pass through to children.

    ``GITHUB_TOKEN`` and AWS keys belong to the user's tooling (gh, git, aws
    cli); stripping them broke child commands while leaving custom provider
    credentials untouched. Only provider credentials are removed.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-user-token")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-user-secret")

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

    await command_runner.run_shell_command(MagicMock(), "echo hi", None, 5, False)

    env = captured["env"]
    assert env["GITHUB_TOKEN"] == "ghp-user-token"
    assert env["AWS_SECRET_ACCESS_KEY"] == "aws-user-secret"


async def test_shell_command_env_strips_configured_model_credentials(monkeypatch):
    """A custom ``$ENV`` credential referenced by a configured model is stripped."""

    monkeypatch.setattr(
        "code_puppy.provider_credentials.all_api_key_env_vars",
        lambda: ["MY_CUSTOM_PROVIDER_KEY"],
    )
    monkeypatch.setenv("MY_CUSTOM_PROVIDER_KEY", "custom-secret")

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

    await command_runner.run_shell_command(MagicMock(), "echo hi", None, 5, False)

    assert "MY_CUSTOM_PROVIDER_KEY" not in captured["env"]


async def test_shell_command_env_strips_well_known_provider_keys(monkeypatch):
    """Provider keys beyond the original eight are stripped from the child env.

    With an empty catalog the scrub set is just the well-known names, which now
    cover every provider code_puppy manages (GROQ, MISTRAL, ...), so they no
    longer leak into child shells.
    """
    monkeypatch.setattr(
        "code_puppy.provider_credentials.all_api_key_env_vars", lambda: []
    )
    monkeypatch.setenv("GROQ_API_KEY", "groq-secret")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-secret")

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

    await command_runner.run_shell_command(MagicMock(), "echo hi", None, 5, False)

    assert "GROQ_API_KEY" not in captured["env"]
    assert "MISTRAL_API_KEY" not in captured["env"]


def test_hook_environment_includes_provider_credentials(monkeypatch):
    """Hooks are user config, so provider keys are inherited (a hook may call an LLM)."""
    from code_puppy.hook_engine.executor import _build_environment
    from code_puppy.hook_engine.models import EventData

    monkeypatch.setenv("ANTHROPIC_API_KEY", "agent-key")
    monkeypatch.setenv("GITHUB_TOKEN", "user-token")

    env = _build_environment(
        EventData(
            event_type="PreToolUse",
            tool_name="Edit",
            tool_args={"file_path": "a.py"},
        )
    )

    assert env["ANTHROPIC_API_KEY"] == "agent-key"
    assert env["GITHUB_TOKEN"] == "user-token"
    assert env["CLAUDE_TOOL_NAME"] == "Edit"
    assert env["CLAUDE_FILE_PATH"] == "a.py"
