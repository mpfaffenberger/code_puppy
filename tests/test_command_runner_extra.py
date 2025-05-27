import pytest
from unittest.mock import patch, MagicMock, ANY
from code_agent.tools.command_runner import run_shell_command

def test_run_shell_command_empty():
    result = run_shell_command({}, "")
    assert "error" in result and "empty" in result["error"].lower()

def test_run_shell_command_fail_exit():
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("ok", "ERR")
    mock_proc.returncode = 2
    with patch("subprocess.Popen", return_value=mock_proc):
        result = run_shell_command({}, "false")
        assert result["exit_code"] == 2
        assert not result["success"]
        assert "ERR" in result["stderr"]

def test_run_shell_command_timeout():
    mock_proc = MagicMock()
    def _communicate(**kwargs):
        raise TimeoutError("timeout!")
    with patch("subprocess.Popen", return_value=mock_proc):
        mock_proc.communicate.side_effect = TimeoutError
        with patch("time.time", side_effect=[0,3]):
            res = run_shell_command({}, "sleep 3", timeout=1)
            assert not res["success"] or res["timeout"]

def test_run_shell_command_exception():
    with patch("subprocess.Popen", side_effect=Exception("oh no!")):
        res = run_shell_command({}, "boom!")
        assert not res["success"]
        assert "error" in res

def test_run_shell_command_cwd():
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("cwd output", "")
    mock_proc.returncode = 0
    with patch("subprocess.Popen", return_value=mock_proc) as p:
        out = run_shell_command({}, "echo cwd", cwd="/tmp")
        assert out["success"]
        assert out["stdout"] == "cwd output"
        p.assert_called_with(
            "echo cwd", shell=True, stdout=ANY, stderr=ANY, text=True, cwd="/tmp"
        )
