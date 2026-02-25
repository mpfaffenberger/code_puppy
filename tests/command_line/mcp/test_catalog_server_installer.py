"""Tests for code_puppy/command_line/mcp/catalog_server_installer.py"""

import os
from unittest.mock import MagicMock, patch

MODULE = "code_puppy.command_line.mcp.catalog_server_installer"
UTILS = "code_puppy.command_line.mcp.utils"


# ---------------------------------------------------------------------------
# Helper fakes
# ---------------------------------------------------------------------------


class FakeServer:
    name = "test-server"
    display_name = "Test Server"
    description = "A test MCP server"

    def get_environment_vars(self):
        return []

    def get_command_line_args(self):
        return []


class FakeServerWithEnv(FakeServer):
    def get_environment_vars(self):
        return ["MY_TOKEN", "GITHUB_TOKEN"]


class FakeServerWithArgs(FakeServer):
    def get_command_line_args(self):
        return [
            {
                "name": "db_url",
                "prompt": "Database URL",
                "default": "localhost",
                "required": True,
            },
            {
                "name": "optional_flag",
                "prompt": "Flag",
                "default": "",
                "required": False,
            },
        ]


# ---------------------------------------------------------------------------
# get_env_var_hint
# ---------------------------------------------------------------------------


class TestGetEnvVarHint:
    def test_known_var(self):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            get_env_var_hint,
        )

        hint = get_env_var_hint("GITHUB_TOKEN")
        assert "github" in hint.lower()

    def test_unknown_var(self):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            get_env_var_hint,
        )

        assert get_env_var_hint("UNKNOWN_VAR_XYZ") == ""


# ---------------------------------------------------------------------------
# prompt_for_server_config
# ---------------------------------------------------------------------------


