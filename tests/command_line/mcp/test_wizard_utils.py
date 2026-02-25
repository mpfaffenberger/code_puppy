"""Tests for code_puppy/command_line/mcp/wizard_utils.py"""

import json
import os
from dataclasses import dataclass
from unittest.mock import MagicMock, patch


@dataclass
class FakeServer:
    name: str = "test-server"
    display_name: str = "Test Server"
    description: str = "A test server"
    type: str = "stdio"
    verified: bool = True
    popular: bool = False
    id: str = "test-server"

    def get_environment_vars(self):
        return []

    def get_command_line_args(self):
        return []

    def to_server_config(self, name, **kwargs):
        return {"command": "npx", "args": ["-y", "test"], "env": {}}


class TestInteractiveServerSelection:
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_select_server_valid(self, mock_info, mock_prompt):
        from code_puppy.command_line.mcp.wizard_utils import (
            interactive_server_selection,
        )

        servers = [FakeServer(), FakeServer(name="s2", display_name="S2", popular=True)]
        mock_catalog = MagicMock()
        mock_catalog.get_popular.return_value = servers
        mock_prompt.return_value = "1"

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            result = interactive_server_selection("grp")
        assert result == servers[0]

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_select_server_quit(self, mock_info, mock_prompt):
        from code_puppy.command_line.mcp.wizard_utils import (
            interactive_server_selection,
        )

        mock_catalog = MagicMock()
        mock_catalog.get_popular.return_value = [FakeServer()]
        mock_prompt.return_value = "q"

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            result = interactive_server_selection("grp")
        assert result is None

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_select_server_invalid_number(self, mock_info, mock_prompt):
        from code_puppy.command_line.mcp.wizard_utils import (
            interactive_server_selection,
        )

        mock_catalog = MagicMock()
        mock_catalog.get_popular.return_value = [FakeServer()]
        mock_prompt.return_value = "99"

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            result = interactive_server_selection("grp")
        assert result is None

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_select_server_non_numeric(self, mock_info, mock_prompt):
        from code_puppy.command_line.mcp.wizard_utils import (
            interactive_server_selection,
        )

        mock_catalog = MagicMock()
        mock_catalog.get_popular.return_value = [FakeServer()]
        mock_prompt.return_value = "abc"

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            result = interactive_server_selection("grp")
        assert result is None

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_select_server_no_servers(self, mock_info):
        from code_puppy.command_line.mcp.wizard_utils import (
            interactive_server_selection,
        )

        mock_catalog = MagicMock()
        mock_catalog.get_popular.return_value = []

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            result = interactive_server_selection("grp")
        assert result is None

    def test_select_server_import_error(self):
        from code_puppy.command_line.mcp.wizard_utils import (
            interactive_server_selection,
        )

        with patch.dict(
            "sys.modules", {"code_puppy.mcp_.server_registry_catalog": None}
        ):
            result = interactive_server_selection("grp")
        assert result is None


class TestInteractiveGetServerName:
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    def test_custom_name(self, mock_prompt):
        from code_puppy.command_line.mcp.wizard_utils import interactive_get_server_name

        mock_prompt.return_value = "my-name"
        server = FakeServer()
        result = interactive_get_server_name(server, "grp")
        assert result == "my-name"

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    def test_default_name(self, mock_prompt):
        from code_puppy.command_line.mcp.wizard_utils import interactive_get_server_name

        mock_prompt.return_value = "  "
        server = FakeServer(name="default-name")
        result = interactive_get_server_name(server, "grp")
        assert result == "default-name"


class TestInteractiveConfigureServer:
    @patch("code_puppy.command_line.mcp.wizard_utils.install_server_from_catalog")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_new_server_confirmed(self, mock_info, mock_prompt, mock_install):
        from code_puppy.command_line.mcp.wizard_utils import (
            interactive_configure_server,
        )

        mock_prompt.return_value = "y"
        mock_install.return_value = True

        with patch(
            "code_puppy.command_line.mcp.utils.find_server_id_by_name",
            return_value=None,
        ):
            result = interactive_configure_server(
                MagicMock(), FakeServer(), "srv", "grp", {"KEY": "val"}, {"arg": "v"}
            )
        assert result is True

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_existing_server_declined(self, mock_info, mock_prompt):
        from code_puppy.command_line.mcp.wizard_utils import (
            interactive_configure_server,
        )

        mock_prompt.return_value = "n"

        with patch(
            "code_puppy.command_line.mcp.utils.find_server_id_by_name",
            return_value="existing-id",
        ):
            result = interactive_configure_server(
                MagicMock(), FakeServer(), "srv", "grp", {}, {}
            )
        assert result is False

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_cancelled_at_confirm(self, mock_info, mock_prompt):
        from code_puppy.command_line.mcp.wizard_utils import (
            interactive_configure_server,
        )

        mock_prompt.return_value = "n"

        with patch(
            "code_puppy.command_line.mcp.utils.find_server_id_by_name",
            return_value=None,
        ):
            result = interactive_configure_server(
                MagicMock(), FakeServer(), "srv", "grp", {}, {}
            )
        assert result is False

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_error")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_exception_handling(self, mock_info, mock_prompt, mock_error):
        from code_puppy.command_line.mcp.wizard_utils import (
            interactive_configure_server,
        )

        with patch(
            "code_puppy.command_line.mcp.utils.find_server_id_by_name",
            side_effect=Exception("boom"),
        ):
            result = interactive_configure_server(
                MagicMock(), FakeServer(), "srv", "grp", {}, {}
            )
        assert result is False


