"""Full coverage tests for scheduler/daemon.py."""

import os
import signal
from datetime import datetime, timedelta
from unittest.mock import patch

from code_puppy.scheduler.config import ScheduledTask
from code_puppy.scheduler.daemon import (
    get_daemon_pid,
    remove_pid_file,
    run_scheduler_loop,
    should_run_task,
    signal_handler,
    start_daemon,
    start_daemon_background,
    stop_daemon,
    write_pid_file,
)


class TestShouldRunTaskExtended:
    """Cover remaining branches of should_run_task."""

    def test_interval_never_run_before(self):
        task = ScheduledTask(
            name="t", prompt="p", schedule_type="interval", schedule_value="1h"
        )
        assert should_run_task(task, datetime.now()) is True

    def test_interval_not_yet_due(self):
        task = ScheduledTask(
            name="t",
            prompt="p",
            schedule_type="interval",
            schedule_value="1h",
            last_run=datetime.now().isoformat(),
        )
        assert should_run_task(task, datetime.now()) is False

    def test_interval_due(self):
        past = (datetime.now() - timedelta(hours=2)).isoformat()
        task = ScheduledTask(
            name="t",
            prompt="p",
            schedule_type="interval",
            schedule_value="1h",
            last_run=past,
        )
        assert should_run_task(task, datetime.now()) is True

    def test_interval_invalid_value(self):
        task = ScheduledTask(
            name="t", prompt="p", schedule_type="interval", schedule_value="invalid"
        )
        assert should_run_task(task, datetime.now()) is False

    def test_hourly_never_run(self):
        task = ScheduledTask(
            name="t", prompt="p", schedule_type="hourly", schedule_value=""
        )
        assert should_run_task(task, datetime.now()) is True

    def test_hourly_not_due(self):
        task = ScheduledTask(
            name="t",
            prompt="p",
            schedule_type="hourly",
            schedule_value="",
            last_run=datetime.now().isoformat(),
        )
        assert should_run_task(task, datetime.now()) is False

    def test_hourly_due(self):
        past = (datetime.now() - timedelta(hours=2)).isoformat()
        task = ScheduledTask(
            name="t",
            prompt="p",
            schedule_type="hourly",
            schedule_value="",
            last_run=past,
        )
        assert should_run_task(task, datetime.now()) is True

    def test_daily_never_run(self):
        task = ScheduledTask(
            name="t", prompt="p", schedule_type="daily", schedule_value=""
        )
        assert should_run_task(task, datetime.now()) is True

    def test_daily_not_due(self):
        task = ScheduledTask(
            name="t",
            prompt="p",
            schedule_type="daily",
            schedule_value="",
            last_run=datetime.now().isoformat(),
        )
        assert should_run_task(task, datetime.now()) is False

    def test_daily_due(self):
        past = (datetime.now() - timedelta(days=2)).isoformat()
        task = ScheduledTask(
            name="t",
            prompt="p",
            schedule_type="daily",
            schedule_value="",
            last_run=past,
        )
        assert should_run_task(task, datetime.now()) is True

    def test_cron_not_supported(self, capsys):
        task = ScheduledTask(
            name="t", prompt="p", schedule_type="cron", schedule_value="* * * * *"
        )
        assert should_run_task(task, datetime.now()) is False
        assert "not yet supported" in capsys.readouterr().out

    def test_unknown_schedule_type(self):
        task = ScheduledTask(
            name="t", prompt="p", schedule_type="unknown", schedule_value=""
        )
        assert should_run_task(task, datetime.now()) is False


class TestRunSchedulerLoop:
    def test_loop_runs_tasks(self):
        import code_puppy.scheduler.daemon as daemon_mod

        task = ScheduledTask(
            name="t", prompt="p", schedule_type="interval", schedule_value="1s"
        )

        call_count = 0

        def mock_sleep(n):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                daemon_mod._shutdown_requested = True

        daemon_mod._shutdown_requested = False
        with (
            patch.object(daemon_mod, "load_tasks", return_value=[task]),
            patch.object(daemon_mod, "execute_task", return_value=(True, 0, None)),
            patch("time.sleep", side_effect=mock_sleep),
        ):
            run_scheduler_loop(check_interval=1)

        daemon_mod._shutdown_requested = False

    def test_loop_handles_exception(self):
        import code_puppy.scheduler.daemon as daemon_mod

        call_count = 0

        def mock_sleep(n):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                daemon_mod._shutdown_requested = True

        daemon_mod._shutdown_requested = False
        with (
            patch.object(daemon_mod, "load_tasks", side_effect=Exception("boom")),
            patch("time.sleep", side_effect=mock_sleep),
        ):
            run_scheduler_loop(check_interval=1)

        daemon_mod._shutdown_requested = False

    def test_loop_task_failure(self):
        import code_puppy.scheduler.daemon as daemon_mod

        task = ScheduledTask(
            name="t", prompt="p", schedule_type="interval", schedule_value="1s"
        )

        call_count = 0

        def mock_sleep(n):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                daemon_mod._shutdown_requested = True

        daemon_mod._shutdown_requested = False
        with (
            patch.object(daemon_mod, "load_tasks", return_value=[task]),
            patch.object(daemon_mod, "execute_task", return_value=(False, 1, "err")),
            patch("time.sleep", side_effect=mock_sleep),
        ):
            run_scheduler_loop(check_interval=1)

        daemon_mod._shutdown_requested = False


