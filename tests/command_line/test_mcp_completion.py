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
        """`/mcp trust` must be discoverable via completion.

        It shipped routable-but-uncompletable, so users concluded it did not
        exist. Keep this alongside the parity test below: this one pins the
        specific regression, that one catches the whole class.
        """
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


# Bare `/mcp` already runs the list dashboard, so `list` is deliberately absent
# from completion. It is the sole sanctioned difference between the two sets.
COMPLETION_EXEMPT_SUBCOMMANDS = {"list"}

# Subcommands whose next argument is an MCP server name. Bucket membership is
# behavioural, not cosmetic: it decides whether `/mcp <cmd> <TAB>` offers server
# names. Putting a non-server command here makes it suggest nonsense.
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
    """The completer must not drift from the handler's routing table.

    `MCPCompleter` hand-maintains its subcommand dicts while
    `MCPCommandHandler` owns the real routing table. They drifted once already:
    `trust` was routable and documented in `/mcp help` but never completable,
    so users concluded it did not exist.

    Production completion code must NOT reach into the handler to fix this --
    `MCPCommandBase.__init__` calls `get_mcp_manager()`, and coupling passive
    completion metadata to live MCP runtime infrastructure would drag registry
    and config work into building the completion stack. So the two lists stay
    independent and this test enforces the invariant instead, constructing the
    handler only here with the manager patched out.
    """

    def _handler_subcommands(self):
        with patch("code_puppy.command_line.mcp.base.get_mcp_manager"):
            from code_puppy.command_line.mcp.handler import MCPCommandHandler

            return set(MCPCommandHandler()._commands)

    def test_completion_set_equals_routing_set(self):
        """Exact equality, deliberately bidirectional.

        Catches BOTH a routed subcommand missing from completion (the `trust`
        bug) AND a stale completion entry that no longer routes anywhere
        (which would tab-complete into an 'Unknown MCP subcommand' error).
        """
        completion = set(MCPCompleter().all_subcommands)
        routed = self._handler_subcommands()

        assert completion == routed - COMPLETION_EXEMPT_SUBCOMMANDS

    def test_exempt_subcommands_are_actually_routed(self):
        """Guard the guard: an exemption for a dead command would hide drift."""
        assert COMPLETION_EXEMPT_SUBCOMMANDS <= self._handler_subcommands()

    def test_server_bucket_holds_exactly_the_server_arg_commands(self):
        """Bucket assignment drives behaviour, so pin it.

        `all_subcommands` merges both dicts, so the parity test above cannot
        see WHICH bucket a name landed in. A non-server command placed in
        `server_subcommands` still completes at the top level -- but then
        `/mcp <cmd> <TAB>` offers MCP server names as its argument, which is
        meaningless for something like `trust` (it takes accept/revoke/status).
        That is the same catalogue-drift bug one layer down, and it is
        otherwise invisible to every other test in this file.
        """
        assert set(MCPCompleter().server_subcommands) == SERVER_ARG_SUBCOMMANDS

    def test_subcommand_buckets_do_not_overlap(self):
        """`all_subcommands` merges with `general` last, so an overlap would
        silently drop the server-argument behaviour for that name."""
        completer = MCPCompleter()
        assert not (
            set(completer.server_subcommands) & set(completer.general_subcommands)
        )
