"""Tests for code_puppy/tools/scheduler_tools.py - 100% coverage."""

from unittest.mock import MagicMock, mock_open, patch


class FakeTask:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "task-1")
        self.name = kwargs.get("name", "Test Task")
        self.enabled = kwargs.get("enabled", True)
        self.last_status = kwargs.get("last_status", None)
        self.schedule_type = kwargs.get("schedule_type", "interval")
        self.schedule_value = kwargs.get("schedule_value", "1h")
        self.agent = kwargs.get("agent", "code-puppy")
        self.model = kwargs.get("model", "")
        self.prompt = kwargs.get("prompt", "Do something")
        self.working_directory = kwargs.get("working_directory", ".")
        self.last_run = kwargs.get("last_run", None)
        self.last_exit_code = kwargs.get("last_exit_code", 0)
        self.log_file = kwargs.get("log_file", "/tmp/task-1.log")


def _make_agent():
    agent = MagicMock()
    captured = {}

    def tool_plain(fn):
        captured["fn"] = fn

    agent.tool_plain = tool_plain
    return agent, captured


@patch("code_puppy.tools.scheduler_tools.generate_group_id", return_value="grp")
@patch("code_puppy.tools.scheduler_tools.emit_info")
class TestSchedulerListTasks:
    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None)
    @patch("code_puppy.scheduler.load_tasks", return_value=[])
    def test_no_tasks(self, mock_load, mock_pid, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_list_tasks

        agent, cap = _make_agent()
        register_scheduler_list_tasks(agent)
        result = cap["fn"]()
        assert "No scheduled tasks" in result

    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=1234)
    @patch("code_puppy.scheduler.load_tasks")
    def test_with_tasks(self, mock_load, mock_pid, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_list_tasks

        tasks = [
            FakeTask(last_status="success", last_run="2024-01-01T00:00:00Z"),
            FakeTask(id="task-2", name="Task 2", enabled=False, last_status="failed"),
            FakeTask(id="task-3", name="Task 3", last_status="running"),
            FakeTask(id="task-4", name="Task 4", last_status=None, prompt="x" * 200),
        ]
        mock_load.return_value = tasks
        agent, cap = _make_agent()
        register_scheduler_list_tasks(agent)
        result = cap["fn"]()
        assert "1234" in result
        assert "Task 2" in result
        assert "✅" in result
        assert "❌" in result
        assert "⏳" in result


@patch("code_puppy.tools.scheduler_tools.generate_group_id", return_value="grp")
@patch("code_puppy.tools.scheduler_tools.emit_info")
@patch("code_puppy.tools.scheduler_tools.emit_success")
class TestSchedulerCreateTask:
    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None)
    @patch("code_puppy.scheduler.add_task")
    def test_create_no_daemon(
        self, mock_add, mock_pid, mock_success, mock_emit, mock_grp
    ):
        from code_puppy.tools.scheduler_tools import register_scheduler_create_task

        agent, cap = _make_agent()
        register_scheduler_create_task(agent)
        result = cap["fn"](name="t", prompt="p")
        assert "Created" in result or "✅" in result
        assert "not running" in result

    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=42)
    @patch("code_puppy.scheduler.add_task")
    def test_create_with_daemon(
        self, mock_add, mock_pid, mock_success, mock_emit, mock_grp
    ):
        from code_puppy.tools.scheduler_tools import register_scheduler_create_task

        agent, cap = _make_agent()
        register_scheduler_create_task(agent)
        result = cap["fn"](name="t", prompt="p")
        assert "42" in result


