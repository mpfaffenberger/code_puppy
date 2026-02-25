"""Tests for code_puppy/plugins/scheduler/scheduler_menu.py"""

from unittest.mock import MagicMock, patch

_MOD = "code_puppy.plugins.scheduler.scheduler_menu"


def _make_task(**kwargs):
    from code_puppy.scheduler.config import ScheduledTask

    defaults = dict(
        id="t1",
        name="Test Task",
        prompt="do stuff",
        agent="code-puppy",
        model="gpt-4",
        schedule_type="interval",
        schedule_value="1h",
        working_directory=".",
        enabled=True,
        last_status=None,
        last_run=None,
        last_exit_code=None,
        log_file="/tmp/t1.log",
    )
    defaults.update(kwargs)
    return ScheduledTask(**defaults)


# ---------------------------------------------------------------------------
# SchedulerMenu unit tests
# ---------------------------------------------------------------------------


class TestSchedulerMenuInit:
    @patch(f"{_MOD}.load_tasks", return_value=[])
    def test_init_empty(self, mock_load):
        from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

        menu = SchedulerMenu()
        assert menu.tasks == []

    @patch(f"{_MOD}.load_tasks", side_effect=RuntimeError("boom"))
    def test_init_error(self, mock_load):
        from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

        menu = SchedulerMenu()
        assert menu.tasks == []

    @patch(f"{_MOD}.load_tasks", return_value=[_make_task()])
    def test_get_current_task(self, mock_load):
        from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

        menu = SchedulerMenu()
        assert menu._get_current_task() is not None
        menu.selected_idx = 99
        assert menu._get_current_task() is None


class TestSchedulerMenuStatusIcon:
    @patch(f"{_MOD}.load_tasks", return_value=[])
    def test_disabled(self, mock_load):
        from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

        menu = SchedulerMenu()
        task = _make_task(enabled=False)
        icon, color = menu._get_status_icon(task)
        assert icon == "⏸"

    @patch(f"{_MOD}.load_tasks", return_value=[])
    def test_running(self, mock_load):
        from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

        menu = SchedulerMenu()
        icon, _ = menu._get_status_icon(_make_task(last_status="running"))
        assert icon == "\u23f3"

    @patch(f"{_MOD}.load_tasks", return_value=[])
    def test_success(self, mock_load):
        from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

        menu = SchedulerMenu()
        icon, _ = menu._get_status_icon(_make_task(last_status="success"))
        assert icon == "✓"

    @patch(f"{_MOD}.load_tasks", return_value=[])
    def test_failed(self, mock_load):
        from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

        menu = SchedulerMenu()
        icon, _ = menu._get_status_icon(_make_task(last_status="failed"))
        assert icon == "✗"

    @patch(f"{_MOD}.load_tasks", return_value=[])
    def test_default(self, mock_load):
        from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

        menu = SchedulerMenu()
        icon, _ = menu._get_status_icon(_make_task(last_status=None))
        assert icon == "○"


