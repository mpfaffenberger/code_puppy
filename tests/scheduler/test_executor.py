"""Tests for code_puppy/scheduler/executor.py - full coverage."""

from unittest.mock import MagicMock, mock_open, patch

from code_puppy.scheduler.config import ScheduledTask
from code_puppy.scheduler.executor import (
    execute_task,
    get_code_puppy_command,
    run_task_by_id,
)


def _make_task(**overrides):
    defaults = dict(
        id="test-id",
        name="test-task",
        prompt="do something",
        agent="code-puppy",
        model="gpt-5",
        working_directory=".",
    )
    defaults.update(overrides)
    return ScheduledTask(**defaults)


class TestGetCodePuppyCommand:
    def test_returns_code_puppy(self):
        assert get_code_puppy_command() == "code-puppy"

    @patch("sys.platform", "win32")
    def test_returns_code_puppy_windows(self):
        # Re-import to test the branch - but the function just returns "code-puppy" either way
        assert get_code_puppy_command() == "code-puppy"


class TestExecuteTask:
    @patch("code_puppy.scheduler.executor.update_task")
    @patch("subprocess.Popen")
    @patch("os.path.isdir", return_value=True)
    @patch("os.makedirs")
    def test_success(self, mock_mkdirs, mock_isdir, mock_popen, mock_update):
        proc = MagicMock()
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        task = _make_task()
        with patch("builtins.open", mock_open()):
            success, code, err = execute_task(task)

        assert success is True
        assert code == 0
        assert err == ""
        assert task.last_status == "success"

    @patch("code_puppy.scheduler.executor.update_task")
    @patch("subprocess.Popen")
    @patch("os.path.isdir", return_value=True)
    @patch("os.makedirs")
    def test_failure_exit_code(self, mock_mkdirs, mock_isdir, mock_popen, mock_update):
        proc = MagicMock()
        proc.wait.return_value = 1
        mock_popen.return_value = proc

        task = _make_task()
        with patch("builtins.open", mock_open()):
            success, code, err = execute_task(task)

        assert success is False
        assert code == 1
        assert task.last_status == "failed"

    @patch("code_puppy.scheduler.executor.update_task")
    def test_working_dir_not_found(self, mock_update):
        task = _make_task(working_directory="/nonexistent/path")
        with patch("os.path.isdir", return_value=False), patch("os.makedirs"):
            success, code, err = execute_task(task)

        assert success is False
        assert code == -1
        assert "not found" in err

    @patch("code_puppy.scheduler.executor.update_task")
    @patch("os.path.isdir", return_value=True)
    @patch("os.makedirs")
    def test_file_not_found_error(self, mock_mkdirs, mock_isdir, mock_update):
        task = _make_task()
        with (
            patch("builtins.open", mock_open()),
            patch("subprocess.Popen", side_effect=FileNotFoundError("not found")),
        ):
            success, code, err = execute_task(task)

        assert success is False
        assert "not found" in err

    @patch("code_puppy.scheduler.executor.update_task")
    @patch("os.path.isdir", return_value=True)
    @patch("os.makedirs")
    def test_generic_exception(self, mock_mkdirs, mock_isdir, mock_update):
        task = _make_task()
        with (
            patch("builtins.open", mock_open()),
            patch("subprocess.Popen", side_effect=RuntimeError("boom")),
        ):
            success, code, err = execute_task(task)

        assert success is False
        assert "boom" in err

    @patch("code_puppy.scheduler.executor.update_task")
    @patch("subprocess.Popen")
    @patch("os.path.isdir", return_value=True)
    @patch("os.makedirs")
    def test_no_model_no_agent(self, mock_mkdirs, mock_isdir, mock_popen, mock_update):
        proc = MagicMock()
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        task = _make_task(model="", agent="")
        with patch("builtins.open", mock_open()):
            success, _, _ = execute_task(task)
        assert success is True
        # Check that --model and --agent were NOT in the command
        cmd = mock_popen.call_args[0][0]
        assert "--model" not in cmd
        assert "--agent" not in cmd

    @patch("code_puppy.scheduler.executor.update_task")
    @patch("subprocess.Popen")
    @patch("os.path.isdir", return_value=True)
    @patch("os.makedirs")
    def test_empty_working_dir(self, mock_mkdirs, mock_isdir, mock_popen, mock_update):
        proc = MagicMock()
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        task = _make_task(working_directory="")
        with patch("builtins.open", mock_open()):
            success, _, _ = execute_task(task)
        assert success is True

    @patch("code_puppy.scheduler.executor.update_task")
    @patch("subprocess.Popen")
    @patch("os.path.isdir", return_value=True)
    @patch("os.makedirs")
    def test_custom_log_file(self, mock_mkdirs, mock_isdir, mock_popen, mock_update):
        proc = MagicMock()
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        task = _make_task(log_file="/tmp/custom.log")
        with patch("builtins.open", mock_open()):
            success, _, _ = execute_task(task)
        assert success is True

    @patch("code_puppy.scheduler.executor.update_task")
    @patch("subprocess.Popen")
    @patch("os.path.isdir", return_value=True)
    @patch("os.makedirs")
    def test_empty_log_file_gets_default(
        self, mock_mkdirs, mock_isdir, mock_popen, mock_update
    ):
        proc = MagicMock()
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        task = _make_task()
        # Force log_file to empty to hit the branch
        task.log_file = ""
        with patch("builtins.open", mock_open()):
            success, _, _ = execute_task(task)
        assert success is True


class TestRunTaskById:
    @patch("code_puppy.scheduler.executor.execute_task")
    @patch("code_puppy.scheduler.config.get_task")
    def test_success(self, mock_get, mock_exec):
        task = _make_task()
        mock_get.return_value = task
        mock_exec.return_value = (True, 0, "")

        ok, msg = run_task_by_id("test-id")
        assert ok is True
        assert "successfully" in msg

    @patch("code_puppy.scheduler.config.get_task")
    def test_not_found(self, mock_get):
        mock_get.return_value = None
        ok, msg = run_task_by_id("missing")
        assert ok is False
        assert "not found" in msg

    @patch("code_puppy.scheduler.executor.execute_task")
    @patch("code_puppy.scheduler.config.get_task")
    def test_failure(self, mock_get, mock_exec):
        task = _make_task()
        mock_get.return_value = task
        mock_exec.return_value = (False, 1, "oops")

        ok, msg = run_task_by_id("test-id")
        assert ok is False
        assert "failed" in msg
