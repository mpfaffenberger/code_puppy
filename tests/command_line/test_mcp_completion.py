"""Tests for mcp_completion.py - 100% coverage."""

from unittest.mock import MagicMock, patch

import pytest

from termflow.tui.completion import Document

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

    @pytest.mark.parametrize(
        ("doc", "extra"),
        [("/mcp ", "install"), ("/mcp st", "stop")],
        ids=["show_all_subcommands", "partial_subcommand"],
    )
    def test_subcommand_completions(self, doc, extra):
        result = self._get_completions(doc)
        names = [c.text for c in result]
        assert "start" in names
        assert extra in names
        # "list" is intentionally not offered: bare /mcp already does that.
        assert "list" not in names

    def test_trust_is_offered(self):
        """Shipped routable but uncompletable, so users concluded it did not exist."""
        names = [c.text for c in self._get_completions("/mcp ")]
        assert "trust" in names

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

    def test_get_server_names_none_returns_empty(self):
        self.completer._server_names_cache = None
        self.completer._cache_timestamp = None
        with patch(
            "code_puppy.command_line.mcp_completion.load_server_names",
            return_value=None,
        ):
            assert self.completer._get_server_names() == []


# Bare `/mcp` already runs the list dashboard, so `list` is deliberately
# uncompletable.
COMPLETION_EXEMPT_SUBCOMMANDS = {"list"}

# Hardcoded rather than derived from `server_subcommands` -- deriving it would
# make the assertion below tautological.
SERVER_ARG_SUBCOMMANDS = {
    "start",
    "stop",
    "restart",
    "status",
    "logs",
    "edit",
    "remove",
}


class TestCompletionMatchesRoutingTable:
    """Pins the completer to the handler's routing table.

    Production code deliberately does not import the handler to stay in sync:
    `MCPCommandBase.__init__` calls `get_mcp_manager()`, so that would drag MCP
    runtime into building a passive completion list. The lists stay
    independent and these tests enforce the invariant instead.
    """

    def _handler_subcommands(self):
        with patch("code_puppy.command_line.mcp.base.get_mcp_manager"):
            from code_puppy.command_line.mcp.handler import MCPCommandHandler

            return set(MCPCommandHandler()._commands)

    def test_completion_set_equals_routing_set(self):
        completion = set(MCPCompleter().all_subcommands)
        routed = self._handler_subcommands()

        assert completion == routed - COMPLETION_EXEMPT_SUBCOMMANDS

    def test_exempt_subcommands_are_actually_routed(self):
        """Stops drift being silenced by exempting a command that no longer exists."""
        assert COMPLETION_EXEMPT_SUBCOMMANDS <= self._handler_subcommands()

    def test_server_bucket_holds_exactly_the_server_arg_commands(self):
        """Bucket membership decides whether `/mcp <cmd> <TAB>` offers server
        names, and the merged-dict check above cannot see it."""
        assert set(MCPCompleter().server_subcommands) == SERVER_ARG_SUBCOMMANDS

    def test_subcommand_buckets_do_not_overlap(self):
        """`general` wins the merge, so an overlap would silently drop the
        server-argument behaviour."""
        completer = MCPCompleter()
        assert not (
            set(completer.server_subcommands) & set(completer.general_subcommands)
        )
