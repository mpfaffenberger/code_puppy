import subprocess
from unittest.mock import MagicMock, patch
import pytest
from code_agent.tools.command_runner import run_shell_command


def test_run_shell_command_success(monkeypatch):
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("output", "")
    mock_process.returncode = 0

    with patch("subprocess.Popen", return_value=mock_process):
        result = run_shell_command(None, "echo Test")

    assert result["success"] is True
    assert result["stdout"] == "output"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0
    assert result["timeout"] is False


def test_run_shell_command_failure(monkeypatch):
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("", "error")
    mock_process.returncode = 1

    with patch("subprocess.Popen", return_value=mock_process):
        result = run_shell_command(None, "fail_command")

    assert result["success"] is False
    assert result["stdout"] == ""
    assert result["stderr"] == "error"
    assert result["exit_code"] == 1
    assert result["timeout"] is False


def test_run_shell_command_exception(monkeypatch):
    with patch("subprocess.Popen", side_effect=Exception("boom")):
        result = run_shell_command(None, "explode")

    assert result["success"] is False
    assert result["exit_code"] == -1
    assert result["timeout"] is False
    assert "boom" in result["error"]