@patch("code_puppy.tools.scheduler_tools.generate_group_id", return_value="grp")
@patch("code_puppy.tools.scheduler_tools.emit_info")
class TestSchedulerDeleteTask:
    @patch("code_puppy.scheduler.get_task", return_value=None)
    @patch("code_puppy.tools.scheduler_tools.emit_warning")
    def test_not_found(self, mock_warn, mock_get, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_delete_task

        agent, cap = _make_agent()
        register_scheduler_delete_task(agent)
        result = cap["fn"](task_id="bad")
        assert "not found" in result

    @patch("code_puppy.scheduler.delete_task", return_value=True)
    @patch("code_puppy.scheduler.get_task", return_value=FakeTask())
    @patch("code_puppy.tools.scheduler_tools.emit_success")
    def test_success(self, mock_succ, mock_get, mock_del, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_delete_task

        agent, cap = _make_agent()
        register_scheduler_delete_task(agent)
        result = cap["fn"](task_id="task-1")
        assert "Deleted" in result or "✅" in result

    @patch("code_puppy.scheduler.delete_task", return_value=False)
    @patch("code_puppy.scheduler.get_task", return_value=FakeTask())
    def test_fail(self, mock_get, mock_del, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_delete_task

        agent, cap = _make_agent()
        register_scheduler_delete_task(agent)
        result = cap["fn"](task_id="task-1")
        assert "Failed" in result or "❌" in result


@patch("code_puppy.tools.scheduler_tools.generate_group_id", return_value="grp")
@patch("code_puppy.tools.scheduler_tools.emit_info")
class TestSchedulerToggleTask:
    @patch("code_puppy.scheduler.get_task", return_value=None)
    @patch("code_puppy.tools.scheduler_tools.emit_warning")
    def test_not_found(self, mock_warn, mock_get, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_toggle_task

        agent, cap = _make_agent()
        register_scheduler_toggle_task(agent)
        result = cap["fn"](task_id="bad")
        assert "not found" in result

    @patch("code_puppy.scheduler.toggle_task", return_value=True)
    @patch("code_puppy.scheduler.get_task", return_value=FakeTask())
    @patch("code_puppy.tools.scheduler_tools.emit_success")
    def test_enable(self, mock_succ, mock_get, mock_toggle, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_toggle_task

        agent, cap = _make_agent()
        register_scheduler_toggle_task(agent)
        result = cap["fn"](task_id="task-1")
        assert "Enabled" in result

    @patch("code_puppy.scheduler.toggle_task", return_value=False)
    @patch("code_puppy.scheduler.get_task", return_value=FakeTask())
    @patch("code_puppy.tools.scheduler_tools.emit_success")
    def test_disable(self, mock_succ, mock_get, mock_toggle, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_toggle_task

        agent, cap = _make_agent()
        register_scheduler_toggle_task(agent)
        result = cap["fn"](task_id="task-1")
        assert "Disabled" in result

    @patch("code_puppy.scheduler.toggle_task", return_value=None)
    @patch("code_puppy.scheduler.get_task", return_value=FakeTask())
    def test_toggle_fail(self, mock_get, mock_toggle, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_toggle_task

        agent, cap = _make_agent()
        register_scheduler_toggle_task(agent)
        result = cap["fn"](task_id="task-1")
        assert "Failed" in result or "❌" in result


@patch("code_puppy.tools.scheduler_tools.generate_group_id", return_value="grp")
@patch("code_puppy.tools.scheduler_tools.emit_info")
class TestSchedulerDaemonStatus:
    @patch(
        "code_puppy.scheduler.load_tasks",
        return_value=[FakeTask(), FakeTask(enabled=False)],
    )
    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=99)
    def test_running(self, mock_pid, mock_tasks, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_daemon_status

        agent, cap = _make_agent()
        register_scheduler_daemon_status(agent)
        result = cap["fn"]()
        assert "RUNNING" in result
        assert "99" in result

    @patch("code_puppy.scheduler.load_tasks", return_value=[])
    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None)
    def test_stopped(self, mock_pid, mock_tasks, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_daemon_status

        agent, cap = _make_agent()
        register_scheduler_daemon_status(agent)
        result = cap["fn"]()
        assert "STOPPED" in result


@patch("code_puppy.tools.scheduler_tools.generate_group_id", return_value="grp")
@patch("code_puppy.tools.scheduler_tools.emit_info")
class TestSchedulerStartDaemon:
    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=55)
    @patch("code_puppy.tools.scheduler_tools.emit_warning")
    def test_already_running(self, mock_warn, mock_pid, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_start_daemon

        agent, cap = _make_agent()
        register_scheduler_start_daemon(agent)
        result = cap["fn"]()
        assert "already running" in result

    @patch("code_puppy.scheduler.daemon.get_daemon_pid", side_effect=[None, 77])
    @patch("code_puppy.scheduler.daemon.start_daemon_background", return_value=True)
    @patch("code_puppy.tools.scheduler_tools.emit_success")
    def test_start_success(self, mock_succ, mock_start, mock_pid, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_start_daemon

        agent, cap = _make_agent()
        register_scheduler_start_daemon(agent)
        result = cap["fn"]()
        assert "started" in result.lower()

    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None)
    @patch("code_puppy.scheduler.daemon.start_daemon_background", return_value=False)
    @patch("code_puppy.tools.scheduler_tools.emit_warning")
    def test_start_fail(self, mock_warn, mock_start, mock_pid, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_start_daemon

        agent, cap = _make_agent()
        register_scheduler_start_daemon(agent)
        result = cap["fn"]()
        assert "Failed" in result


@patch("code_puppy.tools.scheduler_tools.generate_group_id", return_value="grp")
@patch("code_puppy.tools.scheduler_tools.emit_info")
class TestSchedulerStopDaemon:
    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=None)
    @patch("code_puppy.tools.scheduler_tools.emit_warning")
    def test_not_running(self, mock_warn, mock_pid, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_stop_daemon

        agent, cap = _make_agent()
        register_scheduler_stop_daemon(agent)
        result = cap["fn"]()
        assert "not running" in result

    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=88)
    @patch("code_puppy.scheduler.daemon.stop_daemon", return_value=True)
    @patch("code_puppy.tools.scheduler_tools.emit_success")
    def test_stop_success(self, mock_succ, mock_stop, mock_pid, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_stop_daemon

        agent, cap = _make_agent()
        register_scheduler_stop_daemon(agent)
        result = cap["fn"]()
        assert "stopped" in result.lower()

    @patch("code_puppy.scheduler.daemon.get_daemon_pid", return_value=88)
    @patch("code_puppy.scheduler.daemon.stop_daemon", return_value=False)
    @patch("code_puppy.tools.scheduler_tools.emit_warning")
    def test_stop_fail(self, mock_warn, mock_stop, mock_pid, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_stop_daemon

        agent, cap = _make_agent()
        register_scheduler_stop_daemon(agent)
        result = cap["fn"]()
        assert "Failed" in result


@patch("code_puppy.tools.scheduler_tools.generate_group_id", return_value="grp")
@patch("code_puppy.tools.scheduler_tools.emit_info")
class TestSchedulerRunTask:
    @patch("code_puppy.scheduler.get_task", return_value=None)
    @patch("code_puppy.tools.scheduler_tools.emit_warning")
    def test_not_found(self, mock_warn, mock_get, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_run_task

        agent, cap = _make_agent()
        register_scheduler_run_task(agent)
        result = cap["fn"](task_id="bad")
        assert "not found" in result

    @patch("code_puppy.scheduler.executor.run_task_by_id", return_value=(True, "ok"))
    @patch("code_puppy.scheduler.get_task", return_value=FakeTask())
    @patch("code_puppy.tools.scheduler_tools.emit_success")
    def test_success(self, mock_succ, mock_get, mock_run, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_run_task

        agent, cap = _make_agent()
        register_scheduler_run_task(agent)
        result = cap["fn"](task_id="task-1")
        assert "completed" in result.lower()

    @patch("code_puppy.scheduler.executor.run_task_by_id", return_value=(False, "err"))
    @patch("code_puppy.scheduler.get_task", return_value=FakeTask())
    @patch("code_puppy.tools.scheduler_tools.emit_warning")
    def test_fail(self, mock_warn, mock_get, mock_run, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_run_task

        agent, cap = _make_agent()
        register_scheduler_run_task(agent)
        result = cap["fn"](task_id="task-1")
        assert "failed" in result.lower()


@patch("code_puppy.tools.scheduler_tools.generate_group_id", return_value="grp")
@patch("code_puppy.tools.scheduler_tools.emit_info")
class TestSchedulerViewLog:
    @patch("code_puppy.scheduler.get_task", return_value=None)
    @patch("code_puppy.tools.scheduler_tools.emit_warning")
    def test_not_found(self, mock_warn, mock_get, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_view_log

        agent, cap = _make_agent()
        register_scheduler_view_log(agent)
        result = cap["fn"](task_id="bad")
        assert "not found" in result

    @patch("os.path.exists", return_value=False)
    @patch("code_puppy.scheduler.get_task", return_value=FakeTask())
    def test_no_log_file(self, mock_get, mock_exists, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_view_log

        agent, cap = _make_agent()
        register_scheduler_view_log(agent)
        result = cap["fn"](task_id="task-1")
        assert "No log file" in result

    @patch("builtins.open", mock_open(read_data="line1\nline2\nline3\n"))
    @patch("os.path.exists", return_value=True)
    @patch("code_puppy.scheduler.get_task", return_value=FakeTask())
    def test_read_log(self, mock_get, mock_exists, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_view_log

        agent, cap = _make_agent()
        register_scheduler_view_log(agent)
        result = cap["fn"](task_id="task-1", lines=2)
        assert "line" in result.lower()

    @patch("builtins.open", side_effect=IOError("fail"))
    @patch("os.path.exists", return_value=True)
    @patch("code_puppy.scheduler.get_task", return_value=FakeTask())
    def test_read_error(self, mock_get, mock_exists, mock_open, mock_emit, mock_grp):
        from code_puppy.tools.scheduler_tools import register_scheduler_view_log

        agent, cap = _make_agent()
        register_scheduler_view_log(agent)
        result = cap["fn"](task_id="task-1")
        assert "Error" in result
