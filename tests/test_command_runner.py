import subprocess
from unittest.mock import patch, MagicMock
from code_puppy.tools.command_runner import run_shell_command

def test_run_shell_command_timeout():
    with patch("subprocess.Popen") as mock_popen:
        mock_process = mock_popen.return_value
        # When communicate is called with timeout param, raise TimeoutExpired
        def communicate_side_effect(*args, **kwargs):
            if 'timeout' in kwargs:
                raise subprocess.TimeoutExpired(cmd="dummy_command", timeout=1)
            return ("", "")
        mock_process.communicate.side_effect = communicate_side_effect
        mock_process.kill.side_effect = lambda: None
        result = run_shell_command(None, "dummy_command", timeout=1)
        assert result.get("timeout") is True
        assert "timed out" in result.get("error")
        assert result.get("exit_code") is None

def test_run_shell_command_empty_command():
    result = run_shell_command(None, " ")
    assert "error" in result
    assert result["error"] == "Command cannot be empty"


def test_run_shell_command_success():
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("output", "")
    mock_process.returncode = 0

    with patch("subprocess.Popen", return_value=mock_process):
        result = run_shell_command(None, "echo test")

    assert result["exit_code"] == 0
    assert result["stdout"] == "output"
    assert result["stderr"] == ""


def test_run_shell_command_error():
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("", "error")
    mock_process.returncode = 1

    with patch("subprocess.Popen", return_value=mock_process):
        result = run_shell_command(None, "badcmd")

    assert result["exit_code"] == 1
    assert result["stdout"] == ""
    assert result["stderr"] == "error"