class TestSchedulerMenuRendering:
    def _make_menu(self, tasks=None):
        with patch(f"{_MOD}.load_tasks", return_value=tasks or []):
            from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

            return SchedulerMenu()

    @patch(f"{_MOD}.get_daemon_pid", return_value=None)
    def test_render_empty(self, mock_pid):
        menu = self._make_menu()
        lines = menu._render_task_list()
        text = "".join(t for _, t in lines)
        assert "No scheduled tasks" in text
        assert "STOPPED" in text

    @patch(f"{_MOD}.get_daemon_pid", return_value=1234)
    def test_render_with_tasks(self, mock_pid):
        menu = self._make_menu(tasks=[_make_task()])
        lines = menu._render_task_list()
        text = "".join(t for _, t in lines)
        assert "RUNNING" in text
        assert "Test Task" in text

    @patch(f"{_MOD}.get_daemon_pid", return_value=None)
    def test_render_pagination(self, mock_pid):
        tasks = [_make_task(id=f"t{i}", name=f"Task {i}") for i in range(20)]
        menu = self._make_menu(tasks=tasks)
        lines = menu._render_task_list()
        text = "".join(t for _, t in lines)
        assert "Page 1/" in text

    def test_render_details_no_task(self):
        menu = self._make_menu()
        lines = menu._render_task_details()
        text = "".join(t for _, t in lines)
        assert "No task selected" in text

    def test_render_details_with_task(self):
        task = _make_task(
            last_run="2024-01-01T00:00:00",
            last_exit_code=0,
            last_status="success",
        )
        menu = self._make_menu(tasks=[task])
        lines = menu._render_task_details()
        text = "".join(t for _, t in lines)
        assert "Test Task" in text
        assert "Enabled" in text
        assert "Last Run" in text

    def test_render_details_with_model(self):
        menu = self._make_menu(tasks=[_make_task(model="gpt-4")])
        lines = menu._render_task_details()
        text = "".join(t for _, t in lines)
        assert "gpt-4" in text

    def test_render_details_no_model(self):
        menu = self._make_menu(tasks=[_make_task(model="")])
        lines = menu._render_task_details()
        text = "".join(t for _, t in lines)
        assert "TASK DETAILS" in text

    def test_render_details_long_prompt(self):
        menu = self._make_menu(tasks=[_make_task(prompt="x" * 200)])
        lines = menu._render_task_details()
        text = "".join(t for _, t in lines)
        assert "..." in text

    def test_render_details_long_log(self):
        menu = self._make_menu(tasks=[_make_task(log_file="/very/long/" + "x" * 50)])
        lines = menu._render_task_details()
        text = "".join(t for _, t in lines)
        assert "..." in text

    def test_render_details_failed_exit_code(self):
        task = _make_task(last_run="2024-01-01T00:00:00", last_exit_code=1)
        menu = self._make_menu(tasks=[task])
        lines = menu._render_task_details()
        text = "".join(t for _, t in lines)
        assert "1" in text

    def test_update_display(self):
        menu = self._make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.update_display()

    def test_update_display_no_controls(self):
        menu = self._make_menu()
        menu.update_display()  # no crash


def _invoke_kb_handler(kb, key_name, app_mock=None):
    _ALIASES = {
        "enter": "c-m",
        "up": "up",
        "down": "down",
        "left": "left",
        "right": "right",
        "escape": "escape",
        "space": " ",
        "backspace": "c-h",
    }
    target = _ALIASES.get(key_name, key_name)
    event = MagicMock()
    event.app = app_mock or MagicMock()
    for binding in kb.bindings:
        for k in binding.keys:
            name = k.value if hasattr(k, "value") else str(k)
            if name == target or name == key_name:
                binding.handler(event)
                return event
    raise ValueError(f"No handler found for key: {key_name}")


