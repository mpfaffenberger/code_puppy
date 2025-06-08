import subprocess
from unittest.mock import MagicMock, patch

from code_puppy.tools.command_runner import run_shell_command


def test_run_shell_command_timeout():
    with patch("subprocess.Popen") as mock_popen:
        mock_process = mock_popen.return_value

        # When communicate is called with timeout param, raise TimeoutExpired
        def communicate_side_effect(*args, **kwargs):
            if "timeout" in kwargs:
                raise subprocess.TimeoutExpired(cmd="dummy_command", timeout=1)
            return ("", "")

        mock_process.communicate.side_effect = communicate_side_effect
        mock_process.kill.side_effect = lambda: None
        with patch("builtins.input", return_value="yes"):
            result = run_shell_command(None, "dummy_command", timeout=1)
            assert result.get("timeout") is True
            assert "timed out" in result.get("error")
            assert result.get("exit_code") is None


def test_run_shell_command_empty():
    from code_puppy.tools.command_runner import run_shell_command

    result = run_shell_command(None, " ")
    assert result["error"] == "Command cannot be empty"


def test_run_shell_command_success():
    with patch("subprocess.Popen") as mock_popen:
        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = ("output", "")
        mock_process.returncode = 0
        result = run_shell_command(None, "echo hi")
        assert result["success"] is True
        assert result["stdout"] == "output"
        assert result["stderr"] == ""
        assert result["exit_code"] == 0


def test_run_shell_command_nonzero_exit():
    with patch("subprocess.Popen") as mock_popen:
        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = ("", "error")
        mock_process.returncode = 2
        result = run_shell_command(None, "false")
        assert result["success"] is False
        assert result["exit_code"] == 2
        assert result["stderr"] == "error"


def test_run_shell_command_timeout_user_no():
    with patch("subprocess.Popen") as mock_popen:
        mock_process = mock_popen.return_value

        def communicate_side_effect(*args, **kwargs):
            if "timeout" in kwargs:
                raise subprocess.TimeoutExpired(cmd="dummy_command", timeout=1)
            return ("", "")

        mock_process.communicate.side_effect = communicate_side_effect
        with patch("builtins.input", return_value="no"):
            result = run_shell_command(None, "dummy_command", timeout=1)
            assert result["timeout"] is True
            assert result["success"] is False
            assert result["exit_code"] is None


def test_run_shell_command_FileNotFoundError():
    with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
        result = run_shell_command(None, "doesnotexist")
        assert result["success"] is False
        assert "not found" in result["error"]


def test_run_shell_command_OSError():
    with patch("subprocess.Popen", side_effect=OSError("bad os")):
        result = run_shell_command(None, "doesnotexist")
        assert result["success"] is False
        assert "bad os" in result["error"]


def test_run_shell_command_generic_exception():
    with patch("subprocess.Popen", side_effect=Exception("fail!")):
        result = run_shell_command(None, "doesnotexist")
        assert result["success"] is False
        assert "fail!" in result["error"]


def test_run_shell_command_truncates_output():
    # Output >1000 chars is NOT truncated on success, only on timeout/error
    with patch("subprocess.Popen") as mock_popen:
        mock_process = mock_popen.return_value
        long_out = "x" * 2000
        mock_process.communicate.return_value = (long_out, long_out)
        mock_process.returncode = 0
        result = run_shell_command(None, "echo hi")
        assert len(result["stdout"]) == 2000
        assert len(result["stderr"]) == 2000


def test_run_shell_command_with_cwd():
    with patch("subprocess.Popen") as mock_popen:
        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = ("ok", "")
        mock_process.returncode = 0
        result = run_shell_command(None, "ls", cwd="/tmp")
        mock_popen.assert_called_with(
            "ls",
            shell=True,
            cwd="/tmp",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert result["success"] is True


def test_run_shell_command_get_yolo_mode_true():
    # Should run as normal, but we check that get_yolo_mode is called
    with (
        patch("subprocess.Popen") as mock_popen,
        patch("code_puppy.config.get_yolo_mode", return_value=True) as mock_yolo,
    ):
        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = ("ok", "")
        mock_process.returncode = 0
        result = run_shell_command(None, "ls")
        mock_yolo.assert_called()
        assert result["success"] is True


def test_run_shell_command_get_yolo_mode_false():
    # Should run as normal, but we check that get_yolo_mode is called
    with (
        patch("subprocess.Popen") as mock_popen,
        patch("code_puppy.config.get_yolo_mode", return_value=False) as mock_yolo,
        patch("builtins.input", return_value="yes"),
    ):
        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = ("ok", "")
        mock_process.returncode = 0
        result = run_shell_command(None, "ls")
        mock_yolo.assert_called()
        assert result["success"] is True


def test_run_shell_command_empty_command():
    result = run_shell_command(None, " ")
    assert "error" in result
    assert result["error"] == "Command cannot be empty"


def test_run_shell_command_error():
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("", "error")
    mock_process.returncode = 1

    with patch("subprocess.Popen", return_value=mock_process):
        with patch("builtins.input", return_value="yes"):
            result = run_shell_command(None, "badcmd")

    assert result["exit_code"] == 1
    assert result["stdout"] == ""
    assert result["stderr"] == "error"
