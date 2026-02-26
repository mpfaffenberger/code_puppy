"""Tests for code_puppy/command_line/mcp/custom_server_installer.py"""

import json
from unittest.mock import MagicMock, patch

MODULE = "code_puppy.command_line.mcp.custom_server_installer"
UTILS = "code_puppy.command_line.mcp.utils"


class TestPromptAndInstallCustomServer:
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    def test_empty_name_returns_false(self, mock_warn, mock_input):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.return_value = ""
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{MODULE}.safe_input", side_effect=KeyboardInterrupt)
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    def test_keyboard_interrupt_on_name(self, mock_warn, mock_info, mock_input):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{MODULE}.safe_input", side_effect=EOFError)
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    def test_eof_on_name(self, mock_warn, mock_info, mock_input):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value="existing")
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{MODULE}.emit_info")
    def test_existing_server_declined(
        self, mock_info, mock_warn, mock_input, mock_find
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", "n"]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value="existing")
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{MODULE}.emit_info")
    def test_existing_server_keyboard_interrupt(
        self, mock_info, mock_warn, mock_input, mock_find
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", KeyboardInterrupt]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value="existing")
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{MODULE}.emit_info")
    def test_existing_server_eof(self, mock_info, mock_warn, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", EOFError]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value="existing")
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{MODULE}.emit_info")
    def test_existing_server_override_accepted(
        self, mock_info, mock_warn, mock_input, mock_find
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        # name, override=yes, type=invalid -> will fail at type
        mock_input.side_effect = ["my-server", "y", "9"]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{MODULE}.emit_info")
    def test_invalid_type_choice(self, mock_info, mock_warn, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", "9"]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{MODULE}.emit_info")
    def test_type_keyboard_interrupt(self, mock_info, mock_warn, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", KeyboardInterrupt]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{MODULE}.emit_info")
    def test_type_eof(self, mock_info, mock_warn, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", EOFError]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{MODULE}.emit_info")
    def test_empty_json(self, mock_info, mock_warn, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", "1", "", ""]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_error")
    @patch(f"{MODULE}.emit_info")
    def test_invalid_json(self, mock_info, mock_error, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", "1", "not json", "", ""]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_error")
    @patch(f"{MODULE}.emit_info")
    def test_stdio_missing_command(self, mock_info, mock_error, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", "1", '{"args": []}', "", ""]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_error")
    @patch(f"{MODULE}.emit_info")
    def test_http_missing_url(self, mock_info, mock_error, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", "2", '{"command": "x"}', "", ""]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_error")
    @patch(f"{MODULE}.emit_info")
    def test_sse_missing_url(self, mock_info, mock_error, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", "3", '{"command": "x"}', "", ""]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_success")
    @patch(f"{MODULE}.emit_info")
    def test_successful_stdio_install(
        self, mock_info, mock_success, mock_input, mock_find, tmp_path
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        config_json = json.dumps({"command": "npx", "args": ["-y", "test"]})
        mock_input.side_effect = ["my-server", "1", config_json, "", ""]

        manager = MagicMock()
        manager.register_server.return_value = "srv-id"
        mcp_file = tmp_path / "mcp_servers.json"

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            result = prompt_and_install_custom_server(manager)
        assert result is True
        data = json.loads(mcp_file.read_text())
        assert "my-server" in data["mcp_servers"]

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_success")
    @patch(f"{MODULE}.emit_info")
    def test_successful_http_install(
        self, mock_info, mock_success, mock_input, mock_find, tmp_path
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        config_json = json.dumps({"url": "http://localhost:8080/mcp"})
        mock_input.side_effect = ["my-server", "2", config_json, "", ""]

        manager = MagicMock()
        manager.register_server.return_value = "srv-id"
        mcp_file = tmp_path / "mcp_servers.json"

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            result = prompt_and_install_custom_server(manager)
        assert result is True

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_success")
    @patch(f"{MODULE}.emit_info")
    def test_successful_sse_install(
        self, mock_info, mock_success, mock_input, mock_find, tmp_path
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        config_json = json.dumps({"url": "http://localhost:8080/sse"})
        mock_input.side_effect = ["my-server", "3", config_json, "", ""]

        manager = MagicMock()
        manager.register_server.return_value = "srv-id"
        mcp_file = tmp_path / "mcp_servers.json"

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            result = prompt_and_install_custom_server(manager)
        assert result is True

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_error")
    @patch(f"{MODULE}.emit_info")
    def test_register_fails(self, mock_info, mock_error, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        config_json = json.dumps({"command": "npx"})
        mock_input.side_effect = ["my-server", "1", config_json, "", ""]

        manager = MagicMock()
        manager.register_server.return_value = None

        result = prompt_and_install_custom_server(manager)
        assert result is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_error")
    @patch(f"{MODULE}.emit_info")
    def test_register_exception(self, mock_info, mock_error, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        config_json = json.dumps({"command": "npx"})
        mock_input.side_effect = ["my-server", "1", config_json, "", ""]

        manager = MagicMock()
        manager.register_server.side_effect = Exception("boom")

        result = prompt_and_install_custom_server(manager)
        assert result is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_success")
    @patch(f"{MODULE}.emit_info")
    def test_install_with_existing_config_file(
        self, mock_info, mock_success, mock_input, mock_find, tmp_path
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mcp_file = tmp_path / "mcp_servers.json"
        mcp_file.write_text(json.dumps({"mcp_servers": {"old": {}}}))

        config_json = json.dumps({"command": "npx"})
        mock_input.side_effect = ["new-srv", "1", config_json, "", ""]

        manager = MagicMock()
        manager.register_server.return_value = "id"

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_file)):
            result = prompt_and_install_custom_server(manager)
        assert result is True
        data = json.loads(mcp_file.read_text())
        assert "old" in data["mcp_servers"]
        assert "new-srv" in data["mcp_servers"]

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{MODULE}.emit_info")
    def test_json_input_keyboard_interrupt(
        self, mock_info, mock_warn, mock_input, mock_find
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", "1", KeyboardInterrupt]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_error")
    @patch(f"{MODULE}.emit_info")
    def test_json_input_multiline_invalid(
        self, mock_info, mock_error, mock_input, mock_find
    ):
        """Test multi-line JSON input that results in invalid JSON."""
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", "1", '{"command":', "", "bad}", "", ""]
        assert prompt_and_install_custom_server(MagicMock()) is False


class TestCustomServerExamples:
    def test_examples_exist(self):
        from code_puppy.command_line.mcp.custom_server_installer import (
            CUSTOM_SERVER_EXAMPLES,
        )

        assert "stdio" in CUSTOM_SERVER_EXAMPLES
        assert "http" in CUSTOM_SERVER_EXAMPLES
        assert "sse" in CUSTOM_SERVER_EXAMPLES
        for key, val in CUSTOM_SERVER_EXAMPLES.items():
            parsed = json.loads(val)
            assert isinstance(parsed, dict)
