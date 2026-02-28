"""Tests for code_puppy/command_line/mcp/custom_server_form.py"""

import json
from unittest.mock import MagicMock, mock_open, patch

MODULE = "code_puppy.command_line.mcp.custom_server_form"


# ---------------------------------------------------------------------------
# Constants / module-level data
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_server_types(self):
        from code_puppy.command_line.mcp.custom_server_form import SERVER_TYPES

        assert SERVER_TYPES == ["stdio", "http", "sse"]

    def test_custom_server_examples_keys(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CUSTOM_SERVER_EXAMPLES,
        )

        assert set(CUSTOM_SERVER_EXAMPLES.keys()) == {"stdio", "http", "sse"}

    def test_examples_are_valid_json(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CUSTOM_SERVER_EXAMPLES,
        )

        for key, example in CUSTOM_SERVER_EXAMPLES.items():
            parsed = json.loads(example)
            assert isinstance(parsed, dict)

    def test_server_type_descriptions(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            SERVER_TYPE_DESCRIPTIONS,
        )

        assert "stdio" in SERVER_TYPE_DESCRIPTIONS
        assert "http" in SERVER_TYPE_DESCRIPTIONS
        assert "sse" in SERVER_TYPE_DESCRIPTIONS


# ---------------------------------------------------------------------------
# CustomServerForm.__init__
# ---------------------------------------------------------------------------


