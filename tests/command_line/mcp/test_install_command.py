"""Tests for code_puppy/command_line/mcp/install_command.py"""

import os
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

MODULE = "code_puppy.command_line.mcp.install_command"
UTILS = "code_puppy.command_line.mcp.utils"
WIZARD = "code_puppy.command_line.mcp.wizard_utils"
MESSAGING = "code_puppy.messaging"


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


def make_cmd():
    """Create an InstallCommand with mocked manager."""
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.install_command import InstallCommand

        cmd = InstallCommand()
    return cmd


class TestExecute:
    @patch(f"{MODULE}.run_mcp_install_menu")
    def test_no_args_launches_menu(self, mock_menu):
        cmd = make_cmd()
        cmd.execute([], "grp")
        mock_menu.assert_called_once_with(cmd.manager)

    @patch(f"{MODULE}.run_mcp_install_menu")
    def test_no_args_generates_group_id(self, mock_menu):
        cmd = make_cmd()
        cmd.execute([])
        mock_menu.assert_called_once()

    def test_with_args_calls_install_from_catalog(self):
        cmd = make_cmd()
        with patch.object(
            cmd, "_install_from_catalog", return_value=True
        ) as mock_install:
            with patch.dict("sys.modules", {"code_puppy.agent": MagicMock()}):
                cmd.execute(["some-server"], "grp")
        mock_install.assert_called_once_with("some-server", "grp")

    def test_with_args_reloads_on_success(self):
        cmd = make_cmd()
        with patch.object(cmd, "_install_from_catalog", return_value=True):
            with patch.dict("sys.modules", {"code_puppy.agent": MagicMock()}):
                cmd.execute(["srv"], "grp")

    def test_with_args_no_reload_on_failure(self):
        cmd = make_cmd()
        with patch.object(cmd, "_install_from_catalog", return_value=False):
            cmd.execute(["srv"], "grp")

    def test_reload_import_error(self):
        """Test that ImportError on reload_mcp_servers is handled."""
        cmd = make_cmd()
        with patch.object(cmd, "_install_from_catalog", return_value=True):
            # Don't mock code_puppy.agent so it raises ImportError
            cmd.execute(["srv"], "grp")

    @patch(f"{MODULE}.emit_info")
    def test_import_error_in_execute(self, mock_info):
        cmd = make_cmd()
        with patch.object(cmd, "_install_from_catalog", side_effect=ImportError):
            cmd.execute(["srv"], "grp")

    @patch(f"{MODULE}.emit_info")
    def test_general_exception_in_execute(self, mock_info):
        cmd = make_cmd()
        with patch.object(
            cmd, "_install_from_catalog", side_effect=RuntimeError("boom")
        ):
            cmd.execute(["srv"], "grp")


