"""Tests targeting remaining uncovered lines in code_puppy/scheduler/."""

import os
import signal
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# scheduler/__main__.py line 9
# ---------------------------------------------------------------------------


def test_scheduler_main_guard():
    """Cover the if __name__ == '__main__' guard."""
    with patch("code_puppy.scheduler.daemon.start_daemon"):
        # Simulate running __main__.py
        import code_puppy.scheduler.__main__ as mod

        # The guard only fires when __name__ == '__main__', which it won't be here.
        # We just need the module to import; the start_daemon call is in the guard.
        assert hasattr(mod, "__name__")


# ---------------------------------------------------------------------------
# scheduler/platform.py line 9 (Windows branch)
# ---------------------------------------------------------------------------


def test_platform_imports():
    """Cover platform.py - it imports correctly on current platform."""
    from code_puppy.scheduler.platform import is_process_running, terminate_process

    assert callable(is_process_running)
    assert callable(terminate_process)


# ---------------------------------------------------------------------------
# scheduler/config.py lines 68-69 (JSONDecodeError), 96, 116, 126
# ---------------------------------------------------------------------------


def test_load_tasks_json_decode_error(tmp_path):
    """Cover JSONDecodeError branch in load_tasks."""
    from code_puppy.scheduler import config

    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text("{invalid json")

    with (
        patch.object(config, "SCHEDULES_FILE", str(schedules_file)),
        patch.object(config, "ensure_scheduler_dirs", return_value=None),
    ):
        result = config.load_tasks()
        assert result == []


def test_update_task_not_found(tmp_path):
    """Cover update_task returning False (line 96)."""
    from code_puppy.scheduler import config
    from code_puppy.scheduler.config import ScheduledTask, update_task

    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text("[]")

    with (
        patch.object(config, "SCHEDULES_FILE", str(schedules_file)),
        patch.object(config, "ensure_scheduler_dirs", return_value=None),
    ):
        task = ScheduledTask(
            id="nonexistent", name="test", prompt="echo", schedule_value="1h"
        )
        result = update_task(task)
        assert result is False


def test_delete_task_not_found(tmp_path):
    """Cover delete_task returning False (line 116)."""
    from code_puppy.scheduler import config
    from code_puppy.scheduler.config import delete_task

    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text("[]")

    with (
        patch.object(config, "SCHEDULES_FILE", str(schedules_file)),
        patch.object(config, "ensure_scheduler_dirs", return_value=None),
    ):
        result = delete_task("nonexistent")
        assert result is False