class TestPromptForServerConfig:
    @patch(f"{MODULE}.safe_input", return_value="")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    def test_default_name(self, mock_find, mock_info, mock_input):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        result = prompt_for_server_config(MagicMock(), FakeServer())
        assert result is not None
        assert result["name"] == "test-server"

    @patch(f"{MODULE}.safe_input", return_value="custom-name")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    def test_custom_name(self, mock_find, mock_info, mock_input):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        result = prompt_for_server_config(MagicMock(), FakeServer())
        assert result["name"] == "custom-name"

    @patch(f"{MODULE}.safe_input", side_effect=KeyboardInterrupt)
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    def test_keyboard_interrupt_on_name(self, mock_warn, mock_info, mock_input):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        assert prompt_for_server_config(MagicMock(), FakeServer()) is None

    @patch(f"{MODULE}.safe_input", side_effect=EOFError)
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    def test_eof_on_name(self, mock_warn, mock_info, mock_input):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        assert prompt_for_server_config(MagicMock(), FakeServer()) is None

    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{UTILS}.find_server_id_by_name", return_value="existing-id")
    def test_existing_server_declined(
        self, mock_find, mock_warn, mock_info, mock_input
    ):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.side_effect = ["my-server", "n"]
        assert prompt_for_server_config(MagicMock(), FakeServer()) is None

    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{UTILS}.find_server_id_by_name", return_value="existing-id")
    def test_existing_server_accepted(
        self, mock_find, mock_warn, mock_info, mock_input
    ):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.side_effect = ["my-server", "yes"]
        result = prompt_for_server_config(MagicMock(), FakeServer())
        assert result is not None

    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{UTILS}.find_server_id_by_name", return_value="existing-id")
    def test_existing_server_interrupt_on_override(
        self, mock_find, mock_warn, mock_info, mock_input
    ):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.side_effect = ["my-server", KeyboardInterrupt]
        assert prompt_for_server_config(MagicMock(), FakeServer()) is None

    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{UTILS}.find_server_id_by_name", return_value="existing-id")
    def test_existing_server_eof_on_override(
        self, mock_find, mock_warn, mock_info, mock_input
    ):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.side_effect = ["my-server", EOFError]
        assert prompt_for_server_config(MagicMock(), FakeServer()) is None

    @patch("code_puppy.config.set_config_value")
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    def test_env_vars_already_set(self, mock_find, mock_info, mock_input, mock_set_cfg):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.return_value = ""  # default name
        with patch.dict(os.environ, {"MY_TOKEN": "abc", "GITHUB_TOKEN": "def"}):
            result = prompt_for_server_config(MagicMock(), FakeServerWithEnv())
        assert result is not None
        assert result["env_vars"]["MY_TOKEN"] == "abc"
        assert result["env_vars"]["GITHUB_TOKEN"] == "def"

    @patch("code_puppy.config.set_config_value")
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    def test_env_vars_prompted(self, mock_find, mock_info, mock_input, mock_set_cfg):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.side_effect = [
            "",
            "token123",
            "ghtoken",
        ]  # name default, then 2 env vars
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_TOKEN", None)
            os.environ.pop("GITHUB_TOKEN", None)
            result = prompt_for_server_config(MagicMock(), FakeServerWithEnv())
        assert result is not None
        assert result["env_vars"]["MY_TOKEN"] == "token123"

    @patch("code_puppy.config.set_config_value")
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    def test_env_vars_interrupt(
        self, mock_find, mock_warn, mock_info, mock_input, mock_set_cfg
    ):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.side_effect = [
            "",
            KeyboardInterrupt,
        ]  # name default, then interrupt on env var
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_TOKEN", None)
            os.environ.pop("GITHUB_TOKEN", None)
            assert prompt_for_server_config(MagicMock(), FakeServerWithEnv()) is None

    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    def test_cmd_args_with_defaults(self, mock_find, mock_info, mock_input):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.side_effect = [
            "",
            "",
            "",
        ]  # name default, db_url default, optional empty
        result = prompt_for_server_config(MagicMock(), FakeServerWithArgs())
        assert result is not None
        assert result["cmd_args"]["db_url"] == "localhost"

    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    def test_cmd_args_custom_value(self, mock_find, mock_info, mock_input):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.side_effect = ["", "mydb://host", "flagval"]
        result = prompt_for_server_config(MagicMock(), FakeServerWithArgs())
        assert result["cmd_args"]["db_url"] == "mydb://host"
        assert result["cmd_args"]["optional_flag"] == "flagval"

    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    def test_cmd_args_required_missing(
        self, mock_find, mock_warn, mock_info, mock_input
    ):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        server = FakeServer()
        server.get_command_line_args = lambda: [
            {"name": "req", "prompt": "Required", "default": "", "required": True},
        ]
        mock_input.side_effect = ["", ""]  # name default, empty required
        assert prompt_for_server_config(MagicMock(), server) is None

    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    def test_cmd_args_interrupt(self, mock_find, mock_warn, mock_info, mock_input):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.side_effect = ["", KeyboardInterrupt]
        assert prompt_for_server_config(MagicMock(), FakeServerWithArgs()) is None

    @patch("code_puppy.config.set_config_value")
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    def test_env_var_empty_value_skipped(
        self, mock_find, mock_info, mock_input, mock_set_cfg
    ):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            prompt_for_server_config,
        )

        mock_input.side_effect = ["", "", ""]  # name default, empty env vars
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_TOKEN", None)
            os.environ.pop("GITHUB_TOKEN", None)
            result = prompt_for_server_config(MagicMock(), FakeServerWithEnv())
        assert result is not None
        assert "MY_TOKEN" not in result["env_vars"]


# ---------------------------------------------------------------------------
# install_catalog_server
# ---------------------------------------------------------------------------


class TestInstallCatalogServer:
    @patch(
        "code_puppy.command_line.mcp.wizard_utils.install_server_from_catalog",
        return_value=True,
    )
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_success")
    def test_success(self, mock_success, mock_info, mock_install):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            install_catalog_server,
        )

        config = {"name": "srv", "env_vars": {}, "cmd_args": {}}
        result = install_catalog_server(MagicMock(), FakeServer(), config)
        assert result is True
        mock_success.assert_called()

    @patch(
        "code_puppy.command_line.mcp.wizard_utils.install_server_from_catalog",
        return_value=False,
    )
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    def test_failure(self, mock_warn, mock_info, mock_install):
        from code_puppy.command_line.mcp.catalog_server_installer import (
            install_catalog_server,
        )

        config = {"name": "srv", "env_vars": {}, "cmd_args": {}}
        result = install_catalog_server(MagicMock(), FakeServer(), config)
        assert result is False
        mock_warn.assert_called()


# ---------------------------------------------------------------------------
# ENV_VAR_HINTS constant
# ---------------------------------------------------------------------------


class TestEnvVarHints:
    def test_hints_dict(self):
        from code_puppy.command_line.mcp.catalog_server_installer import ENV_VAR_HINTS

        assert isinstance(ENV_VAR_HINTS, dict)
        assert len(ENV_VAR_HINTS) > 0
        for key, val in ENV_VAR_HINTS.items():
            assert isinstance(key, str)
            assert isinstance(val, str)
