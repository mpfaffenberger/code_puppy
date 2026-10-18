"""The model must know the host OS and the shell used by the shell tool."""

import pytest

from code_puppy.agents import _environment
from code_puppy.agents.agent_code_puppy import CodePuppyAgent


@pytest.mark.parametrize("system", ["Linux", "Darwin", "FreeBSD"])
def test_posix_uses_sh_not_interactive_shell(monkeypatch, system):
    monkeypatch.setattr(_environment.platform, "system", lambda: system)
    monkeypatch.setattr(_environment.sys, "platform", "linux")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    text = _environment.get_execution_environment_prompt()
    assert f"Operating system: {system}" in text
    assert "Command shell: /bin/sh" in text
    assert "/bin/zsh" not in text
    assert "GNU-only" in text


def test_windows_uses_comspec_not_powershell_terminal(monkeypatch):
    monkeypatch.setattr(_environment.platform, "system", lambda: "Windows")
    monkeypatch.setattr(_environment.sys, "platform", "win32")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    monkeypatch.setenv("SHELL", "pwsh.exe")
    text = _environment.get_execution_environment_prompt()
    assert "Operating system: Windows" in text
    assert r"Command shell: C:\Windows\System32\cmd.exe" in text
    assert "%NAME%" in text
    assert "do not use PowerShell cmdlets" in text


def test_windows_fallback(monkeypatch):
    monkeypatch.setattr(_environment.sys, "platform", "win32")
    monkeypatch.delenv("COMSPEC", raising=False)
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    text = _environment.get_execution_environment_prompt()
    assert "cmd.exe" in text


def test_android_uses_subprocess_android_shell(monkeypatch):
    monkeypatch.setattr(_environment.sys, "platform", "android")
    monkeypatch.setattr(
        _environment.sys, "getandroidapilevel", lambda: 35, raising=False
    )
    assert (
        "Command shell: /system/bin/sh"
        in _environment.get_execution_environment_prompt()
    )


def test_unknown_os_falls_back_to_sys_platform(monkeypatch):
    monkeypatch.setattr(_environment.platform, "system", lambda: "")
    monkeypatch.setattr(_environment.sys, "platform", "freebsd")
    assert (
        "Operating system: freebsd" in _environment.get_execution_environment_prompt()
    )


def test_shared_runtime_contains_environment_without_plugins(monkeypatch):
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])
    agent = CodePuppyAgent()
    text = agent.get_runtime_system_prompt()
    assert "Execution environment (local shell tool):" in text
    assert "Operating system:" in text
    assert "Command shell:" in text
    assert agent.get_identity() in text
    assert "Execution environment (local shell tool):" not in agent.get_system_prompt()
    assert agent.get_full_system_prompt() == agent.get_system_prompt() + text
