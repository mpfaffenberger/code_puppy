"""Tests for code_puppy/command_line/mcp/custom_server_form.py"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
# Preview rendering
# ---------------------------------------------------------------------------


class TestFormPreview:
    def test_preview_shows_values_and_valid_json(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CustomServerForm,
            form_preview,
        )

        form = CustomServerForm(MagicMock())
        form.server_name = "my-srv"
        text = form_preview(form)
        assert "my-srv" in text
        assert "stdio" in text
        assert "valid" in text

    def test_preview_shows_json_error(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CustomServerForm,
            form_preview,
        )

        form = CustomServerForm(MagicMock())
        form.json_config = "{nope"
        text = form_preview(form)
        assert "Invalid JSON" in text

    def test_preview_shows_status_message(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CustomServerForm,
            form_preview,
        )

        form = CustomServerForm(MagicMock())
        form.status_message = "Save failed: kaboom"
        form.status_is_error = True
        assert "Save failed: kaboom" in form_preview(form)


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

    def test_install_new_server_success(self, tmp_path):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mcp_file = tmp_path / "mcp_servers.json"
        mgr = MagicMock()
        mgr.register_server.return_value = "new-id"
        form = CustomServerForm(mgr)
        form.server_name = "my-server"
        form.json_config = json.dumps({"command": "npx", "args": []})

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            assert form._install_server() is True

        data = json.loads(mcp_file.read_text())
        assert "my-server" in data["mcp_servers"]

    def test_install_new_server_register_fails(self, tmp_path):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mcp_file = tmp_path / "mcp_servers.json"
        mgr = MagicMock()
        mgr.register_server.return_value = None
        form = CustomServerForm(mgr)
        form.server_name = "my-server"
        form.json_config = json.dumps({"command": "npx"})

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            assert form._install_server() is False
        assert form.status_is_error is True

    def test_install_edit_mode_existing_found(self, tmp_path):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mcp_file = tmp_path / "mcp_servers.json"
        mcp_file.write_text(json.dumps({"mcp_servers": {"old": {}}}))
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

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            assert form._install_server() is True

    def test_install_edit_mode_existing_not_found(self, tmp_path):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mcp_file = tmp_path / "mcp_servers.json"
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

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            assert form._install_server() is True

    def test_install_edit_mode_update_fails(self, tmp_path):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mcp_file = tmp_path / "mcp_servers.json"
        mcp_file.write_text(json.dumps({"mcp_servers": {}}))
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

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            assert form._install_server() is False

    def test_install_exception_during_save(self, tmp_path):
        """_install_server must report failure (not raise) if persisting to
        mcp_servers.json blows up -- the underlying I/O failure modes
        themselves are covered by test_atomic_io.py / test_atomic_json.py,
        this just pins _install_server's own error handling."""
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mcp_file = tmp_path / "mcp_servers.json"
        mgr = MagicMock()
        mgr.register_server.return_value = "new-id"
        form = CustomServerForm(mgr)
        form.server_name = "my-server"
        form.json_config = json.dumps({"command": "npx"})

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            with patch(
                "code_puppy.command_line.mcp.mcp_servers_store.upsert_mcp_server",
                side_effect=PermissionError("no access"),
            ):
                assert form._install_server() is False
        assert form.status_is_error is True

    def test_install_edit_mode_name_changed_removes_old(self, tmp_path):
        """When editing and name changes, old entry should be removed from persisted file."""
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        mcp_file = tmp_path / "mcp_servers.json"
        mcp_file.write_text(json.dumps({"mcp_servers": {"old-name": {}}}))
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

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            assert form._install_server() is True

        data = json.loads(mcp_file.read_text())
        assert "new-name" in data["mcp_servers"]
        assert "old-name" not in data["mcp_servers"]


# ---------------------------------------------------------------------------
# run() method
# ---------------------------------------------------------------------------
# Flow (headless widget drives)
# ---------------------------------------------------------------------------


def _keys(*keys):
    from io import StringIO

    script = iter(keys)
    return {
        "key_source": lambda: next(script),
        "output": StringIO(),
        "size": lambda: (110, 32),
    }


class TestFormWidgets:
    def test_form_menu_lists_fields(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CustomServerForm,
            build_form_menu,
        )

        form = CustomServerForm(MagicMock())
        menu = build_form_menu(form, **_keys("enter"))
        result = menu.run()
        assert result.item.value == "name"

    def test_name_editor_updates_form(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CustomServerForm,
            run_name_editor,
        )

        form = CustomServerForm(MagicMock())
        run_name_editor(form, **_keys("s", "r", "v", "enter"))
        assert form.server_name == "srv"

    def test_name_editor_escape_keeps_value(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CustomServerForm,
            run_name_editor,
        )

        form = CustomServerForm(MagicMock(), existing_name="keep-me")
        run_name_editor(form, **_keys("escape"))
        assert form.server_name == "keep-me"

    def test_type_menu_swaps_example_json(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CUSTOM_SERVER_EXAMPLES,
            CustomServerForm,
            run_type_menu,
        )

        form = CustomServerForm(MagicMock())
        run_type_menu(form, **_keys("down", "enter"))  # http
        assert form._get_current_type() == "http"
        assert form.json_config == CUSTOM_SERVER_EXAMPLES["http"]

    def test_type_menu_never_clobbers_user_json(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CustomServerForm,
            run_type_menu,
        )

        form = CustomServerForm(
            MagicMock(), existing_config={"command": "mine", "args": []}
        )
        original = form.json_config
        run_type_menu(form, **_keys("down", "enter"))
        assert form._get_current_type() == "http"
        assert form.json_config == original  # user config untouched

    def test_json_fallback_editor_reformats(self):
        from code_puppy.command_line.mcp.custom_server_form import (
            CustomServerForm,
            run_json_fallback_editor,
        )

        form = CustomServerForm(MagicMock())
        form.json_config = "{}"
        keys = list('{"command": "x"}'.replace("{}", "")) or []
        # Clear the initial compact text, then type fresh JSON.
        script = ["ctrl-u"] + list('{"command":"x"}') + ["enter"]
        run_json_fallback_editor(form, **_keys(*script))
        assert json.loads(form.json_config) == {"command": "x"}