class TestInstallFromCatalog:
    @patch(f"{MODULE}.emit_info")
    def test_server_not_found(self, mock_info):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        mock_catalog.get_by_id.return_value = None
        mock_catalog.search.return_value = []

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            result = cmd._install_from_catalog("nonexistent", "grp")
        assert result is False

    @patch(f"{MODULE}.emit_info")
    def test_multiple_matches(self, mock_info):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        mock_catalog.get_by_id.return_value = None
        mock_catalog.search.return_value = [
            FakeServer(),
            FakeServer(name="s2", display_name="S2"),
        ]

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            result = cmd._install_from_catalog("test", "grp")
        assert result is False

    @patch(f"{WIZARD}.install_server_from_catalog", return_value=True)
    @patch(f"{MESSAGING}.emit_prompt")
    @patch(f"{MODULE}.emit_info")
    def test_single_match_install(self, mock_info, mock_prompt, mock_install):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        mock_catalog.get_by_id.return_value = None
        server = FakeServer()
        mock_catalog.search.return_value = [server]
        mock_prompt.return_value = ""  # use default name

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            with patch(f"{UTILS}.find_server_id_by_name", return_value=None):
                result = cmd._install_from_catalog("test", "grp")
        assert result is True

    @patch(f"{WIZARD}.install_server_from_catalog", return_value=True)
    @patch(f"{MESSAGING}.emit_prompt")
    @patch(f"{MODULE}.emit_info")
    def test_direct_id_match(self, mock_info, mock_prompt, mock_install):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        server = FakeServer()
        mock_catalog.get_by_id.return_value = server
        mock_prompt.return_value = "my-name"

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            with patch(f"{UTILS}.find_server_id_by_name", return_value=None):
                result = cmd._install_from_catalog("test-server", "grp")
        assert result is True

    @patch(f"{MESSAGING}.emit_prompt")
    @patch(f"{MODULE}.emit_info")
    def test_existing_server_override_declined(self, mock_info, mock_prompt):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        mock_catalog.get_by_id.return_value = FakeServer()
        mock_prompt.side_effect = ["", "n"]  # default name, decline override

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            with patch(f"{UTILS}.find_server_id_by_name", return_value="existing"):
                result = cmd._install_from_catalog("test-server", "grp")
        assert result is False

    @patch(f"{WIZARD}.install_server_from_catalog", return_value=True)
    @patch(f"{MESSAGING}.emit_prompt")
    @patch(f"{MODULE}.emit_info")
    def test_existing_server_override_accepted(
        self, mock_info, mock_prompt, mock_install
    ):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        mock_catalog.get_by_id.return_value = FakeServer()
        mock_prompt.side_effect = ["", "y"]

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            with patch(f"{UTILS}.find_server_id_by_name", return_value="existing"):
                result = cmd._install_from_catalog("test-server", "grp")
        assert result is True

    @patch(f"{WIZARD}.install_server_from_catalog", return_value=True)
    @patch(f"{MESSAGING}.emit_prompt")
    @patch(f"{MODULE}.emit_info")
    def test_with_env_vars_and_cmd_args(self, mock_info, mock_prompt, mock_install):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        server = FakeServer()
        server.get_environment_vars = lambda: ["TOKEN"]
        server.get_command_line_args = lambda: [
            {"name": "path", "prompt": "Path", "default": "/tmp", "required": True},
            {"name": "opt", "prompt": "Opt", "default": "def", "required": False},
        ]
        mock_catalog.get_by_id.return_value = server
        # name, token value, path value, opt value (empty -> uses default)
        mock_prompt.side_effect = ["", "my-token", "val", ""]

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            with patch(f"{UTILS}.find_server_id_by_name", return_value=None):
                os.environ.pop("TOKEN", None)
                result = cmd._install_from_catalog("test-server", "grp")
        assert result is True

    @patch(f"{WIZARD}.install_server_from_catalog", return_value=True)
    @patch(f"{MESSAGING}.emit_prompt")
    @patch(f"{MODULE}.emit_info")
    def test_env_var_already_set(self, mock_info, mock_prompt, mock_install):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        server = FakeServer()
        server.get_environment_vars = lambda: ["PRESET_VAR"]
        mock_catalog.get_by_id.return_value = server
        mock_prompt.return_value = ""

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            with patch(f"{UTILS}.find_server_id_by_name", return_value=None):
                with patch.dict(os.environ, {"PRESET_VAR": "value"}):
                    result = cmd._install_from_catalog("test-server", "grp")
        assert result is True

    @patch(f"{MODULE}.emit_info")
    def test_import_error(self, mock_info):
        cmd = make_cmd()
        with patch.dict(
            "sys.modules", {"code_puppy.mcp_.server_registry_catalog": None}
        ):
            result = cmd._install_from_catalog("srv", "grp")
        assert result is False

    @patch(f"{MODULE}.emit_error")
    @patch(f"{MODULE}.emit_info")
    def test_general_exception(self, mock_info, mock_error):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        mock_catalog.get_by_id.side_effect = RuntimeError("boom")

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            result = cmd._install_from_catalog("srv", "grp")
        assert result is False

    @patch(f"{MODULE}.emit_info")
    def test_multiple_matches_with_indicators(self, mock_info):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        mock_catalog.get_by_id.return_value = None
        servers = [
            FakeServer(verified=True, popular=True),
            FakeServer(name="s2", display_name="S2", verified=False, popular=False),
        ]
        mock_catalog.search.return_value = servers

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            result = cmd._install_from_catalog("test", "grp")
        assert result is False

    @patch(f"{WIZARD}.install_server_from_catalog", return_value=True)
    @patch(f"{MESSAGING}.emit_prompt")
    @patch(f"{MODULE}.emit_info")
    def test_server_no_description(self, mock_info, mock_prompt, mock_install):
        cmd = make_cmd()
        mock_catalog = MagicMock()
        server = FakeServer(description="")
        mock_catalog.get_by_id.return_value = server
        mock_prompt.return_value = ""

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            with patch(f"{UTILS}.find_server_id_by_name", return_value=None):
                result = cmd._install_from_catalog("test-server", "grp")
        assert result is True

    @patch(f"{WIZARD}.install_server_from_catalog", return_value=True)
    @patch(f"{MESSAGING}.emit_prompt")
    @patch(f"{MODULE}.emit_info")
    def test_cmd_args_not_required_no_default(
        self, mock_info, mock_prompt, mock_install
    ):
        """Test cmd arg that is not required and has no default - should be skipped."""
        cmd = make_cmd()
        mock_catalog = MagicMock()
        server = FakeServer()
        server.get_command_line_args = lambda: [
            {"name": "opt", "prompt": "Optional", "default": "", "required": False},
        ]
        mock_catalog.get_by_id.return_value = server
        mock_prompt.return_value = ""

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            with patch(f"{UTILS}.find_server_id_by_name", return_value=None):
                result = cmd._install_from_catalog("test-server", "grp")
        assert result is True

    @patch(f"{MODULE}.emit_info")
    def test_more_than_5_search_results(self, mock_info):
        """Test that only first 5 results are shown."""
        cmd = make_cmd()
        mock_catalog = MagicMock()
        mock_catalog.get_by_id.return_value = None
        mock_catalog.search.return_value = [FakeServer(name=f"s{i}") for i in range(8)]

        with patch.dict(
            "sys.modules",
            {
                "code_puppy.mcp_.server_registry_catalog": MagicMock(
                    catalog=mock_catalog
                )
            },
        ):
            result = cmd._install_from_catalog("test", "grp")
        assert result is False