class TestWriteRemovePidFile:
    def test_write_and_remove(self, tmp_path):
        pid_file = str(tmp_path / "test.pid")
        with patch("code_puppy.scheduler.daemon.SCHEDULER_PID_FILE", pid_file):
            write_pid_file()
            assert os.path.exists(pid_file)
            with open(pid_file) as f:
                assert f.read().strip() == str(os.getpid())
            remove_pid_file()
            assert not os.path.exists(pid_file)

    def test_remove_nonexistent(self, tmp_path):
        pid_file = str(tmp_path / "nope.pid")
        with patch("code_puppy.scheduler.daemon.SCHEDULER_PID_FILE", pid_file):
            remove_pid_file()  # Should not raise


class TestSignalHandler:
    def test_sets_shutdown(self):
        import code_puppy.scheduler.daemon as daemon_mod

        daemon_mod._shutdown_requested = False
        signal_handler(signal.SIGTERM, None)
        assert daemon_mod._shutdown_requested is True
        daemon_mod._shutdown_requested = False


class TestGetDaemonPid:
    def test_no_pid_file(self, tmp_path):
        pid_file = str(tmp_path / "nope.pid")
        with patch("code_puppy.scheduler.daemon.SCHEDULER_PID_FILE", pid_file):
            assert get_daemon_pid() is None

    def test_empty_pid_file(self, tmp_path):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("")
        with patch("code_puppy.scheduler.daemon.SCHEDULER_PID_FILE", str(pid_file)):
            assert get_daemon_pid() is None

    def test_running_process(self, tmp_path):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text(str(os.getpid()))
        with patch("code_puppy.scheduler.daemon.SCHEDULER_PID_FILE", str(pid_file)):
            result = get_daemon_pid()
            assert result == os.getpid()

    def test_stale_pid(self, tmp_path):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("99999999")  # unlikely to be running
        with (
            patch("code_puppy.scheduler.daemon.SCHEDULER_PID_FILE", str(pid_file)),
            patch("os.kill", side_effect=ProcessLookupError),
        ):
            assert get_daemon_pid() is None

    def test_invalid_pid(self, tmp_path):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("not-a-number")
        with patch("code_puppy.scheduler.daemon.SCHEDULER_PID_FILE", str(pid_file)):
            assert get_daemon_pid() is None


class TestStartDaemonBackground:
    def test_already_running(self):
        with patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123):
            assert start_daemon_background() is True

    def test_starts_new_daemon(self):
        with (
            patch(
                "code_puppy.scheduler.daemon.get_daemon_pid", side_effect=[None, 456]
            ),
            patch("subprocess.Popen") as mock_popen,
            patch("time.sleep"),
        ):
            assert start_daemon_background() is True
            mock_popen.assert_called_once()

    def test_fails_to_start(self):
        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch("subprocess.Popen"),
            patch("time.sleep"),
        ):
            assert start_daemon_background() is False


class TestStopDaemon:
    def test_not_running(self):
        with patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None):
            assert stop_daemon() is False

    def test_stops_successfully(self):
        with (
            patch(
                "code_puppy.scheduler.daemon.get_daemon_pid",
                side_effect=[123, 123, None],
            ),
            patch("os.kill"),
            patch("time.sleep"),
        ):
            assert stop_daemon() is True

    def test_fails_to_stop(self):
        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("os.kill"),
            patch("time.sleep"),
        ):
            assert stop_daemon() is False

    def test_exception_during_stop(self):
        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("os.kill", side_effect=Exception("fail")),
            patch("time.sleep"),
        ):
            assert stop_daemon() is False


class TestStartDaemon:
    def test_start_daemon_foreground(self):
        import code_puppy.scheduler.daemon as daemon_mod

        daemon_mod._shutdown_requested = True  # Make loop exit immediately

        with (
            patch("code_puppy.scheduler.daemon.write_pid_file"),
            patch("code_puppy.scheduler.daemon.remove_pid_file"),
            patch("code_puppy.scheduler.daemon.run_scheduler_loop"),
            patch("atexit.register"),
            patch("signal.signal"),
        ):
            start_daemon(foreground=True)

        daemon_mod._shutdown_requested = False
