"""Tests for code_puppy/command_line/mcp/custom_server_installer.py"""

import json
from unittest.mock import MagicMock, patch

import pytest

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

    @pytest.mark.parametrize(
        "exc", [KeyboardInterrupt, EOFError], ids=["keyboard_interrupt", "eof"]
    )
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_info")
    @patch(f"{MODULE}.emit_warning")
    def test_name_input_aborted(self, mock_warn, mock_info, mock_input, exc):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = exc
        assert prompt_and_install_custom_server(MagicMock()) is False

    @pytest.mark.parametrize(
        "found,response",
        [
            ("existing", "n"),
            ("existing", KeyboardInterrupt),
            ("existing", EOFError),
            (None, "9"),
            (None, KeyboardInterrupt),
            (None, EOFError),
        ],
        ids=[
            "declined",
            "existing_keyboard_interrupt",
            "existing_eof",
            "invalid_choice",
            "no_existing_keyboard_interrupt",
            "no_existing_eof",
        ],
    )
    @patch(f"{UTILS}.find_server_id_by_name")
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_warning")
    @patch(f"{MODULE}.emit_info")
    def test_existing_server_and_type_prompts_handled(
        self, mock_info, mock_warn, mock_input, mock_find, response, found
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_find.return_value = found
        mock_input.side_effect = ["my-server", response]
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
    def test_empty_json(self, mock_info, mock_warn, mock_input, mock_find):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", "1", "", ""]
        assert prompt_and_install_custom_server(MagicMock()) is False

    @pytest.mark.parametrize(
        "type_idx,config",
        [
            ("1", "not json"),
            ("1", '{"args": []}'),
            ("2", '{"command": "x"}'),
            ("3", '{"command": "x"}'),
        ],
        ids=[
            "invalid_json",
            "stdio_missing_command",
            "http_missing_url",
            "sse_missing_url",
        ],
    )
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_error")
    @patch(f"{MODULE}.emit_info")
    def test_invalid_config_rejected(
        self, mock_info, mock_error, mock_input, mock_find, type_idx, config
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        mock_input.side_effect = ["my-server", type_idx, config, "", ""]
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

    @pytest.mark.parametrize(
        "type_idx,url",
        [
            ("2", "http://localhost:8080/mcp"),
            ("3", "http://localhost:8080/sse"),
        ],
        ids=["http", "sse"],
    )
    @patch(f"{UTILS}.find_server_id_by_name", return_value=None)
    @patch(f"{MODULE}.safe_input")
    @patch(f"{MODULE}.emit_success")
    @patch(f"{MODULE}.emit_info")
    def test_successful_url_install(
        self, mock_info, mock_success, mock_input, mock_find, tmp_path, type_idx, url
    ):
        from code_puppy.command_line.mcp.custom_server_installer import (
            prompt_and_install_custom_server,
        )

        config_json = json.dumps({"url": url})
        mock_input.side_effect = ["my-server", type_idx, config_json, "", ""]

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