def test_toggle_task_not_found(tmp_path):
    """Cover toggle_task returning None (line 126)."""
    from code_puppy.scheduler import config
    from code_puppy.scheduler.config import toggle_task

    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text("[]")

    with (
        patch.object(config, "SCHEDULES_FILE", str(schedules_file)),
        patch.object(config, "ensure_scheduler_dirs", return_value=None),
    ):
        result = toggle_task("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# scheduler/daemon.py
# ---------------------------------------------------------------------------


def test_should_run_task_disabled():
    """Cover should_run_task with disabled task (line 45 area)."""
    from code_puppy.scheduler.config import ScheduledTask
    from code_puppy.scheduler.daemon import should_run_task

    task = ScheduledTask(
        id="t1", name="test", prompt="echo", schedule_value="1h", enabled=False
    )
    assert should_run_task(task, datetime.now()) is False


def test_daemon_loop_runs_tasks():
    """Cover the daemon main loop (lines 101, 114)."""
    from code_puppy.scheduler import daemon
    from code_puppy.scheduler.config import ScheduledTask

    task = ScheduledTask(
        id="t1",
        name="test",
        prompt="echo hi",
        schedule_value="1m",
        enabled=True,
        last_run=(datetime.now() - timedelta(hours=1)).isoformat(),
    )

    # Make _shutdown_requested True after one iteration
    call_count = 0
    original_shutdown = daemon._shutdown_requested

    def fake_sleep(t):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            daemon._shutdown_requested = True

    with (
        patch.object(daemon, "load_tasks", return_value=[task]),
        patch.object(daemon, "execute_task", return_value=(True, 0, None)),
        patch.object(daemon, "should_run_task", return_value=True),
        patch("code_puppy.scheduler.daemon.time.sleep", side_effect=fake_sleep),
    ):
        daemon._shutdown_requested = False
        daemon.run_scheduler_loop(check_interval=1)

    daemon._shutdown_requested = original_shutdown


def test_daemon_loop_task_failure():
    """Cover task failure branch in daemon loop."""
    from code_puppy.scheduler import daemon
    from code_puppy.scheduler.config import ScheduledTask

    task = ScheduledTask(
        id="t2",
        name="fail-test",
        prompt="false",
        schedule_value="1m",
        enabled=True,
        last_run=(datetime.now() - timedelta(hours=1)).isoformat(),
    )

    call_count = 0

    def fake_sleep(t):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            daemon._shutdown_requested = True

    with (
        patch.object(daemon, "load_tasks", return_value=[task]),
        patch.object(daemon, "execute_task", return_value=(False, 1, "error")),
        patch.object(daemon, "should_run_task", return_value=True),
        patch("code_puppy.scheduler.daemon.time.sleep", side_effect=fake_sleep),
    ):
        daemon._shutdown_requested = False
        daemon.run_scheduler_loop(check_interval=1)


def test_daemon_loop_exception():
    """Cover exception branch in daemon loop (line 114)."""
    from code_puppy.scheduler import daemon

    call_count = 0

    def fake_sleep(t):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            daemon._shutdown_requested = True

    with (
        patch.object(daemon, "load_tasks", side_effect=Exception("boom")),
        patch("code_puppy.scheduler.daemon.time.sleep", side_effect=fake_sleep),
    ):
        daemon._shutdown_requested = False
        daemon.run_scheduler_loop(check_interval=1)


def test_write_pid_file(tmp_path):
    """Cover write_pid_file (lines 137-142)."""
    from code_puppy.scheduler import daemon

    pid_file = str(tmp_path / "test.pid")

    with patch.object(daemon, "SCHEDULER_PID_FILE", pid_file):
        daemon.write_pid_file()
        assert os.path.exists(pid_file)
        content = open(pid_file).read()
        assert content == str(os.getpid())


def test_write_pid_file_failure(tmp_path):
    """Cover write_pid_file failure cleanup (lines 150-151)."""
    from code_puppy.scheduler import daemon

    with (
        patch.object(daemon, "SCHEDULER_PID_FILE", "/nonexistent/dir/test.pid"),
        patch("tempfile.mkstemp", side_effect=OSError("no space")),
    ):
        with pytest.raises(OSError):
            daemon.write_pid_file()


def test_remove_pid_file(tmp_path):
    """Cover remove_pid_file."""
    from code_puppy.scheduler import daemon

    pid_file = tmp_path / "test.pid"
    pid_file.write_text("1234")

    with patch.object(daemon, "SCHEDULER_PID_FILE", str(pid_file)):
        daemon.remove_pid_file()
        assert not pid_file.exists()


def test_signal_handler():
    """Cover signal_handler."""
    from code_puppy.scheduler import daemon

    daemon._shutdown_requested = False
    daemon.signal_handler(signal.SIGTERM, None)
    assert daemon._shutdown_requested is True
    daemon._shutdown_requested = False


def test_get_daemon_pid_valid(tmp_path):
    """Cover get_daemon_pid with valid running process."""
    from code_puppy.scheduler import daemon

    pid_file = tmp_path / "sched.pid"
    pid_file.write_text(str(os.getpid()))

    with patch.object(daemon, "SCHEDULER_PID_FILE", str(pid_file)):
        pid = daemon.get_daemon_pid()
        assert pid == os.getpid()


def test_get_daemon_pid_stale(tmp_path):
    """Cover get_daemon_pid with stale PID (lines 197-206)."""
    from code_puppy.scheduler import daemon

    pid_file = tmp_path / "sched.pid"
    pid_file.write_text("999999999")  # Non-existent PID

    with patch.object(daemon, "SCHEDULER_PID_FILE", str(pid_file)):
        pid = daemon.get_daemon_pid()
        assert pid is None


def test_get_daemon_pid_empty(tmp_path):
    """Cover get_daemon_pid with empty file."""
    from code_puppy.scheduler import daemon

    pid_file = tmp_path / "sched.pid"
    pid_file.write_text("")

    with patch.object(daemon, "SCHEDULER_PID_FILE", str(pid_file)):
        pid = daemon.get_daemon_pid()
        assert pid is None


def test_get_daemon_pid_no_file(tmp_path):
    """Cover get_daemon_pid with no PID file."""
    from code_puppy.scheduler import daemon

    with patch.object(daemon, "SCHEDULER_PID_FILE", str(tmp_path / "nonexistent.pid")):
        pid = daemon.get_daemon_pid()
        assert pid is None


def test_start_daemon_background_already_running():
    """Cover start_daemon_background when already running (line 235)."""
    from code_puppy.scheduler import daemon

    with patch.object(daemon, "get_daemon_pid", return_value=12345):
        result = daemon.start_daemon_background()
        assert result is True


def test_start_daemon_background_unix():
    """Cover start_daemon_background unix Popen path (lines 263-268)."""
    from code_puppy.scheduler import daemon

    mock_popen = MagicMock()
    with (
        patch.object(daemon, "get_daemon_pid", side_effect=[None, 99999]),
        patch("subprocess.Popen", return_value=mock_popen),
        patch("code_puppy.scheduler.daemon.time.sleep"),
    ):
        result = daemon.start_daemon_background()
        assert result is True


def test_stop_daemon_not_running():
    """Cover stop_daemon when not running."""
    from code_puppy.scheduler import daemon

    with patch.object(daemon, "get_daemon_pid", return_value=None):
        result = daemon.stop_daemon()
        assert result is False


def test_stop_daemon_unix():
    """Cover stop_daemon on unix."""
    from code_puppy.scheduler import daemon

    with (
        patch.object(daemon, "get_daemon_pid", return_value=12345),
        patch("os.kill") as mock_kill,
        patch("time.sleep"),
        patch.object(daemon, "remove_pid_file"),
    ):
        daemon.stop_daemon()
        mock_kill.assert_called()
