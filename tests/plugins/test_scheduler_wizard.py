"""Tests for code_puppy/plugins/scheduler/scheduler_wizard.py"""

from unittest.mock import MagicMock, patch

import pytest

_MOD = "code_puppy.plugins.scheduler.scheduler_wizard"


# ---------------------------------------------------------------------------
# SelectionMenu
# ---------------------------------------------------------------------------


class TestSelectionMenu:
    def test_render(self):
        from code_puppy.plugins.scheduler.scheduler_wizard import SelectionMenu

        menu = SelectionMenu("Pick one", ["A", "B"], ["desc a", "desc b"])
        lines = menu._render()
        text = "".join(t for _, t in lines)
        assert "Pick one" in text
        assert "A" in text
        assert "desc a" in text

    def test_render_no_descriptions(self):
        from code_puppy.plugins.scheduler.scheduler_wizard import SelectionMenu

        menu = SelectionMenu("Pick", ["A", "B"])
        lines = menu._render()
        text = "".join(t for _, t in lines)
        assert "A" in text

    def test_render_selected_idx(self):
        from code_puppy.plugins.scheduler.scheduler_wizard import SelectionMenu

        menu = SelectionMenu("Pick", ["A", "B", "C"], ["da", "db", "dc"])
        menu.selected_idx = 2
        lines = menu._render()
        text = "".join(t for _, t in lines)
        assert "dc" in text

    @patch(f"{_MOD}.set_awaiting_user_input")
    @patch(f"{_MOD}.Application")
    def test_run_select(self, mock_app_cls, mock_await):
        from code_puppy.plugins.scheduler.scheduler_wizard import SelectionMenu

        menu = SelectionMenu("Pick", ["A", "B"])
        mock_app = MagicMock()

        def fake_run(**kw):
            menu.result = "A"

        mock_app.run.side_effect = fake_run
        mock_app_cls.return_value = mock_app
        result = menu.run()
        assert result == "A"

    @patch(f"{_MOD}.set_awaiting_user_input")
    @patch(f"{_MOD}.Application")
    def test_run_cancelled(self, mock_app_cls, mock_await):
        from code_puppy.plugins.scheduler.scheduler_wizard import SelectionMenu

        menu = SelectionMenu("Pick", ["A"])
        mock_app = MagicMock()

        def fake_run(**kw):
            menu.cancelled = True

        mock_app.run.side_effect = fake_run
        mock_app_cls.return_value = mock_app
        result = menu.run()
        assert result is None

    def test_key_bindings(self):
        """Test key binding handlers by capturing KeyBindings."""
        from prompt_toolkit.key_binding import KeyBindings as OrigKB

        captured_kb = [None]

        class CapturingKB(OrigKB):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                captured_kb[0] = self

        def _invoke(kb, key_name, app_mock=None):
            _ALIASES = {"enter": "c-m", "up": "up", "down": "down", "escape": "escape"}
            target = _ALIASES.get(key_name, key_name)
            event = MagicMock()
            event.app = app_mock or MagicMock()
            for binding in kb.bindings:
                for k in binding.keys:
                    name = k.value if hasattr(k, "value") else str(k)
                    if name == target or name == key_name:
                        binding.handler(event)
                        return event
            raise ValueError(f"No handler: {key_name}")

        from code_puppy.plugins.scheduler.scheduler_wizard import SelectionMenu

        menu = SelectionMenu("Pick", ["A", "B", "C"], ["da", "db", "dc"])

        with (
            patch(f"{_MOD}.set_awaiting_user_input"),
            patch(f"{_MOD}.KeyBindings", CapturingKB),
            patch(f"{_MOD}.Application") as mock_app_cls,
        ):
            mock_app = MagicMock()

            def fake_run(**kw):
                kb = captured_kb[0]
                # Down
                _invoke(kb, "down", mock_app)
                assert menu.selected_idx == 1
                _invoke(kb, "j", mock_app)
                assert menu.selected_idx == 2
                # Down at bottom
                _invoke(kb, "down", mock_app)
                assert menu.selected_idx == 2
                # Up
                _invoke(kb, "up", mock_app)
                assert menu.selected_idx == 1
                _invoke(kb, "k", mock_app)
                assert menu.selected_idx == 0
                # Up at top
                _invoke(kb, "up", mock_app)
                assert menu.selected_idx == 0
                # Enter
                _invoke(kb, "enter", mock_app)
                assert menu.result == "A"
                # Escape
                menu.result = None
                _invoke(kb, "escape", mock_app)
                assert menu.cancelled is True
                # Ctrl+C
                menu.cancelled = False
                _invoke(kb, "c-c", mock_app)
                assert menu.cancelled is True

            mock_app.run.side_effect = fake_run
            mock_app_cls.return_value = mock_app
            menu.run()