class TestSchedulerMenuKeyBindings:
    def _run_with_keys(self, tasks=None, callback=None):
        from prompt_toolkit.key_binding import KeyBindings as OrigKB

        captured_kb = [None]

        class CapturingKB(OrigKB):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                captured_kb[0] = self

        with (
            patch(f"{_MOD}.load_tasks", return_value=tasks or []),
            patch(f"{_MOD}.set_awaiting_user_input"),
            patch(f"{_MOD}.KeyBindings", CapturingKB),
            patch(f"{_MOD}.Application") as mock_app_cls,
            patch(f"{_MOD}.time"),
            patch("sys.stdout"),
        ):
            from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

            menu = SchedulerMenu()
            mock_app = MagicMock()

            def fake_run(**kwargs):
                if callback:
                    callback(menu, captured_kb[0], mock_app)

            mock_app.run.side_effect = fake_run
            mock_app_cls.return_value = mock_app
            result = menu.run()
            return menu, result

    @patch(f"{_MOD}.toggle_task")
    def test_navigation_and_actions(self, mock_toggle):
        tasks = [_make_task(id=f"t{i}", name=f"Task {i}") for i in range(20)]

        def exercise(menu, kb, app):
            # Down
            _invoke_kb_handler(kb, "down", app)
            assert menu.selected_idx == 1
            _invoke_kb_handler(kb, "j", app)
            assert menu.selected_idx == 2
            # Up
            _invoke_kb_handler(kb, "up", app)
            assert menu.selected_idx == 1
            _invoke_kb_handler(kb, "k", app)
            assert menu.selected_idx == 0
            # Up at top
            _invoke_kb_handler(kb, "up", app)
            assert menu.selected_idx == 0
            # Page right
            _invoke_kb_handler(kb, "right", app)
            assert menu.current_page == 1
            # Page left
            _invoke_kb_handler(kb, "left", app)
            assert menu.current_page == 0
            # Left at start
            _invoke_kb_handler(kb, "left", app)
            assert menu.current_page == 0
            # Space (toggle)
            _invoke_kb_handler(kb, "space", app)
            assert menu.result == "changed"
            # n (new task)
            _invoke_kb_handler(kb, "n", app)
            assert menu.result == "new_task"
            # r (run task)
            _invoke_kb_handler(kb, "r", app)
            assert menu.result == "run_task"
            # t (tail log)
            _invoke_kb_handler(kb, "t", app)
            assert menu.result == "tail_log"
            # d (delete)
            _invoke_kb_handler(kb, "d", app)
            assert menu.result == "delete_task"
            # s (toggle daemon)
            _invoke_kb_handler(kb, "s", app)
            assert menu.result == "toggle_daemon"
            # q (quit)
            _invoke_kb_handler(kb, "q", app)
            assert menu.result == "quit"
            # escape
            menu.result = None
            _invoke_kb_handler(kb, "escape", app)
            assert menu.result == "quit"
            # Ctrl+C
            menu.result = None
            _invoke_kb_handler(kb, "c-c", app)
            assert menu.result == "quit"

        self._run_with_keys(tasks=tasks, callback=exercise)

    def test_down_at_bottom(self):
        tasks = [_make_task()]

        def exercise(menu, kb, app):
            _invoke_kb_handler(kb, "down", app)
            assert menu.selected_idx == 0
            _invoke_kb_handler(kb, "right", app)
            assert menu.current_page == 0

        self._run_with_keys(tasks=tasks, callback=exercise)

    def test_space_no_task(self):
        def exercise(menu, kb, app):
            _invoke_kb_handler(kb, "space", app)
            # No task, result should not be "changed"

        self._run_with_keys(tasks=[], callback=exercise)


class TestSchedulerMenuRun:
    @patch(f"{_MOD}.set_awaiting_user_input")
    @patch(f"{_MOD}.Application")
    @patch(f"{_MOD}.time")
    @patch("sys.stdout")
    @patch(f"{_MOD}.load_tasks", return_value=[])
    def test_run_quit(
        self, mock_load, mock_stdout, mock_time, mock_app_cls, mock_await
    ):
        from code_puppy.plugins.scheduler.scheduler_menu import SchedulerMenu

        menu = SchedulerMenu()
        mock_app = MagicMock()

        def fake_run(**kw):
            menu.result = "quit"

        mock_app.run.side_effect = fake_run
        mock_app_cls.return_value = mock_app
        result = menu.run()
        assert result == "quit"


# ---------------------------------------------------------------------------
# show_scheduler_menu
# ---------------------------------------------------------------------------


