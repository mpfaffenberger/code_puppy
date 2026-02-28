"""Full coverage tests for tools/scheduler_tools.py."""

from unittest.mock import MagicMock, patch

from code_puppy.scheduler.config import ScheduledTask


def _make_task(**kwargs):
    defaults = dict(
        name="Test",
        prompt="do stuff",
        schedule_type="interval",
        schedule_value="1h",
        agent="code-puppy",
        model="",
        working_directory=".",
        enabled=True,
        last_run="2024-01-01T00:00:00",
        last_status="success",
        last_exit_code=0,
    )
    defaults.update(kwargs)
    return ScheduledTask(**defaults)


def _capture(register_func):
    """Register tool and return the captured inner function."""
    agent = MagicMock()
    captured = {}

    def tp(fn):
        captured["fn"] = fn
        return fn

    agent.tool_plain = tp
    register_func(agent)
    return captured["fn"]


class TestSchedulerListTasks:
    def test_with_tasks(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_list_tasks

        fn = _capture(register_scheduler_list_tasks)
        task = _make_task()
        with (
            patch("code_puppy.scheduler.load_tasks", return_value=[task]),
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn()
            assert "Running" in result
            assert "Test" in result

    def test_with_tasks_various_statuses(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_list_tasks

        fn = _capture(register_scheduler_list_tasks)
        tasks = [
            _make_task(name="ok", last_status="success"),
            _make_task(name="fail", last_status="failed"),
            _make_task(name="run", last_status="running"),
            _make_task(name="off", enabled=False),
        ]
        with (
            patch("code_puppy.scheduler.load_tasks", return_value=tasks),
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn()
            assert "Stopped" in result

    def test_no_tasks(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_list_tasks

        fn = _capture(register_scheduler_list_tasks)
        with (
            patch("code_puppy.scheduler.load_tasks", return_value=[]),
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn()
            assert "No scheduled tasks" in result

    def test_long_prompt(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_list_tasks

        fn = _capture(register_scheduler_list_tasks)
        task = _make_task(prompt="x" * 200)
        with (
            patch("code_puppy.scheduler.load_tasks", return_value=[task]),
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn()
            assert "..." in result


class TestSchedulerCreateTask:
    def test_create_task(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_create_task

        fn = _capture(register_scheduler_create_task)
        with (
            patch("code_puppy.scheduler.add_task"),
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_success"),
        ):
            result = fn(name="t", prompt="p")
            assert "Created" in result
            assert "not running" in result

    def test_create_task_daemon_running(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_create_task

        fn = _capture(register_scheduler_create_task)
        with (
            patch("code_puppy.scheduler.add_task"),
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_success"),
        ):
            result = fn(name="t", prompt="p")
            assert "running" in result.lower()


class TestSchedulerDeleteTask:
    def test_delete_found(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_delete_task

        fn = _capture(register_scheduler_delete_task)
        task = _make_task()
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch("code_puppy.scheduler.delete_task", return_value=True),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_success"),
        ):
            result = fn(task_id="t1")
            assert "Deleted" in result

    def test_delete_not_found(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_delete_task

        fn = _capture(register_scheduler_delete_task)
        with (
            patch("code_puppy.scheduler.get_task", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_warning"),
        ):
            result = fn(task_id="nope")
            assert "not found" in result

    def test_delete_fails(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_delete_task

        fn = _capture(register_scheduler_delete_task)
        task = _make_task()
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch("code_puppy.scheduler.delete_task", return_value=False),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn(task_id="t1")
            assert "Failed" in result


class TestSchedulerToggleTask:
    def test_toggle_enable(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_toggle_task

        fn = _capture(register_scheduler_toggle_task)
        task = _make_task()
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch("code_puppy.scheduler.toggle_task", return_value=True),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_success"),
        ):
            result = fn(task_id="t1")
            assert "Enabled" in result

    def test_toggle_disable(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_toggle_task

        fn = _capture(register_scheduler_toggle_task)
        task = _make_task()
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch("code_puppy.scheduler.toggle_task", return_value=False),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_success"),
        ):
            result = fn(task_id="t1")
            assert "Disabled" in result

    def test_toggle_not_found(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_toggle_task

        fn = _capture(register_scheduler_toggle_task)
        with (
            patch("code_puppy.scheduler.get_task", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_warning"),
        ):
            result = fn(task_id="nope")
            assert "not found" in result

    def test_toggle_fails(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_toggle_task

        fn = _capture(register_scheduler_toggle_task)
        task = _make_task()
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch("code_puppy.scheduler.toggle_task", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn(task_id="t1")
            assert "Failed" in result


class TestSchedulerDaemonStatus:
    def test_running(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_daemon_status

        fn = _capture(register_scheduler_daemon_status)
        with (
            patch("code_puppy.scheduler.load_tasks", return_value=[_make_task()]),
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn()
            assert "RUNNING" in result

    def test_stopped(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_daemon_status

        fn = _capture(register_scheduler_daemon_status)
        with (
            patch("code_puppy.scheduler.load_tasks", return_value=[]),
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn()
            assert "STOPPED" in result


class TestSchedulerStartDaemon:
    def test_already_running(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_start_daemon

        fn = _capture(register_scheduler_start_daemon)
        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_warning"),
        ):
            result = fn()
            assert "already running" in result

    def test_start_success(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_start_daemon

        fn = _capture(register_scheduler_start_daemon)
        with (
            patch(
                "code_puppy.scheduler.daemon.get_daemon_pid", side_effect=[None, 456]
            ),
            patch(
                "code_puppy.scheduler.daemon.start_daemon_background", return_value=True
            ),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_success"),
        ):
            result = fn()
            assert "started" in result

    def test_start_failure(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_start_daemon

        fn = _capture(register_scheduler_start_daemon)
        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch(
                "code_puppy.scheduler.daemon.start_daemon_background",
                return_value=False,
            ),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_warning"),
        ):
            result = fn()
            assert "Failed" in result


class TestSchedulerStopDaemon:
    def test_not_running(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_stop_daemon

        fn = _capture(register_scheduler_stop_daemon)
        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_warning"),
        ):
            result = fn()
            assert "not running" in result

    def test_stop_success(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_stop_daemon

        fn = _capture(register_scheduler_stop_daemon)
        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("code_puppy.scheduler.daemon.stop_daemon", return_value=True),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_success"),
        ):
            result = fn()
            assert "stopped" in result

    def test_stop_failure(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_stop_daemon

        fn = _capture(register_scheduler_stop_daemon)
        with (
            patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=123),
            patch("code_puppy.scheduler.daemon.stop_daemon", return_value=False),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_warning"),
        ):
            result = fn()
            assert "Failed" in result


class TestSchedulerRunTask:
    def test_run_success(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_run_task

        fn = _capture(register_scheduler_run_task)
        task = _make_task()
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch(
                "code_puppy.scheduler.executor.run_task_by_id",
                return_value=(True, "done"),
            ),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_success"),
        ):
            result = fn(task_id="t1")
            assert "completed" in result

    def test_run_failure(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_run_task

        fn = _capture(register_scheduler_run_task)
        task = _make_task()
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch(
                "code_puppy.scheduler.executor.run_task_by_id",
                return_value=(False, "error"),
            ),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_warning"),
        ):
            result = fn(task_id="t1")
            assert "failed" in result

    def test_run_not_found(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_run_task

        fn = _capture(register_scheduler_run_task)
        with (
            patch("code_puppy.scheduler.get_task", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_warning"),
        ):
            result = fn(task_id="nope")
            assert "not found" in result


class TestSchedulerViewLog:
    def test_view_log_success(self, tmp_path):
        from code_puppy.tools.scheduler_tools import register_scheduler_view_log

        fn = _capture(register_scheduler_view_log)
        log = tmp_path / "log.txt"
        log.write_text("line1\nline2\nline3")
        task = _make_task()
        task.log_file = str(log)
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn(task_id="t1", lines=50)
            assert "line1" in result

    def test_view_log_not_found(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_view_log

        fn = _capture(register_scheduler_view_log)
        with (
            patch("code_puppy.scheduler.get_task", return_value=None),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("code_puppy.tools.scheduler_tools.emit_warning"),
        ):
            result = fn(task_id="nope")
            assert "not found" in result

    def test_view_log_no_file(self):
        from code_puppy.tools.scheduler_tools import register_scheduler_view_log

        fn = _capture(register_scheduler_view_log)
        task = _make_task()
        task.log_file = "/nonexistent/log.txt"
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn(task_id="t1")
            assert "No log file" in result

    def test_view_log_read_error(self, tmp_path):
        from code_puppy.tools.scheduler_tools import register_scheduler_view_log

        fn = _capture(register_scheduler_view_log)
        log = tmp_path / "log.txt"
        log.write_text("data")
        task = _make_task()
        task.log_file = str(log)
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
            patch("builtins.open", side_effect=PermissionError("denied")),
        ):
            result = fn(task_id="t1")
            assert "Error" in result

    def test_view_log_truncated(self, tmp_path):
        from code_puppy.tools.scheduler_tools import register_scheduler_view_log

        fn = _capture(register_scheduler_view_log)
        log = tmp_path / "log.txt"
        log.write_text("\n".join(f"line{i}" for i in range(100)))
        task = _make_task()
        task.log_file = str(log)
        with (
            patch("code_puppy.scheduler.get_task", return_value=task),
            patch("code_puppy.tools.scheduler_tools.emit_info"),
        ):
            result = fn(task_id="t1", lines=5)
            assert "last 5" in result