class TestEditJsonInEditor:
    def test_editor_roundtrip(self, monkeypatch, tmp_path):
        from code_puppy.command_line.mcp import custom_server_form as csf

        def fake_call(cmd):
            Path(cmd[-1]).write_text('{"command": "edited"}')
            return 0

        monkeypatch.setenv("EDITOR", "true")
        monkeypatch.setattr(csf.subprocess, "call", fake_call)
        assert csf.edit_json_in_editor("{}") == '{"command": "edited"}'

    def test_editor_failure_returns_none(self, monkeypatch):
        from code_puppy.command_line.mcp import custom_server_form as csf

        monkeypatch.setattr(csf.subprocess, "call", lambda cmd: 1)
        assert csf.edit_json_in_editor("{}") is None


class TestRunFormFlow:
    def _flow(self, form, menu_scripts, **kwargs):
        from code_puppy.command_line.mcp.custom_server_form import (
            build_form_menu,
            run_form_flow,
        )

        scripts = iter(menu_scripts)

        def factory(f, initial_index=0, **kw):
            return build_form_menu(f, initial_index=initial_index, **_keys(*next(scripts)))

        return run_form_flow(form, menu_factory=factory, **kwargs)

    def test_cancel_via_escape(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        form = CustomServerForm(MagicMock())
        assert self._flow(form, [["escape"]]) is False
        assert form.result == "cancelled"

    def test_cancel_menu_entry(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        form = CustomServerForm(MagicMock())
        assert self._flow(form, [["end", "enter"]]) is False  # last item = Cancel

    def test_save_success_installs(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        form = CustomServerForm(MagicMock())
        form.server_name = "srv"
        with patch.object(
            CustomServerForm, "_install_server", return_value=True
        ) as mock_install:
            # Save & Install is second from last.
            assert self._flow(form, [["end", "up", "enter"]]) is True
        mock_install.assert_called_once()
        assert form.result == "installed"

    def test_save_failure_reopens_menu(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        form = CustomServerForm(MagicMock())
        with patch.object(CustomServerForm, "_install_server", return_value=False):
            result = self._flow(form, [["end", "up", "enter"], ["escape"]])
        assert result is False

    def test_edit_name_then_save(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        form = CustomServerForm(MagicMock())
        with patch.object(CustomServerForm, "_install_server", return_value=True):
            result = self._flow(
                form,
                [["enter"], ["end", "up", "enter"]],
                name_editor=lambda f, **kw: setattr(f, "server_name", "typed"),
            )
        assert result is True
        assert form.server_name == "typed"

    def test_json_editor_fallback_used_when_editor_unavailable(self):
        from code_puppy.command_line.mcp.custom_server_form import CustomServerForm

        form = CustomServerForm(MagicMock())
        fallback_called = []
        self._flow(
            form,
            [["down", "down", "enter"], ["escape"]],
            json_editor=lambda initial: None,
            json_fallback=lambda f, **kw: fallback_called.append(True),
        )
        assert fallback_called == [True]


class TestRunCustomServerForm:
    def test_delegates_and_reports(self):
        from code_puppy.command_line.mcp import custom_server_form as csf

        mgr = MagicMock()
        with (
            patch.object(csf, "run_form_flow", return_value=True) as mock_flow,
            patch(
                "code_puppy.command_line.menu_session.menu_session"
            ) as mock_session,
            patch(
                "code_puppy.command_line.mcp_binding_menu.prompt_bind_after_install_sync",
                create=True,  # only the async variant exists; the call site
                # swallows the ImportError (same as the old implementation)
            ) as mock_bind,
        ):
            mock_session.return_value.__enter__ = lambda s: None
            mock_session.return_value.__exit__ = lambda s, *a: False
            result = csf.run_custom_server_form(mgr)
        assert result is True
        mock_flow.assert_called_once()
        mock_bind.assert_called_once()

    def test_returns_false_on_cancel(self):
        from code_puppy.command_line.mcp import custom_server_form as csf

        with (
            patch.object(csf, "run_form_flow", return_value=False),
            patch("code_puppy.command_line.menu_session.menu_session") as mock_session,
        ):
            mock_session.return_value.__enter__ = lambda s: None
            mock_session.return_value.__exit__ = lambda s, *a: False
            assert csf.run_custom_server_form(MagicMock()) is False

