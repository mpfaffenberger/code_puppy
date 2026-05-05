"""Full coverage tests for scheduler/cli.py."""

from unittest.mock import patch

from code_puppy.scheduler.config import ScheduledTask


class TestHandleSchedulerStart:
    def test_already_running(self):
        from code_puppy.scheduler.cli import handle_scheduler_start

        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("code_puppy.scheduler.cli.emit_warning"),
        ):
            assert handle_scheduler_start() is True

    def test_starts_successfully(self):
        from code_puppy.scheduler.cli import handle_scheduler_start

        with (
            patch(
                "code_puppy.scheduler.daemon.get_daemon_pid", side_effect=[None, 456]
            ),
            patch(
                "code_puppy.scheduler.daemon.start_daemon_background", return_value=True
            ),
            patch("code_puppy.scheduler.cli.emit_info"),
            patch("code_puppy.scheduler.cli.emit_success"),
        ):
            assert handle_scheduler_start() is True

    def test_fails_to_start(self):
        from code_puppy.scheduler.cli import handle_scheduler_start

        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch(
                "code_puppy.scheduler.daemon.start_daemon_background",
                return_value=False,
            ),
            patch("code_puppy.scheduler.cli.emit_info"),
            patch("code_puppy.scheduler.cli.emit_error"),
        ):
            assert handle_scheduler_start() is False


class TestHandleSchedulerStop:
    def test_not_running(self):
        from code_puppy.scheduler.cli import handle_scheduler_stop

        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch("code_puppy.scheduler.cli.emit_info"),
        ):
            assert handle_scheduler_stop() is True

    def test_stops_successfully(self):
        from code_puppy.scheduler.cli import handle_scheduler_stop

        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("code_puppy.scheduler.daemon.stop_daemon", return_value=True),
            patch("code_puppy.scheduler.cli.emit_info"),
            patch("code_puppy.scheduler.cli.emit_success"),
        ):
            assert handle_scheduler_stop() is True

    def test_fails_to_stop(self):
        from code_puppy.scheduler.cli import handle_scheduler_stop

        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("code_puppy.scheduler.daemon.stop_daemon", return_value=False),
            patch("code_puppy.scheduler.cli.emit_info"),
            patch("code_puppy.scheduler.cli.emit_error"),
        ):
            assert handle_scheduler_stop() is False


class TestHandleSchedulerStatus:
    def test_running_with_tasks(self):
        from code_puppy.scheduler.cli import handle_scheduler_status

        task = ScheduledTask(
            name="t",
            prompt="p",
            schedule_type="interval",
            schedule_value="1h",
            last_run="2024-01-01T00:00:00",
            last_status="success",
        )
        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("code_puppy.scheduler.config.load_tasks", return_value=[task]),
            patch("code_puppy.scheduler.cli.emit_success"),
            patch("code_puppy.scheduler.cli.emit_info"),
        ):
            assert handle_scheduler_status() is True

    def test_stopped_no_tasks(self):
        from code_puppy.scheduler.cli import handle_scheduler_status

        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch("code_puppy.scheduler.config.load_tasks", return_value=[]),
            patch("code_puppy.scheduler.cli.emit_warning"),
            patch("code_puppy.scheduler.cli.emit_info"),
        ):
            assert handle_scheduler_status() is True


class TestHandleSchedulerList:
    def test_no_tasks(self):
        from code_puppy.scheduler.cli import handle_scheduler_list

        with (
            patch("code_puppy.scheduler.config.load_tasks", return_value=[]),
            patch("code_puppy.scheduler.cli.emit_info"),
        ):
            assert handle_scheduler_list() is True

    def test_with_tasks(self):
        from code_puppy.scheduler.cli import handle_scheduler_list

        task = ScheduledTask(
            name="t",
            prompt="p",
            schedule_type="interval",
            schedule_value="1h",
            last_run="2024-01-01T00:00:00",
            last_status="success",
        )
        with (
            patch("code_puppy.scheduler.config.load_tasks", return_value=[task]),
            patch("code_puppy.scheduler.cli.emit_info"),
        ):
            assert handle_scheduler_list() is True


class TestHandleSchedulerRun:
    def test_success(self):
        from code_puppy.scheduler.cli import handle_scheduler_run

        with (
            patch(
                "code_puppy.scheduler.executor.run_task_by_id",
                return_value=(True, "ok"),
            ),
            patch("code_puppy.scheduler.cli.emit_info"),
            patch("code_puppy.scheduler.cli.emit_success"),
        ):
            assert handle_scheduler_run("task-1") is True

    def test_failure(self):
        from code_puppy.scheduler.cli import handle_scheduler_run

        with (
            patch(
                "code_puppy.scheduler.executor.run_task_by_id",
                return_value=(False, "fail"),
            ),
            patch("code_puppy.scheduler.cli.emit_info"),
            patch("code_puppy.scheduler.cli.emit_error"),
        ):
            assert handle_scheduler_run("task-1") is False
