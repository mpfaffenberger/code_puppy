"""Tests for MCP search command."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def search_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.search_command import SearchCommand

        return SearchCommand()


def _make_server_template(
    id_,
    name,
    category="general",
    desc="A server",
    tags=None,
    verified=False,
    popular=False,
):
    s = MagicMock()
    s.id = id_
    s.display_name = name
    s.category = category
    s.description = desc
    s.tags = tags or ["tag1"]
    s.verified = verified
    s.popular = popular
    return s


class TestSearchCommand:
    def test_no_args_shows_popular(self, search_cmd):
        server = _make_server_template("s1", "Server1")
        mock_catalog = MagicMock()
        mock_catalog.get_popular.return_value = [server]

        with (
            patch("code_puppy.command_line.mcp.search_command.emit_info"),
            patch("code_puppy.command_line.mcp.search_command.emit_system_message"),
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.mcp_.server_registry_catalog": MagicMock(
                        catalog=mock_catalog
                    )
                },
            ),
        ):
            search_cmd.execute([], group_id="g1")
            mock_catalog.get_popular.assert_called_once_with(15)

    def test_generates_group_id(self, search_cmd):
        mock_catalog = MagicMock()
        mock_catalog.get_popular.return_value = []
        with (
            patch("code_puppy.command_line.mcp.search_command.emit_info"),
            patch("code_puppy.command_line.mcp.search_command.emit_warning"),
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.mcp_.server_registry_catalog": MagicMock(
                        catalog=mock_catalog
                    )
                },
            ),
        ):
            search_cmd.execute([])

    def test_with_query(self, search_cmd):
        server = _make_server_template("s1", "Server1")
        mock_catalog = MagicMock()
        mock_catalog.search.return_value = [server]

        with (
            patch("code_puppy.command_line.mcp.search_command.emit_info"),
            patch("code_puppy.command_line.mcp.search_command.emit_system_message"),
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.mcp_.server_registry_catalog": MagicMock(
                        catalog=mock_catalog
                    )
                },
            ),
        ):
            search_cmd.execute(["database"], group_id="g1")
            mock_catalog.search.assert_called_once_with("database")

    def test_no_results(self, search_cmd):
        mock_catalog = MagicMock()
        mock_catalog.search.return_value = []

        with (
            patch("code_puppy.command_line.mcp.search_command.emit_info") as _mock_emit,
            patch(
                "code_puppy.command_line.mcp.search_command.emit_warning"
            ) as mock_warn,
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.mcp_.server_registry_catalog": MagicMock(
                        catalog=mock_catalog
                    )
                },
            ),
        ):
            search_cmd.execute(["nonexistent"], group_id="g1")
            mock_warn.assert_called_once()

    def test_verified_and_popular_indicators(self, search_cmd):
        server = _make_server_template(
            "s1", "Server1", verified=True, popular=True, tags=["a", "b", "c", "d"]
        )
        mock_catalog = MagicMock()
        mock_catalog.search.return_value = [server]

        with (
            patch("code_puppy.command_line.mcp.search_command.emit_info"),
            patch("code_puppy.command_line.mcp.search_command.emit_system_message"),
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.mcp_.server_registry_catalog": MagicMock(
                        catalog=mock_catalog
                    )
                },
            ),
        ):
            search_cmd.execute(["test"], group_id="g1")

    def test_long_description_truncated(self, search_cmd):
        server = _make_server_template("s1", "Server1", desc="A" * 100)
        mock_catalog = MagicMock()
        mock_catalog.search.return_value = [server]

        with (
            patch("code_puppy.command_line.mcp.search_command.emit_info"),
            patch("code_puppy.command_line.mcp.search_command.emit_system_message"),
            patch.dict(
                "sys.modules",
                {
                    "code_puppy.mcp_.server_registry_catalog": MagicMock(
                        catalog=mock_catalog
                    )
                },
            ),
        ):
            search_cmd.execute(["test"], group_id="g1")

    def test_import_error(self, search_cmd):
        with (
            patch("code_puppy.command_line.mcp.search_command.emit_info") as _mock_emit,
            patch.dict(
                "sys.modules", {"code_puppy.mcp_.server_registry_catalog": None}
            ),
        ):
            search_cmd.execute([], group_id="g1")

    def test_generic_exception(self, search_cmd):
        mock_mod = MagicMock()
        mock_mod.catalog.get_popular.side_effect = Exception("boom")

        with (
            patch("code_puppy.command_line.mcp.search_command.emit_info") as _mock_emit,
            patch.dict(
                "sys.modules", {"code_puppy.mcp_.server_registry_catalog": mock_mod}
            ),
        ):
            search_cmd.execute([], group_id="g1")