class TestInstallServerFromCatalog:
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_successful_install(self, mock_info, tmp_path):
        from code_puppy.command_line.mcp.wizard_utils import install_server_from_catalog

        server = FakeServer()
        manager = MagicMock()
        manager.register_server.return_value = "srv-id"

        mcp_file = tmp_path / "mcp_servers.json"

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            result = install_server_from_catalog(
                manager, server, "my-srv", {}, {}, "grp"
            )
        assert result is True
        assert mcp_file.exists()
        data = json.loads(mcp_file.read_text())
        assert "my-srv" in data["mcp_servers"]

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_install_with_existing_file(self, mock_info, tmp_path):
        from code_puppy.command_line.mcp.wizard_utils import install_server_from_catalog

        mcp_file = tmp_path / "mcp_servers.json"
        mcp_file.write_text(json.dumps({"mcp_servers": {"old": {}}}))

        server = FakeServer()
        manager = MagicMock()
        manager.register_server.return_value = "srv-id"

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            result = install_server_from_catalog(
                manager, server, "new-srv", {}, {}, "grp"
            )
        assert result is True
        data = json.loads(mcp_file.read_text())
        assert "old" in data["mcp_servers"]
        assert "new-srv" in data["mcp_servers"]

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_install_with_env_var_replacement(self, mock_info, tmp_path):
        from code_puppy.command_line.mcp.wizard_utils import install_server_from_catalog

        server = FakeServer()
        server.to_server_config = lambda name, **kw: {
            "command": "npx",
            "env": {"TOKEN": "$MY_TOKEN"},
        }
        manager = MagicMock()
        manager.register_server.return_value = "srv-id"
        mcp_file = tmp_path / "mcp_servers.json"

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            result = install_server_from_catalog(
                manager, server, "srv", {"MY_TOKEN": "secret"}, {}, "grp"
            )
        assert result is True

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_error")
    def test_register_fails(self, mock_error, mock_info, tmp_path):
        from code_puppy.command_line.mcp.wizard_utils import install_server_from_catalog

        server = FakeServer()
        manager = MagicMock()
        manager.register_server.return_value = None

        mcp_file = tmp_path / "mcp_servers.json"
        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            result = install_server_from_catalog(manager, server, "srv", {}, {}, "grp")
        assert result is False

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_error")
    def test_exception_during_install(self, mock_error):
        from code_puppy.command_line.mcp.wizard_utils import install_server_from_catalog

        server = FakeServer()
        server.to_server_config = MagicMock(side_effect=Exception("boom"))
        manager = MagicMock()

        result = install_server_from_catalog(manager, server, "srv", {}, {}, "grp")
        assert result is False


