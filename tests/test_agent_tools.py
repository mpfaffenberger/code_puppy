from unittest.mock import patch, MagicMock
from code_puppy.tools.file_operations import read_file
from code_puppy.tools.command_runner import run_shell_command

def test_read_file_nonexistent():
    with patch("os.path.exists", return_value=False):
        result = read_file({}, "fake_path")
        assert "error" in result
        assert "does not exist" in result["error"]


def test_run_shell_command_success():
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("output", "")
    mock_proc.returncode = 0
    with patch("subprocess.Popen", return_value=mock_proc):
        result = run_shell_command({}, "echo hello")
        assert result["success"]
        assert "output" in result["stdout"]
