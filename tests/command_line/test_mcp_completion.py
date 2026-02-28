"""Tests for mcp_completion.py - 100% coverage."""

from unittest.mock import MagicMock, patch

from prompt_toolkit.document import Document

from code_puppy.command_line.mcp_completion import MCPCompleter, load_server_names


class TestLoadServerNames:
    @patch("code_puppy.mcp_.manager.MCPManager")
    def test_success(self, mock_mgr_cls):
        mock_server = MagicMock()
        mock_server.name = "test-server"
        mock_mgr_cls.return_value.list_servers.return_value = [mock_server]
        result = load_server_names()
        assert isinstance(result, list)

    def test_failure(self):
        with patch("code_puppy.mcp_.manager.MCPManager", side_effect=Exception("err")):
            result = load_server_names()
            assert result == []


class TestMCPCompleter:
    def setup_method(self):
        self.completer = MCPCompleter()
        self.event = MagicMock()

    def _get_completions(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        doc = Document(text, cursor_pos)
        return list(self.completer.get_completions(doc, self.event))

    def test_no_trigger(self):
        assert self._get_completions("hello") == []

    def test_trigger_no_space(self):
        assert self._get_completions("/mcp") == []

    def test_show_all_subcommands(self):
        result = self._get_completions("/mcp ")
        names = [c.text for c in result]
        assert "start" in names
        assert "list" in names
        assert "install" in names

    def test_partial_subcommand(self):
        result = self._get_completions("/mcp st")
        names = [c.text for c in result]
        assert "start" in names
        assert "stop" in names
        assert "list" not in names

    @patch.object(
        MCPCompleter, "_get_server_names", return_value=["server-a", "server-b"]
    )
    def test_server_subcommand_show_servers(self, mock_names):
        result = self._get_completions("/mcp start ")
        names = [c.text for c in result]
        assert "server-a" in names
        assert "server-b" in names

    @patch.object(MCPCompleter, "_get_server_names", return_value=["alpha", "beta"])
    def test_server_subcommand_filter(self, mock_names):
        result = self._get_completions("/mcp start al")
        names = [c.text for c in result]
        assert "alpha" in names
        assert "beta" not in names

    def test_general_subcommand_no_further(self):
        result = self._get_completions("/mcp list ")
        assert result == []

    def test_get_server_names_cache(self):
        self.completer._server_names_cache = ["cached"]
        self.completer._cache_timestamp = 999999999999.0
        result = self.completer._get_server_names()
        assert result == ["cached"]

    def test_get_server_names_refresh(self):
        self.completer._server_names_cache = None
        self.completer._cache_timestamp = None
        with patch(
            "code_puppy.command_line.mcp_completion.load_server_names",
            return_value=["new"],
        ):
            result = self.completer._get_server_names()
            assert result == ["new"]