class TestRunInteractiveInstallWizard:
    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_configure_server",
        return_value=True,
    )
    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_get_server_name",
        return_value="my-srv",
    )
    @patch("code_puppy.command_line.mcp.wizard_utils.interactive_server_selection")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_full_wizard_no_env_no_args(
        self, mock_info, mock_select, mock_name, mock_config
    ):
        from code_puppy.command_line.mcp.wizard_utils import (
            run_interactive_install_wizard,
        )

        mock_select.return_value = FakeServer()
        result = run_interactive_install_wizard(MagicMock(), "grp")
        assert result is True

    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_server_selection",
        return_value=None,
    )
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_wizard_cancelled_at_selection(self, mock_info, mock_select):
        from code_puppy.command_line.mcp.wizard_utils import (
            run_interactive_install_wizard,
        )

        result = run_interactive_install_wizard(MagicMock(), "grp")
        assert result is False

    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_get_server_name",
        return_value=None,
    )
    @patch("code_puppy.command_line.mcp.wizard_utils.interactive_server_selection")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_wizard_cancelled_at_name(self, mock_info, mock_select, mock_name):
        from code_puppy.command_line.mcp.wizard_utils import (
            run_interactive_install_wizard,
        )

        mock_select.return_value = FakeServer()
        result = run_interactive_install_wizard(MagicMock(), "grp")
        assert result is False

    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_configure_server",
        return_value=True,
    )
    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_get_server_name",
        return_value="srv",
    )
    @patch("code_puppy.command_line.mcp.wizard_utils.interactive_server_selection")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_wizard_with_env_vars_and_cmd_args(
        self, mock_info, mock_prompt, mock_select, mock_name, mock_config
    ):
        from code_puppy.command_line.mcp.wizard_utils import (
            run_interactive_install_wizard,
        )

        server = FakeServer()
        server.get_environment_vars = lambda: ["API_KEY"]
        server.get_command_line_args = lambda: [
            {
                "name": "path",
                "prompt": "Enter path",
                "default": "/tmp",
                "required": True,
            },
            {"name": "opt", "prompt": "Optional", "default": "", "required": False},
        ]
        mock_select.return_value = server
        mock_prompt.return_value = "value"

        with patch.dict(os.environ, {}, clear=False):
            # Make sure API_KEY is not set
            os.environ.pop("API_KEY", None)
            result = run_interactive_install_wizard(MagicMock(), "grp")
        assert result is True

    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_configure_server",
        return_value=True,
    )
    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_get_server_name",
        return_value="srv",
    )
    @patch("code_puppy.command_line.mcp.wizard_utils.interactive_server_selection")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_wizard_cmd_arg_not_required_no_default(
        self, mock_info, mock_prompt, mock_select, mock_name, mock_config
    ):
        """Test cmd arg that is not required and has no default - should be skipped."""
        from code_puppy.command_line.mcp.wizard_utils import (
            run_interactive_install_wizard,
        )

        server = FakeServer()
        server.get_command_line_args = lambda: [
            {"name": "opt", "prompt": "Optional", "default": "", "required": False},
        ]
        mock_select.return_value = server

        result = run_interactive_install_wizard(MagicMock(), "grp")
        assert result is True

    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_configure_server",
        return_value=True,
    )
    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_get_server_name",
        return_value="srv",
    )
    @patch("code_puppy.command_line.mcp.wizard_utils.interactive_server_selection")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_wizard_cmd_arg_empty_value_uses_default(
        self, mock_info, mock_prompt, mock_select, mock_name, mock_config
    ):
        """Test cmd arg where user enters empty value and default is used."""
        from code_puppy.command_line.mcp.wizard_utils import (
            run_interactive_install_wizard,
        )

        server = FakeServer()
        server.get_command_line_args = lambda: [
            {"name": "path", "prompt": "Path", "default": "/tmp", "required": True},
        ]
        mock_select.return_value = server
        mock_prompt.return_value = ""  # empty -> uses default

        result = run_interactive_install_wizard(MagicMock(), "grp")
        assert result is True

    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_configure_server",
        return_value=True,
    )
    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_get_server_name",
        return_value="srv",
    )
    @patch("code_puppy.command_line.mcp.wizard_utils.interactive_server_selection")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_wizard_cmd_arg_not_required_with_default_empty_input(
        self, mock_info, mock_prompt, mock_select, mock_name, mock_config
    ):
        """Test optional cmd arg with default where user enters empty -> uses default."""
        from code_puppy.command_line.mcp.wizard_utils import (
            run_interactive_install_wizard,
        )

        server = FakeServer()
        server.get_command_line_args = lambda: [
            {"name": "opt", "prompt": "Opt", "default": "def", "required": False},
        ]
        mock_select.return_value = server
        mock_prompt.return_value = ""  # empty -> uses default

        result = run_interactive_install_wizard(MagicMock(), "grp")
        assert result is True

    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_configure_server",
        return_value=True,
    )
    @patch(
        "code_puppy.command_line.mcp.wizard_utils.interactive_get_server_name",
        return_value="srv",
    )
    @patch("code_puppy.command_line.mcp.wizard_utils.interactive_server_selection")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_prompt")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_wizard_env_var_already_set(
        self, mock_info, mock_prompt, mock_select, mock_name, mock_config
    ):
        from code_puppy.command_line.mcp.wizard_utils import (
            run_interactive_install_wizard,
        )

        server = FakeServer()
        server.get_environment_vars = lambda: ["EXISTING_VAR"]
        mock_select.return_value = server

        with patch.dict(os.environ, {"EXISTING_VAR": "already-set"}):
            result = run_interactive_install_wizard(MagicMock(), "grp")
        assert result is True

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_error")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_wizard_general_exception(self, mock_info, mock_error):
        from code_puppy.command_line.mcp.wizard_utils import (
            run_interactive_install_wizard,
        )

        with patch(
            "code_puppy.command_line.mcp.wizard_utils.interactive_server_selection",
            side_effect=RuntimeError("boom"),
        ):
            result = run_interactive_install_wizard(MagicMock(), "grp")
        assert result is False

    @patch("code_puppy.command_line.mcp.wizard_utils.emit_error")
    @patch("code_puppy.command_line.mcp.wizard_utils.emit_info")
    def test_wizard_import_error(self, mock_info, mock_error):
        from code_puppy.command_line.mcp.wizard_utils import (
            run_interactive_install_wizard,
        )

        with patch(
            "code_puppy.command_line.mcp.wizard_utils.interactive_server_selection",
            side_effect=ImportError("no module"),
        ):
            result = run_interactive_install_wizard(MagicMock(), "grp")
        assert result is False