# ---------------------------------------------------------------------------
# TextInputMenu
# ---------------------------------------------------------------------------


class TestTextInputMenu:
    @patch("code_puppy.command_line.utils.safe_input", return_value="hello")
    def test_input(self, mock_input):
        from code_puppy.plugins.scheduler.scheduler_wizard import TextInputMenu

        menu = TextInputMenu("Name")
        assert menu.run() == "hello"

    @patch("code_puppy.command_line.utils.safe_input", return_value="")
    def test_default(self, mock_input):
        from code_puppy.plugins.scheduler.scheduler_wizard import TextInputMenu

        menu = TextInputMenu("Name", default="default-val")
        assert menu.run() == "default-val"

    @patch("code_puppy.command_line.utils.safe_input", return_value="")
    def test_empty_no_default(self, mock_input):
        from code_puppy.plugins.scheduler.scheduler_wizard import TextInputMenu

        menu = TextInputMenu("Name")
        assert menu.run() is None

    @patch("code_puppy.command_line.utils.safe_input", side_effect=KeyboardInterrupt)
    def test_cancelled(self, mock_input):
        from code_puppy.plugins.scheduler.scheduler_wizard import TextInputMenu

        menu = TextInputMenu("Name")
        assert menu.run() is None

    @patch("code_puppy.command_line.utils.safe_input", side_effect=EOFError)
    def test_eof(self, mock_input):
        from code_puppy.plugins.scheduler.scheduler_wizard import TextInputMenu

        menu = TextInputMenu("Name")
        assert menu.run() is None


# ---------------------------------------------------------------------------
# MultilineInputMenu
# ---------------------------------------------------------------------------


class TestMultilineInputMenu:
    @patch(
        "code_puppy.command_line.utils.safe_input", side_effect=["line1", "line2", ""]
    )
    def test_multiline(self, mock_input):
        from code_puppy.plugins.scheduler.scheduler_wizard import MultilineInputMenu

        menu = MultilineInputMenu("Prompt")
        result = menu.run()
        assert result == "line1\nline2"

    @patch("code_puppy.command_line.utils.safe_input", side_effect=[""])
    def test_empty(self, mock_input):
        from code_puppy.plugins.scheduler.scheduler_wizard import MultilineInputMenu

        menu = MultilineInputMenu("Prompt")
        assert menu.run() is None

    @patch("code_puppy.command_line.utils.safe_input", side_effect=KeyboardInterrupt)
    def test_cancelled(self, mock_input):
        from code_puppy.plugins.scheduler.scheduler_wizard import MultilineInputMenu

        menu = MultilineInputMenu("Prompt")
        assert menu.run() is None


# ---------------------------------------------------------------------------
# get_available_agents_list / get_available_models_list
# ---------------------------------------------------------------------------


class TestGetAgentsAndModels:
    def test_get_agents(self):
        from code_puppy.plugins.scheduler import scheduler_wizard as sw

        agents_mod = MagicMock()
        agents_mod.get_available_agents.return_value = {"a": "Agent A"}
        agents_mod.get_agent_descriptions.return_value = {"a": "Desc A"}
        with patch.dict("sys.modules", {"code_puppy.agents": agents_mod}):
            result = sw.get_available_agents_list()
        assert len(result) >= 1

    def test_get_agents_error(self):
        from code_puppy.plugins.scheduler import scheduler_wizard as sw

        with patch.dict("sys.modules", {"code_puppy.agents": None}):
            result = sw.get_available_agents_list()
        assert result == [("code-puppy", "Default agent")]

    def test_get_models(self):
        from code_puppy.plugins.scheduler import scheduler_wizard as sw

        mpc_mod = MagicMock()
        mpc_mod.load_model_names.return_value = ["m1", "m2"]
        with patch.dict(
            "sys.modules", {"code_puppy.command_line.model_picker_completion": mpc_mod}
        ):
            result = sw.get_available_models_list()
        assert "m1" in result

    def test_get_models_empty(self):
        from code_puppy.plugins.scheduler import scheduler_wizard as sw

        mpc_mod = MagicMock()
        mpc_mod.load_model_names.return_value = []
        with patch.dict(
            "sys.modules", {"code_puppy.command_line.model_picker_completion": mpc_mod}
        ):
            result = sw.get_available_models_list()
        assert result == ["(default)"]

    def test_get_models_error(self):
        from code_puppy.plugins.scheduler import scheduler_wizard as sw

        with patch.dict(
            "sys.modules", {"code_puppy.command_line.model_picker_completion": None}
        ):
            result = sw.get_available_models_list()
        assert result == ["(default)"]