class TestCustomServerFormInit:
    def test_default_init(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mgr = MagicMock()
        form = CustomServerForm(mgr)
        assert form.edit_mode is False
        assert form.server_name == ""
        assert form.selected_type_idx == 0
        assert form.result is None
        assert form.focused_field == 0
        assert form.validation_error is None
        assert form.status_message is None
        assert form.status_is_error is False

    def test_edit_mode_init(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mgr = MagicMock()
        cfg = {"command": "npx", "args": ["-y", "test"]}
        form = CustomServerForm(
            mgr,
            edit_mode=True,
            existing_name="my-srv",
            existing_type="http",
            existing_config=cfg,
        )
        assert form.edit_mode is True
        assert form.original_name == "my-srv"
        assert form.selected_type_idx == 1  # http index
        assert json.loads(form.json_config) == cfg

    def test_edit_mode_unknown_type_defaults_to_zero(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        form = CustomServerForm(MagicMock(), existing_type="unknown")
        assert form.selected_type_idx == 0

    def test_no_existing_config_uses_example(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CUSTOM_SERVER_EXAMPLES,
            CustomServerForm,
        )

        form = CustomServerForm(MagicMock())
        assert form.json_config == CUSTOM_SERVER_EXAMPLES["stdio"]


# ---------------------------------------------------------------------------
# _get_current_type
# ---------------------------------------------------------------------------


class TestGetCurrentType:
    def test_returns_correct_type(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        form = CustomServerForm(MagicMock())
        form.selected_type_idx = 2
        assert form._get_current_type() == "sse"


# ---------------------------------------------------------------------------
# _validate_server_name
# ---------------------------------------------------------------------------


class TestValidateServerName:
    def _make_form(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        return CustomServerForm(MagicMock())

    def test_empty_name(self):
        assert self._make_form()._validate_server_name("") is not None

    def test_whitespace_only(self):
        assert self._make_form()._validate_server_name("   ") is not None

    def test_valid_name(self):
        assert self._make_form()._validate_server_name("my-server_1") is None

    def test_invalid_chars(self):
        assert self._make_form()._validate_server_name("my server!") is not None

    def test_too_long(self):
        assert self._make_form()._validate_server_name("a" * 65) is not None

    def test_max_length_ok(self):
        assert self._make_form()._validate_server_name("a" * 64) is None


# ---------------------------------------------------------------------------
# _validate_json
# ---------------------------------------------------------------------------


class TestValidateJson:
    def _make_form(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        return CustomServerForm(MagicMock())

    def test_valid_stdio(self):
        form = self._make_form()
        form.json_config = json.dumps({"command": "npx", "args": []})
        form.selected_type_idx = 0  # stdio
        assert form._validate_json() is True
        assert form.validation_error is None

    def test_stdio_missing_command(self):
        form = self._make_form()
        form.json_config = json.dumps({"args": []})
        form.selected_type_idx = 0
        assert form._validate_json() is False
        assert "command" in form.validation_error

    def test_valid_http(self):
        form = self._make_form()
        form.json_config = json.dumps({"url": "http://localhost"})
        form.selected_type_idx = 1  # http
        assert form._validate_json() is True

    def test_http_missing_url(self):
        form = self._make_form()
        form.json_config = json.dumps({"command": "x"})
        form.selected_type_idx = 1
        assert form._validate_json() is False
        assert "url" in form.validation_error

    def test_valid_sse(self):
        form = self._make_form()
        form.json_config = json.dumps({"url": "http://localhost/sse"})
        form.selected_type_idx = 2  # sse
        assert form._validate_json() is True

    def test_sse_missing_url(self):
        form = self._make_form()
        form.json_config = json.dumps({})
        form.selected_type_idx = 2
        assert form._validate_json() is False

    def test_invalid_json(self):
        form = self._make_form()
        form.json_config = "{not valid json"
        assert form._validate_json() is False
        assert "Invalid JSON" in form.validation_error


# ---------------------------------------------------------------------------
# _render_form
# ---------------------------------------------------------------------------


class TestRenderForm:
    def _make_form(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        return CustomServerForm(MagicMock())

    def test_render_form_returns_list(self):
        form = self._make_form()
        result = form._render_form()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_render_form_edit_mode(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        form = CustomServerForm(MagicMock(), edit_mode=True)
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "EDIT" in texts

    def test_render_form_add_mode(self):
        form = self._make_form()
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "ADD" in texts

    def test_render_form_focused_name(self):
        form = self._make_form()
        form.focused_field = 0
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "Type in the box below" in texts

    def test_render_form_unfocused_name_empty(self):
        form = self._make_form()
        form.focused_field = 1
        form.server_name = ""
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "(not set)" in texts

    def test_render_form_unfocused_name_set(self):
        form = self._make_form()
        form.focused_field = 1
        form.server_name = "test-srv"
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "test-srv" in texts

    def test_render_form_name_validation_hint(self):
        form = self._make_form()
        form.focused_field = 1
        form.server_name = "bad name!"
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "⚠" in texts

    def test_render_form_focused_type(self):
        form = self._make_form()
        form.focused_field = 1
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "Change type" in texts

    def test_render_form_focused_json(self):
        form = self._make_form()
        form.focused_field = 2
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "Editing in box below" in texts

    def test_render_form_validation_error(self):
        form = self._make_form()
        form.validation_error = "Something wrong"
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "Something wrong" in texts

    def test_render_form_valid_json_indicator(self):
        form = self._make_form()
        form.validation_error = None
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "Valid JSON" in texts

    def test_render_form_status_message_error(self):
        form = self._make_form()
        form.status_message = "Save failed: oops"
        form.status_is_error = True
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "Save failed: oops" in texts

    def test_render_form_status_message_success(self):
        form = self._make_form()
        form.status_message = "Saved!"
        form.status_is_error = False
        result = form._render_form()
        texts = "".join(t[1] for t in result)
        assert "Saved!" in texts


# ---------------------------------------------------------------------------
# _render_preview
# ---------------------------------------------------------------------------


class TestRenderPreview:
    def _make_form(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        return CustomServerForm(MagicMock())

    def test_render_preview_stdio(self):
        form = self._make_form()
        form.selected_type_idx = 0
        result = form._render_preview()
        texts = "".join(t[1] for t in result)
        assert "STDIO" in texts
        assert "command" in texts

    def test_render_preview_http(self):
        form = self._make_form()
        form.selected_type_idx = 1
        result = form._render_preview()
        texts = "".join(t[1] for t in result)
        assert "HTTP" in texts
        assert "url" in texts

    def test_render_preview_sse(self):
        form = self._make_form()
        form.selected_type_idx = 2
        result = form._render_preview()
        texts = "".join(t[1] for t in result)
        assert "SSE" in texts

    def test_render_preview_contains_tips(self):
        form = self._make_form()
        result = form._render_preview()
        texts = "".join(t[1] for t in result)
        assert "Tips" in texts
        assert "$ENV_VAR" in texts


# ---------------------------------------------------------------------------
# _install_server
# ---------------------------------------------------------------------------


class TestInstallServer:
    def _make_form(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        form = CustomServerForm(MagicMock())
        return form

    def test_install_fails_invalid_name(self):
        form = self._make_form()
        form.server_name = ""
        assert form._install_server() is False
        assert form.status_is_error is True

    def test_install_fails_invalid_json(self):
        form = self._make_form()
        form.server_name = "good-name"
        form.json_config = "{bad json"
        assert form._install_server() is False
        assert form.status_is_error is True

    @patch(f"{MODULE}.os.path.exists", return_value=False)
    @patch(f"{MODULE}.os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_install_new_server_success(self, m_open, m_makedirs, m_exists):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mgr = MagicMock()
        mgr.register_server.return_value = "new-id"
        form = CustomServerForm(mgr)
        form.server_name = "my-server"
        form.json_config = json.dumps({"command": "npx", "args": []})
        assert form._install_server() is True

    @patch(f"{MODULE}.os.path.exists", return_value=False)
    @patch(f"{MODULE}.os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_install_new_server_register_fails(self, m_open, m_makedirs, m_exists):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mgr = MagicMock()
        mgr.register_server.return_value = None
        form = CustomServerForm(mgr)
        form.server_name = "my-server"
        form.json_config = json.dumps({"command": "npx"})
        assert form._install_server() is False
        assert form.status_is_error is True

    @patch(f"{MODULE}.os.path.exists", return_value=True)
    @patch(f"{MODULE}.os.makedirs")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=json.dumps({"mcp_servers": {"old": {}}}),
    )
    def test_install_edit_mode_existing_found(self, m_open, m_makedirs, m_exists):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mgr = MagicMock()
        existing = MagicMock()
        existing.id = "old-id"
        mgr.get_server_by_name.return_value = existing
        mgr.update_server.return_value = True
        form = CustomServerForm(
            mgr,
            edit_mode=True,
            existing_name="old-name",
            existing_type="stdio",
        )
        form.server_name = "new-name"
        form.json_config = json.dumps({"command": "npx"})
        assert form._install_server() is True

    @patch(f"{MODULE}.os.path.exists", return_value=False)
    @patch(f"{MODULE}.os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_install_edit_mode_existing_not_found(self, m_open, m_makedirs, m_exists):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mgr = MagicMock()
        mgr.get_server_by_name.return_value = None
        mgr.register_server.return_value = "new-id"
        form = CustomServerForm(
            mgr,
            edit_mode=True,
            existing_name="old-name",
        )
        form.server_name = "my-server"
        form.json_config = json.dumps({"command": "npx"})
        assert form._install_server() is True

    @patch(f"{MODULE}.os.path.exists", return_value=True)
    @patch(f"{MODULE}.os.makedirs")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=json.dumps({"mcp_servers": {}}),
    )
    def test_install_edit_mode_update_fails(self, m_open, m_makedirs, m_exists):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mgr = MagicMock()
        existing = MagicMock()
        existing.id = "old-id"
        mgr.get_server_by_name.return_value = existing
        mgr.update_server.return_value = False
        form = CustomServerForm(
            mgr,
            edit_mode=True,
            existing_name="old",
        )
        form.server_name = "my-server"
        form.json_config = json.dumps({"command": "npx"})
        assert form._install_server() is False

    @patch(f"{MODULE}.os.path.exists", return_value=True)
    @patch(f"{MODULE}.os.makedirs")
    @patch("builtins.open", side_effect=PermissionError("no access"))
    def test_install_exception_during_save(self, m_open, m_makedirs, m_exists):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mgr = MagicMock()
        mgr.register_server.return_value = "new-id"
        form = CustomServerForm(mgr)
        form.server_name = "my-server"
        form.json_config = json.dumps({"command": "npx"})
        assert form._install_server() is False
        assert form.status_is_error is True

    @patch(f"{MODULE}.os.path.exists", return_value=True)
    @patch(f"{MODULE}.os.makedirs")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=json.dumps({"mcp_servers": {"old-name": {}}}),
    )
    def test_install_edit_mode_name_changed_removes_old(
        self, m_open, m_makedirs, m_exists
    ):
        """When editing and name changes, old entry should be removed from persisted file."""
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mgr = MagicMock()
        existing = MagicMock()
        existing.id = "old-id"
        mgr.get_server_by_name.return_value = existing
        mgr.update_server.return_value = True
        form = CustomServerForm(
            mgr,
            edit_mode=True,
            existing_name="old-name",
        )
        form.server_name = "new-name"
        form.json_config = json.dumps({"command": "npx"})
        assert form._install_server() is True
        # Verify JSON written includes new name and not old
        written = m_open().write.call_args_list
        written_str = "".join(c[0][0] for c in written)
        data = json.loads(written_str)
        assert "new-name" in data["mcp_servers"]
        assert "old-name" not in data["mcp_servers"]


# ---------------------------------------------------------------------------
# run() method
# ---------------------------------------------------------------------------


class TestRun:
    @patch(f"{MODULE}.set_awaiting_user_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.sys")
    @patch(f"{MODULE}.time")
    @patch(f"{MODULE}.Application")
    def test_run_cancelled(self, MockApp, mock_time, mock_sys, mock_emit, mock_set):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mock_sys.stdout = MagicMock()
        app_instance = MagicMock()
        MockApp.return_value = app_instance

        form = CustomServerForm(MagicMock())
        form.result = "cancelled"

        def side_run(**kwargs):
            form.result = "cancelled"

        app_instance.run.side_effect = side_run

        result = form.run()
        assert result is False
        mock_set.assert_any_call(True)
        mock_set.assert_any_call(False)

    @patch(f"{MODULE}.set_awaiting_user_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_success")
    @patch(f"{MODULE}.sys")
    @patch(f"{MODULE}.time")
    @patch(f"{MODULE}.Application")
    def test_run_installed(
        self, MockApp, mock_time, mock_sys, mock_success, mock_info, mock_set
    ):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mock_sys.stdout = MagicMock()
        app_instance = MagicMock()
        MockApp.return_value = app_instance

        form = CustomServerForm(MagicMock())
        form.server_name = "test-srv"

        def side_run(**kwargs):
            form.result = "installed"

        app_instance.run.side_effect = side_run

        result = form.run()
        assert result is True
        mock_success.assert_called()

    @patch(f"{MODULE}.set_awaiting_user_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_success")
    @patch(f"{MODULE}.sys")
    @patch(f"{MODULE}.time")
    @patch(f"{MODULE}.Application")
    def test_run_installed_edit_mode(
        self, MockApp, mock_time, mock_sys, mock_success, mock_info, mock_set
    ):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mock_sys.stdout = MagicMock()
        app_instance = MagicMock()
        MockApp.return_value = app_instance

        form = CustomServerForm(MagicMock(), edit_mode=True, existing_name="old")
        form.server_name = "test-srv"

        def side_run(**kwargs):
            form.result = "installed"

        app_instance.run.side_effect = side_run

        result = form.run()
        assert result is True
        success_msg = mock_success.call_args[0][0]
        assert "updated" in success_msg.lower() or "updated" in success_msg


# ---------------------------------------------------------------------------
# Key binding handlers inside run()
# ---------------------------------------------------------------------------


class TestRunKeyBindings:
    """Test the inner key-binding handlers by capturing the KeyBindings object."""

    def _run_form_capture_kb(self):
        """Create form and capture the KeyBindings passed to Application."""
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        captured = {}

        with (
            patch(f"{MODULE}.set_awaiting_user_input"),
            patch(f"{MODULE}.sys") as mock_sys,
            patch(f"{MODULE}.time"),
            patch(f"{MODULE}.emit_info"),
            patch(f"{MODULE}.Application") as MockApp,
        ):
            mock_sys.stdout = MagicMock()
            app_instance = MagicMock()

            def capture_app(**kwargs):
                captured["kb"] = kwargs.get("key_bindings")
                captured["layout"] = kwargs.get("layout")
                return app_instance

            MockApp.side_effect = capture_app

            form = CustomServerForm(MagicMock())

            def side_run(**kwargs):
                form.result = "cancelled"

            app_instance.run.side_effect = side_run
            form.run()

        return form, captured.get("kb"), app_instance

    def _find_handler(self, kb, key_name):
        """Find a handler in KeyBindings by key name."""
        alias_map = {"tab": "c-i"}
        search = alias_map.get(key_name, key_name)
        for binding in kb.bindings:
            keys = [k.value if hasattr(k, "value") else str(k) for k in binding.keys]
            if search in keys:
                return binding.handler
        return None

    def test_tab_handler(self):
        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "tab")
        assert handler is not None
        event = MagicMock()
        event.app = app
        form.focused_field = 0
        handler(event)
        assert form.focused_field == 1

    def test_shift_tab_handler(self):
        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "s-tab")
        assert handler is not None
        event = MagicMock()
        event.app = app
        form.focused_field = 1
        handler(event)
        assert form.focused_field == 0

    def test_up_handler(self):
        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "up")
        assert handler is not None
        event = MagicMock()
        event.app = app
        form.focused_field = 1  # type selector
        form.selected_type_idx = 1
        handler(event)
        assert form.selected_type_idx == 0

    def test_up_handler_at_zero(self):
        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "up")
        event = MagicMock()
        event.app = app
        form.focused_field = 1
        form.selected_type_idx = 0
        handler(event)
        assert form.selected_type_idx == 0  # stays at 0

    def test_down_handler(self):
        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "down")
        assert handler is not None
        event = MagicMock()
        event.app = app
        form.focused_field = 1
        form.selected_type_idx = 0
        handler(event)
        assert form.selected_type_idx == 1

    def test_down_handler_at_max(self):
        from code_puppy.command_line.mcp.custom_server_form import SERVER_TYPES

        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "down")
        event = MagicMock()
        event.app = app
        form.focused_field = 1
        form.selected_type_idx = len(SERVER_TYPES) - 1
        handler(event)
        assert form.selected_type_idx == len(SERVER_TYPES) - 1

    def test_ctrl_n_handler(self):
        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "c-n")
        assert handler is not None
        event = MagicMock()
        event.app = app
        handler(event)
        # Should load example
        from code_puppy.command_line.mcp.custom_server_form import (
            CUSTOM_SERVER_EXAMPLES,
        )

        assert form.json_area.text == CUSTOM_SERVER_EXAMPLES[form._get_current_type()]

    def test_ctrl_s_handler_success(self):
        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "c-s")
        assert handler is not None
        event = MagicMock()
        event.app = app
        form.name_area.text = "good-name"
        form.json_area.text = json.dumps({"command": "npx"})
        with patch.object(form, "_install_server", return_value=True):
            handler(event)
        assert form.result == "installed"
        event.app.exit.assert_called_once()

    def test_ctrl_s_handler_failure(self):
        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "c-s")
        event = MagicMock()
        event.app = app
        form.name_area.text = "good-name"
        form.json_area.text = json.dumps({"command": "npx"})
        with patch.object(form, "_install_server", return_value=False):
            handler(event)
        assert form.result != "installed"

    def test_escape_handler(self):
        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "escape")
        assert handler is not None
        event = MagicMock()
        event.app = app
        handler(event)
        assert form.result == "cancelled"
        event.app.exit.assert_called()

    def test_ctrl_c_handler(self):
        form, kb, app = self._run_form_capture_kb()
        handler = self._find_handler(kb, "c-c")
        assert handler is not None
        event = MagicMock()
        event.app = app
        handler(event)
        assert form.result == "cancelled"


# ---------------------------------------------------------------------------
# run_custom_server_form
# ---------------------------------------------------------------------------


class TestRunCustomServerForm:
    @patch(f"{MODULE}.CustomServerForm")
    def test_delegates_to_form(self, MockForm):
        from code_puppy.command_line.mcp.custom_server_form import (
            run_custom_server_form,
        )

        instance = MagicMock()
        instance.run.return_value = True
        MockForm.return_value = instance
        result = run_custom_server_form(
            MagicMock(),
            edit_mode=True,
            existing_name="x",
            existing_type="http",
            existing_config={"url": "http://a"},
        )
        assert result is True
        MockForm.assert_called_once()
        instance.run.assert_called_once()

    @patch(f"{MODULE}.CustomServerForm")
    def test_returns_false_on_cancel(self, MockForm):
        from code_puppy.command_line.mcp.custom_server_form import (
            run_custom_server_form,
        )

        instance = MagicMock()
        instance.run.return_value = False
        MockForm.return_value = instance
        assert run_custom_server_form(MagicMock()) is False