class TestShowSchedulerMenu:
    @patch(f"{_MOD}.SchedulerMenu")
    def test_quit(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.return_value = "quit"
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        assert show_scheduler_menu() is False

    @patch(f"{_MOD}.SchedulerMenu")
    def test_none_result(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.return_value = None
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        assert show_scheduler_menu() is False

    @patch(f"{_MOD}.add_task")
    @patch(f"{_MOD}._create_new_task")
    @patch(f"{_MOD}.SchedulerMenu")
    def test_new_task(self, mock_cls, mock_create, mock_add):
        mock_create.return_value = _make_task()
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["new_task", "quit"]
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        result = show_scheduler_menu()
        assert result is True

    @patch(f"{_MOD}._create_new_task", return_value=None)
    @patch(f"{_MOD}.SchedulerMenu")
    def test_new_task_cancelled(self, mock_cls, mock_create):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["new_task", "quit"]
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        assert show_scheduler_menu() is False

    @patch(f"{_MOD}.run_task_by_id", return_value=(True, "ok"))
    @patch("code_puppy.command_line.utils.safe_input", return_value="")
    @patch(f"{_MOD}.SchedulerMenu")
    def test_run_task_success(self, mock_cls, mock_input, mock_run):
        task = _make_task()
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["run_task", "quit"]
        mock_menu._get_current_task.return_value = task
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        assert show_scheduler_menu() is True

    @patch(f"{_MOD}.run_task_by_id", return_value=(False, "fail"))
    @patch("code_puppy.command_line.utils.safe_input", return_value="")
    @patch(f"{_MOD}.SchedulerMenu")
    def test_run_task_failure(self, mock_cls, mock_input, mock_run):
        task = _make_task()
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["run_task", "quit"]
        mock_menu._get_current_task.return_value = task
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        assert show_scheduler_menu() is True

    @patch(f"{_MOD}.SchedulerMenu")
    def test_run_task_no_task(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["run_task", "quit"]
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        show_scheduler_menu()

    @patch(f"{_MOD}._tail_log_file")
    @patch(f"{_MOD}.SchedulerMenu")
    def test_tail_log(self, mock_cls, mock_tail):
        task = _make_task()
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["tail_log", "quit"]
        mock_menu._get_current_task.return_value = task
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        show_scheduler_menu()
        mock_tail.assert_called_once()

    @patch(f"{_MOD}.SchedulerMenu")
    def test_tail_log_no_task(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["tail_log", "quit"]
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        show_scheduler_menu()

    @patch(f"{_MOD}.SchedulerMenu")
    def test_tail_log_no_log_file(self, mock_cls):
        # Task with falsy log_file (manually override post_init)
        task = _make_task()
        task.log_file = ""  # override post_init
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["tail_log", "quit"]
        mock_menu._get_current_task.return_value = task
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        show_scheduler_menu()

    @patch(f"{_MOD}.delete_task")
    @patch("code_puppy.command_line.utils.safe_input", return_value="y")
    @patch(f"{_MOD}.SchedulerMenu")
    def test_delete_task(self, mock_cls, mock_input, mock_delete):
        task = _make_task()
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["delete_task", "quit"]
        mock_menu._get_current_task.return_value = task
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        assert show_scheduler_menu() is True

    @patch("code_puppy.command_line.utils.safe_input", return_value="n")
    @patch(f"{_MOD}.SchedulerMenu")
    def test_delete_task_cancelled(self, mock_cls, mock_input):
        task = _make_task()
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["delete_task", "quit"]
        mock_menu._get_current_task.return_value = task
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        assert show_scheduler_menu() is False

    @patch(f"{_MOD}.SchedulerMenu")
    def test_delete_task_no_task(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["delete_task", "quit"]
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        show_scheduler_menu()

    @patch(f"{_MOD}.start_daemon_background", return_value=True)
    @patch(f"{_MOD}.get_daemon_pid", return_value=None)
    @patch("code_puppy.command_line.utils.safe_input", return_value="")
    @patch(f"{_MOD}.SchedulerMenu")
    def test_toggle_daemon_start(self, mock_cls, mock_input, mock_pid, mock_start):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["toggle_daemon", "quit"]
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        show_scheduler_menu()
        mock_start.assert_called_once()

    @patch(f"{_MOD}.stop_daemon", return_value=True)
    @patch(f"{_MOD}.get_daemon_pid", return_value=1234)
    @patch("code_puppy.command_line.utils.safe_input", return_value="")
    @patch(f"{_MOD}.SchedulerMenu")
    def test_toggle_daemon_stop(self, mock_cls, mock_input, mock_pid, mock_stop):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["toggle_daemon", "quit"]
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        show_scheduler_menu()
        mock_stop.assert_called_once()

    @patch(f"{_MOD}.start_daemon_background", return_value=False)
    @patch(f"{_MOD}.get_daemon_pid", return_value=None)
    @patch("code_puppy.command_line.utils.safe_input", return_value="")
    @patch(f"{_MOD}.SchedulerMenu")
    def test_toggle_daemon_start_fail(self, mock_cls, mock_input, mock_pid, mock_start):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["toggle_daemon", "quit"]
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        show_scheduler_menu()

    @patch(f"{_MOD}.stop_daemon", return_value=False)
    @patch(f"{_MOD}.get_daemon_pid", return_value=1234)
    @patch("code_puppy.command_line.utils.safe_input", return_value="")
    @patch(f"{_MOD}.SchedulerMenu")
    def test_toggle_daemon_stop_fail(self, mock_cls, mock_input, mock_pid, mock_stop):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["toggle_daemon", "quit"]
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        show_scheduler_menu()

    @patch(f"{_MOD}.SchedulerMenu")
    def test_changed_result(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["changed", "quit"]
        mock_menu._get_current_task.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu

        assert show_scheduler_menu() is True


# ---------------------------------------------------------------------------
# _create_new_task
# ---------------------------------------------------------------------------


class TestCreateNewTask:
    @patch(
        "code_puppy.plugins.scheduler.scheduler_wizard.create_task_wizard",
        return_value=None,
    )
    def test_cancelled(self, mock_wizard):
        from code_puppy.plugins.scheduler.scheduler_menu import _create_new_task

        assert _create_new_task() is None

    @patch("code_puppy.plugins.scheduler.scheduler_wizard.create_task_wizard")
    def test_success(self, mock_wizard):
        mock_wizard.return_value = {
            "name": "Test",
            "prompt": "do stuff",
            "agent": "code-puppy",
            "model": "",
            "schedule_type": "interval",
            "schedule_value": "1h",
            "working_directory": ".",
        }
        from code_puppy.plugins.scheduler.scheduler_menu import _create_new_task

        task = _create_new_task()
        assert task is not None
        assert task.name == "Test"


# ---------------------------------------------------------------------------
# _tail_log_file
# ---------------------------------------------------------------------------


class TestTailLogFile:
    @patch("code_puppy.command_line.utils.safe_input", return_value="")
    def test_file_not_found(self, mock_input):
        from code_puppy.plugins.scheduler.scheduler_menu import _tail_log_file

        _tail_log_file("/nonexistent/file.log")

    def test_reads_file(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text("line1\nline2\n")

        from prompt_toolkit.key_binding import KeyBindings as OrigKB
        from prompt_toolkit.layout.controls import FormattedTextControl

        captured_kb = [None]
        captured_render = [None]

        class CapturingKB(OrigKB):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                captured_kb[0] = self

        orig_ftc = FormattedTextControl.__init__

        def capturing_ftc(self_ctrl, *a, **kw):
            orig_ftc(self_ctrl, *a, **kw)
            if "text" in kw and callable(kw["text"]):
                captured_render[0] = kw["text"]

        with (
            patch("prompt_toolkit.application.Application") as mock_app_cls,
            patch(f"{_MOD}.set_awaiting_user_input"),
            patch("prompt_toolkit.key_binding.KeyBindings", CapturingKB),
        ):
            mock_app = MagicMock()

            # Capture FormattedTextControl to call render_log
            original_ftc_init = FormattedTextControl.__init__
            render_funcs = []

            def patched_ftc_init(self_ctrl, *a, **kw):
                original_ftc_init(self_ctrl, *a, **kw)
                text_arg = kw.get("text") or (a[0] if a else None)
                if callable(text_arg):
                    render_funcs.append(text_arg)

            def fake_run(**kw):
                # Exercise key binding
                if captured_kb[0]:
                    event = MagicMock()
                    for binding in captured_kb[0].bindings:
                        binding.handler(event)
                        break
                # Call render_log if captured
                for fn in render_funcs:
                    try:
                        fn()
                    except Exception:
                        pass

            mock_app.run.side_effect = fake_run
            mock_app_cls.return_value = mock_app

            from prompt_toolkit.layout.controls import FormattedTextControl

            with patch.object(FormattedTextControl, "__init__", patched_ftc_init):
                from code_puppy.plugins.scheduler.scheduler_menu import _tail_log_file

                _tail_log_file(str(log))

    @patch("code_puppy.command_line.utils.safe_input", return_value="")
    def test_read_error(self, mock_input, tmp_path):
        log = tmp_path / "test.log"
        log.write_text("data")
        # Make unreadable
        log.chmod(0o000)
        from code_puppy.plugins.scheduler.scheduler_menu import _tail_log_file

        try:
            _tail_log_file(str(log))
        finally:
            log.chmod(0o644)

    def test_large_file(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text("\n".join(f"line {i}" for i in range(300)))
        with (
            patch("prompt_toolkit.application.Application") as mock_app_cls,
            patch(f"{_MOD}.set_awaiting_user_input"),
        ):
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            from code_puppy.plugins.scheduler.scheduler_menu import _tail_log_file

            _tail_log_file(str(log))
