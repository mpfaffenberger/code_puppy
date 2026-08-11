"""Render-path tests for code_puppy/command_line/mcp/install_menu.py.

Split out of test_install_menu.py so both files stay under 600 lines.
"""

import os
from unittest.mock import MagicMock, patch

from tests.command_line.mcp.test_install_menu import FakeServer, make_menu


class TestRenderCategoryList:
    def test_renders_categories(self):
        menu = make_menu()
        menu.selected_category_idx = 0
        lines = menu._render_category_list()
        assert len(lines) > 0
        # Check header exists
        text = "".join(str(t[1]) for t in lines)
        assert "CATEGORIES" in text

    def test_renders_with_no_categories(self):
        menu = make_menu()
        menu.categories = []
        lines = menu._render_category_list()
        text = "".join(str(t[1]) for t in lines)
        assert "No categories" in text

    def test_pagination(self):
        menu = make_menu(catalog_categories=[f"Cat{i}" for i in range(20)])
        menu.current_page = 1
        menu.selected_category_idx = 12
        lines = menu._render_category_list()
        text = "".join(str(t[1]) for t in lines)
        assert "Page" in text

    def test_renders_with_no_catalog(self):
        menu = make_menu()
        menu.catalog = None
        menu.selected_category_idx = 1  # non-custom category
        lines = menu._render_category_list()
        text = "".join(str(t[1]) for t in lines)
        assert "(0)" in text  # zero server count when catalog is None

    def test_uses_semantic_tui_roles(self):
        menu = make_menu()
        menu.selected_category_idx = 1

        styles = {style for style, _text in menu._render_category_list() if style}

        assert {
            "class:tui.header",
            "class:tui.selected",
            "class:tui.help-key",
        } <= styles
        assert not any("fg:" in style or "ansi" in style for style in styles)


class TestRenderServerList:
    def test_no_category_selected(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_category = None
        lines = menu._render_server_list()
        text = "".join(str(t[1]) for t in lines)
        assert "No category" in text

    def test_empty_servers(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_category = "Code"
        menu.current_servers = []
        lines = menu._render_server_list()
        text = "".join(str(t[1]) for t in lines)
        assert "No servers" in text

    def test_renders_servers(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_category = "Code"
        menu.current_servers = [
            FakeServer(verified=True, popular=True),
            FakeServer(name="s2", display_name="S2", verified=False, popular=False),
        ]
        menu.selected_server_idx = 0
        lines = menu._render_server_list()
        text = "".join(str(t[1]) for t in lines)
        assert "Test Server" in text

    def test_server_pagination(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_category = "Code"
        menu.current_servers = [
            FakeServer(name=f"s{i}", display_name=f"S{i}") for i in range(20)
        ]
        menu.current_page = 1
        menu.selected_server_idx = 12
        lines = menu._render_server_list()
        text = "".join(str(t[1]) for t in lines)
        assert "Page" in text

    def test_server_details_use_semantic_status_roles(self, monkeypatch):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_servers = [FakeServer()]
        menu.selected_server_idx = 0
        monkeypatch.delenv("API_KEY", raising=False)

        styles = {style for style, _text in menu._render_details() if style}

        assert {"class:tui.label", "class:tui.muted", "class:tui.warning"} <= styles
        assert not any("fg:" in style or "ansi" in style for style in styles)


class TestRenderDetails:
    def test_no_category(self):
        menu = make_menu()
        menu.view_mode = "categories"
        menu.selected_category_idx = 999
        lines = menu._render_details()
        text = "".join(str(t[1]) for t in lines)
        assert "No category" in text

    def test_custom_server_details(self):
        menu = make_menu()
        menu.view_mode = "categories"
        menu.selected_category_idx = 0
        lines = menu._render_details()
        text = "".join(str(t[1]) for t in lines)
        assert "Custom" in text
        assert "stdio" in text

    def test_category_details_with_popular(self):
        menu = make_menu()
        menu.view_mode = "categories"
        menu.selected_category_idx = 1  # "Code" category
        popular_server = FakeServer(popular=True)
        menu.catalog.get_by_category.return_value = [popular_server]
        lines = menu._render_details()
        text = "".join(str(t[1]) for t in lines)
        assert "Popular" in text

    def test_category_details_no_popular(self):
        menu = make_menu()
        menu.view_mode = "categories"
        menu.selected_category_idx = 1
        menu.catalog.get_by_category.return_value = [FakeServer(popular=False)]
        lines = menu._render_details()
        text = "".join(str(t[1]) for t in lines)
        assert "1 servers" in text

    def test_server_details_full(self):
        menu = make_menu()
        menu.view_mode = "servers"
        srv = FakeServer(verified=True, popular=True)
        menu.current_servers = [srv]
        menu.selected_server_idx = 0
        with patch.dict(os.environ, {"API_KEY": "set"}):
            lines = menu._render_details()
        text = "".join(str(t[1]) for t in lines)
        assert "Test Server" in text
        assert "Verified" in text
        assert "Popular" in text
        assert "stdio" in text
        assert "test" in text  # tags
        assert "API_KEY" in text
        assert "Example" in text

    def test_server_details_no_description(self):
        menu = make_menu()
        menu.view_mode = "servers"
        srv = FakeServer(
            description="", tags=[], example_usage="", verified=False, popular=False
        )
        srv.get_environment_vars = lambda: []
        srv.get_command_line_args = lambda: []
        srv.get_requirements = lambda: MagicMock(required_tools=[])
        menu.current_servers = [srv]
        menu.selected_server_idx = 0
        lines = menu._render_details()
        text = "".join(str(t[1]) for t in lines)
        assert "No description" in text

    def test_server_details_unset_env_var(self):
        menu = make_menu()
        menu.view_mode = "servers"
        srv = FakeServer()
        menu.current_servers = [srv]
        menu.selected_server_idx = 0
        os.environ.pop("API_KEY", None)
        lines = menu._render_details()
        text = "".join(str(t[1]) for t in lines)
        assert "API_KEY" in text

    def test_no_server_selected(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_servers = []
        lines = menu._render_details()
        text = "".join(str(t[1]) for t in lines)
        assert "No server" in text

    def test_server_long_description_wraps(self):
        menu = make_menu()
        menu.view_mode = "servers"
        srv = FakeServer(description="word " * 50)
        srv.get_environment_vars = lambda: []
        srv.get_command_line_args = lambda: []
        srv.get_requirements = lambda: MagicMock(required_tools=[])
        menu.current_servers = [srv]
        menu.selected_server_idx = 0
        lines = menu._render_details()
        # Should have multiple description lines
        assert len(lines) > 5