# ---------------------------------------------------------------------------
# create_task_wizard
# ---------------------------------------------------------------------------


class TestCreateTaskWizard:
    @patch("code_puppy.command_line.utils.safe_input", return_value="y")
    @patch(f"{_MOD}.MultilineInputMenu")
    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    @patch(f"{_MOD}.get_available_models_list", return_value=["m1"])
    @patch(
        f"{_MOD}.get_available_agents_list", return_value=[("code-puppy", "Default")]
    )
    def test_full_wizard(
        self, mock_agents, mock_models, mock_sel, mock_text, mock_multi, mock_confirm
    ):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        # TextInputMenu: name, working_dir
        text_instances = [MagicMock(), MagicMock()]
        text_instances[0].run.return_value = "My Task"
        text_instances[1].run.return_value = "."
        mock_text.side_effect = text_instances

        # SelectionMenu: schedule, agent, model
        sel_instances = [MagicMock(), MagicMock(), MagicMock()]
        sel_instances[0].run.return_value = "Every hour"
        sel_instances[1].run.return_value = "code-puppy"
        sel_instances[2].run.return_value = "(use default model)"
        mock_sel.side_effect = sel_instances

        # MultilineInputMenu: prompt
        multi_inst = MagicMock()
        multi_inst.run.return_value = "do stuff"
        mock_multi.return_value = multi_inst

        result = create_task_wizard()
        assert result is not None
        assert result["name"] == "My Task"
        assert result["schedule_type"] == "hourly"
        assert result["model"] == ""

    @patch(f"{_MOD}.TextInputMenu")
    def test_wizard_cancel_name(self, mock_text):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        inst = MagicMock()
        inst.run.return_value = None
        mock_text.return_value = inst
        assert create_task_wizard() is None

    @patch(f"{_MOD}.SelectionMenu")
    @patch(f"{_MOD}.TextInputMenu")
    def test_wizard_cancel_schedule(self, mock_text, mock_sel):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        text_inst = MagicMock()
        text_inst.run.return_value = "Task"
        mock_text.return_value = text_inst
        sel_inst = MagicMock()
        sel_inst.run.return_value = None
        mock_sel.return_value = sel_inst
        assert create_task_wizard() is None

    @patch("code_puppy.command_line.utils.safe_input", return_value="y")
    @patch(f"{_MOD}.MultilineInputMenu")
    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    @patch(f"{_MOD}.get_available_models_list", return_value=["m1"])
    @patch(
        f"{_MOD}.get_available_agents_list", return_value=[("code-puppy", "Default")]
    )
    def test_wizard_custom_interval(
        self, mock_agents, mock_models, mock_sel, mock_text, mock_multi, mock_confirm
    ):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        # TextInputMenu: name, custom_interval, working_dir
        text_instances = [MagicMock(), MagicMock(), MagicMock()]
        text_instances[0].run.return_value = "Task"
        text_instances[1].run.return_value = "45m"
        text_instances[2].run.return_value = "."
        mock_text.side_effect = text_instances

        sel_instances = [MagicMock(), MagicMock(), MagicMock()]
        sel_instances[0].run.return_value = "Custom interval..."
        sel_instances[1].run.return_value = "code-puppy"
        sel_instances[2].run.return_value = "m1"
        mock_sel.side_effect = sel_instances

        multi_inst = MagicMock()
        multi_inst.run.return_value = "prompt"
        mock_multi.return_value = multi_inst

        result = create_task_wizard()
        assert result is not None
        assert result["schedule_value"] == "45m"

    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    def test_wizard_cancel_custom_interval(self, mock_sel, mock_text):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        text_instances = [MagicMock(), MagicMock()]
        text_instances[0].run.return_value = "Task"
        text_instances[1].run.return_value = None  # cancel custom interval
        mock_text.side_effect = text_instances

        sel_inst = MagicMock()
        sel_inst.run.return_value = "Custom interval..."
        mock_sel.return_value = sel_inst

        assert create_task_wizard() is None

    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    @patch(
        f"{_MOD}.get_available_agents_list", return_value=[("code-puppy", "Default")]
    )
    def test_wizard_cancel_agent(self, mock_agents, mock_sel, mock_text):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        text_inst = MagicMock()
        text_inst.run.return_value = "Task"
        mock_text.return_value = text_inst

        sel_instances = [MagicMock(), MagicMock()]
        sel_instances[0].run.return_value = "Every hour"
        sel_instances[1].run.return_value = None  # cancel agent
        mock_sel.side_effect = sel_instances

        assert create_task_wizard() is None

    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    @patch(f"{_MOD}.get_available_models_list", return_value=["m1"])
    @patch(
        f"{_MOD}.get_available_agents_list", return_value=[("code-puppy", "Default")]
    )
    def test_wizard_cancel_model(self, mock_agents, mock_models, mock_sel, mock_text):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        text_inst = MagicMock()
        text_inst.run.return_value = "Task"
        mock_text.return_value = text_inst

        sel_instances = [MagicMock(), MagicMock(), MagicMock()]
        sel_instances[0].run.return_value = "Every hour"
        sel_instances[1].run.return_value = "code-puppy"
        sel_instances[2].run.return_value = None  # cancel model
        mock_sel.side_effect = sel_instances

        assert create_task_wizard() is None

    @patch(f"{_MOD}.MultilineInputMenu")
    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    @patch(f"{_MOD}.get_available_models_list", return_value=["m1"])
    @patch(
        f"{_MOD}.get_available_agents_list", return_value=[("code-puppy", "Default")]
    )
    def test_wizard_cancel_prompt(
        self, mock_agents, mock_models, mock_sel, mock_text, mock_multi
    ):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        text_inst = MagicMock()
        text_inst.run.return_value = "Task"
        mock_text.return_value = text_inst

        sel_instances = [MagicMock(), MagicMock(), MagicMock()]
        sel_instances[0].run.return_value = "Every hour"
        sel_instances[1].run.return_value = "code-puppy"
        sel_instances[2].run.return_value = "m1"
        mock_sel.side_effect = sel_instances

        multi_inst = MagicMock()
        multi_inst.run.return_value = None
        mock_multi.return_value = multi_inst

        assert create_task_wizard() is None

    @patch(f"{_MOD}.MultilineInputMenu")
    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    @patch(f"{_MOD}.get_available_models_list", return_value=["m1"])
    @patch(
        f"{_MOD}.get_available_agents_list", return_value=[("code-puppy", "Default")]
    )
    def test_wizard_cancel_workdir(
        self, mock_agents, mock_models, mock_sel, mock_text, mock_multi
    ):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        text_instances = [MagicMock(), MagicMock()]
        text_instances[0].run.return_value = "Task"
        text_instances[1].run.return_value = None  # cancel workdir
        mock_text.side_effect = text_instances

        sel_instances = [MagicMock(), MagicMock(), MagicMock()]
        sel_instances[0].run.return_value = "Every hour"
        sel_instances[1].run.return_value = "code-puppy"
        sel_instances[2].run.return_value = "m1"
        mock_sel.side_effect = sel_instances

        multi_inst = MagicMock()
        multi_inst.run.return_value = "prompt"
        mock_multi.return_value = multi_inst

        assert create_task_wizard() is None

    @patch("code_puppy.command_line.utils.safe_input", return_value="n")
    @patch(f"{_MOD}.MultilineInputMenu")
    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    @patch(f"{_MOD}.get_available_models_list", return_value=["m1"])
    @patch(
        f"{_MOD}.get_available_agents_list", return_value=[("code-puppy", "Default")]
    )
    def test_wizard_decline_confirm(
        self, mock_agents, mock_models, mock_sel, mock_text, mock_multi, mock_confirm
    ):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        text_instances = [MagicMock(), MagicMock()]
        text_instances[0].run.return_value = "Task"
        text_instances[1].run.return_value = "."
        mock_text.side_effect = text_instances

        sel_instances = [MagicMock(), MagicMock(), MagicMock()]
        sel_instances[0].run.return_value = "Every hour"
        sel_instances[1].run.return_value = "code-puppy"
        sel_instances[2].run.return_value = "m1"
        mock_sel.side_effect = sel_instances

        multi_inst = MagicMock()
        multi_inst.run.return_value = "prompt"
        mock_multi.return_value = multi_inst

        assert create_task_wizard() is None

    @patch("code_puppy.command_line.utils.safe_input", side_effect=KeyboardInterrupt)
    @patch(f"{_MOD}.MultilineInputMenu")
    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    @patch(f"{_MOD}.get_available_models_list", return_value=["m1"])
    @patch(
        f"{_MOD}.get_available_agents_list", return_value=[("code-puppy", "Default")]
    )
    def test_wizard_confirm_interrupt(
        self, mock_agents, mock_models, mock_sel, mock_text, mock_multi, mock_confirm
    ):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        text_instances = [MagicMock(), MagicMock()]
        text_instances[0].run.return_value = "Task"
        text_instances[1].run.return_value = "."
        mock_text.side_effect = text_instances

        sel_instances = [MagicMock(), MagicMock(), MagicMock()]
        sel_instances[0].run.return_value = "Every hour"
        sel_instances[1].run.return_value = "code-puppy"
        sel_instances[2].run.return_value = "m1"
        mock_sel.side_effect = sel_instances

        multi_inst = MagicMock()
        multi_inst.run.return_value = "prompt"
        mock_multi.return_value = multi_inst

        assert create_task_wizard() is None

    @patch("code_puppy.command_line.utils.safe_input", return_value="y")
    @patch(f"{_MOD}.MultilineInputMenu")
    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    @patch(f"{_MOD}.get_available_models_list", return_value=["m1"])
    @patch(
        f"{_MOD}.get_available_agents_list",
        return_value=[("code-puppy", "Default"), ("other", "Other")],
    )
    def test_wizard_code_puppy_first(
        self, mock_agents, mock_models, mock_sel, mock_text, mock_multi, mock_confirm
    ):
        """Verify code-puppy is moved to front of agent list."""
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        text_instances = [MagicMock(), MagicMock()]
        text_instances[0].run.return_value = "Task"
        text_instances[1].run.return_value = "."
        mock_text.side_effect = text_instances

        sel_instances = [MagicMock(), MagicMock(), MagicMock()]
        sel_instances[0].run.return_value = "Daily"
        sel_instances[1].run.return_value = "code-puppy"
        sel_instances[2].run.return_value = "m1"
        mock_sel.side_effect = sel_instances

        multi_inst = MagicMock()
        multi_inst.run.return_value = "prompt"
        mock_multi.return_value = multi_inst

        result = create_task_wizard()
        assert result is not None
        assert result["schedule_type"] == "daily"

    # Test all schedule_map entries
    @pytest.mark.parametrize(
        "choice,expected_type,expected_value",
        [
            ("Every 15 minutes", "interval", "15m"),
            ("Every 30 minutes", "interval", "30m"),
            ("Every 2 hours", "interval", "2h"),
            ("Every 6 hours", "interval", "6h"),
        ],
    )
    @patch("code_puppy.command_line.utils.safe_input", return_value="y")
    @patch(f"{_MOD}.MultilineInputMenu")
    @patch(f"{_MOD}.TextInputMenu")
    @patch(f"{_MOD}.SelectionMenu")
    @patch(f"{_MOD}.get_available_models_list", return_value=["m1"])
    @patch(
        f"{_MOD}.get_available_agents_list", return_value=[("code-puppy", "Default")]
    )
    def test_schedule_map(
        self,
        mock_agents,
        mock_models,
        mock_sel,
        mock_text,
        mock_multi,
        mock_confirm,
        choice,
        expected_type,
        expected_value,
    ):
        from code_puppy.plugins.scheduler.scheduler_wizard import create_task_wizard

        text_instances = [MagicMock(), MagicMock()]
        text_instances[0].run.return_value = "Task"
        text_instances[1].run.return_value = "."
        mock_text.side_effect = text_instances

        sel_instances = [MagicMock(), MagicMock(), MagicMock()]
        sel_instances[0].run.return_value = choice
        sel_instances[1].run.return_value = "code-puppy"
        sel_instances[2].run.return_value = "m1"
        mock_sel.side_effect = sel_instances

        multi_inst = MagicMock()
        multi_inst.run.return_value = "prompt"
        mock_multi.return_value = multi_inst

        result = create_task_wizard()
        assert result["schedule_type"] == expected_type
        assert result["schedule_value"] == expected_value
