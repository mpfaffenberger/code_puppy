"""Tests for code_puppy/command_line/mcp/install_menu.py"""

import os
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

MODULE = "code_puppy.command_line.mcp.install_menu"


@dataclass
class FakeServer:
    name: str = "test-server"
    display_name: str = "Test Server"
    description: str = "A test server description that is fairly long for wrapping"
    type: str = "stdio"
    verified: bool = True
    popular: bool = False
    id: str = "test-server"
    tags: list = None
    example_usage: str = "test --help"

    def __post_init__(self):
        if self.tags is None:
            self.tags = ["test", "dev"]

    def get_environment_vars(self):
        return ["API_KEY"]

    def get_command_line_args(self):
        return [{"name": "path", "required": True, "default": "/tmp"}]

    def get_requirements(self):
        return MagicMock(required_tools=["npx", "node"])


def make_menu(catalog_categories=None, catalog_servers=None):
    """Create MCPInstallMenu with mocked catalog."""
    mock_catalog = MagicMock()
    mock_catalog.list_categories.return_value = catalog_categories or [
        "Code",
        "Storage",
    ]
    mock_catalog.get_by_category.return_value = catalog_servers or [FakeServer()]
    mock_catalog.get_popular.return_value = catalog_servers or [FakeServer()]

    with patch.dict(
        "sys.modules",
        {"code_puppy.mcp_.server_registry_catalog": MagicMock(catalog=mock_catalog)},
    ):
        from code_puppy.command_line.mcp.install_menu import MCPInstallMenu

        menu = MCPInstallMenu(MagicMock())
        menu.catalog = mock_catalog
        menu.categories = ["➕ Custom Server"] + (
            catalog_categories or ["Code", "Storage"]
        )
    return menu


class TestMCPInstallMenuInit:
    def test_init_with_catalog(self):
        menu = make_menu()
        assert len(menu.categories) >= 2
        assert menu.categories[0] == "➕ Custom Server"
        assert menu.view_mode == "categories"

    def test_init_catalog_import_error(self):
        with patch.dict(
            "sys.modules", {"code_puppy.mcp_.server_registry_catalog": None}
        ):
            from code_puppy.command_line.mcp.install_menu import MCPInstallMenu

            with patch(f"{MODULE}.emit_error"):
                menu = MCPInstallMenu(MagicMock())
        assert menu.categories == ["➕ Custom Server"]

    def test_init_catalog_general_exception(self):
        mock_mod = MagicMock()
        mock_mod.catalog.list_categories.side_effect = RuntimeError("boom")
        with patch.dict(
            "sys.modules", {"code_puppy.mcp_.server_registry_catalog": mock_mod}
        ):
            from code_puppy.command_line.mcp.install_menu import MCPInstallMenu

            with patch(f"{MODULE}.emit_error"):
                menu = MCPInstallMenu(MagicMock())
        assert menu.categories == ["➕ Custom Server"]

    def test_init_empty_catalog(self):
        mock_mod = MagicMock()
        mock_mod.catalog.list_categories.return_value = []
        with patch.dict(
            "sys.modules", {"code_puppy.mcp_.server_registry_catalog": mock_mod}
        ):
            from code_puppy.command_line.mcp.install_menu import MCPInstallMenu

            with patch(f"{MODULE}.emit_error"):
                menu = MCPInstallMenu(MagicMock())
        # Only custom category
        assert len(menu.categories) == 1


class TestGetters:
    def test_get_current_category(self):
        menu = make_menu()
        menu.selected_category_idx = 0
        assert menu._get_current_category() == "➕ Custom Server"

    def test_get_current_category_out_of_range(self):
        menu = make_menu()
        menu.selected_category_idx = 999
        assert menu._get_current_category() is None

    def test_get_current_server_no_servers(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_servers = []
        assert menu._get_current_server() is None

    def test_get_current_server_valid(self):
        menu = make_menu()
        menu.view_mode = "servers"
        srv = FakeServer()
        menu.current_servers = [srv]
        menu.selected_server_idx = 0
        assert menu._get_current_server() == srv

    def test_get_current_server_categories_mode(self):
        menu = make_menu()
        menu.view_mode = "categories"
        menu.current_servers = [FakeServer()]
        assert menu._get_current_server() is None

    def test_get_current_server_out_of_range(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_servers = [FakeServer()]
        menu.selected_server_idx = 99
        assert menu._get_current_server() is None


class TestCategoryIcon:
    def test_custom_server_icon(self):
        menu = make_menu()
        assert menu._get_category_icon("➕ Custom Server") == "➕"

    def test_known_category_icon(self):
        menu = make_menu()
        assert menu._get_category_icon("Code") == "💻"
        assert menu._get_category_icon("Storage") == "💾"

    def test_unknown_category_icon(self):
        menu = make_menu()
        assert menu._get_category_icon("Unknown") == "📁"


class TestIsCustomServerSelected:
    def test_custom_selected(self):
        menu = make_menu()
        menu.view_mode = "categories"
        menu.selected_category_idx = 0
        assert menu._is_custom_server_selected() is True

    def test_not_custom(self):
        menu = make_menu()
        menu.view_mode = "categories"
        menu.selected_category_idx = 1
        assert menu._is_custom_server_selected() is False

    def test_servers_mode(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.selected_category_idx = 0
        assert menu._is_custom_server_selected() is False


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


class TestNavigation:
    def test_enter_category(self):
        menu = make_menu()
        menu.selected_category_idx = 1  # "Code"
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu._enter_category()
        assert menu.view_mode == "servers"
        assert menu.current_category == "Code"

    def test_enter_custom_server(self):
        menu = make_menu()
        menu.selected_category_idx = 0
        menu._enter_category()
        assert menu.result == "pending_custom"

    def test_enter_no_category(self):
        menu = make_menu()
        menu.selected_category_idx = 999
        menu._enter_category()
        assert menu.view_mode == "categories"

    def test_enter_no_catalog(self):
        menu = make_menu()
        menu.catalog = None
        menu.selected_category_idx = 1
        menu._enter_category()
        assert menu.view_mode == "categories"

    def test_go_back(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_category = "Code"
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu._go_back_to_categories()
        assert menu.view_mode == "categories"
        assert menu.current_category is None

    def test_select_server(self):
        menu = make_menu()
        menu.view_mode = "servers"
        srv = FakeServer()
        menu.current_servers = [srv]
        menu.selected_server_idx = 0
        menu._select_current_server()
        assert menu.pending_server == srv
        assert menu.result == "pending_install"

    def test_select_no_server(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_servers = []
        menu._select_current_server()
        assert menu.pending_server is None


class TestRun:
    @patch(f"{MODULE}.emit_warning")
    def test_no_categories(self, mock_warn):
        menu = make_menu()
        menu.categories = []
        result = menu.run()
        assert result is False

    @patch(f"{MODULE}.set_awaiting_user_input")
    @patch("sys.stdout")
    def test_run_exits_normally(self, mock_stdout, mock_set_input):
        menu = make_menu()
        menu.result = None
        mock_app = MagicMock()

        with patch(f"{MODULE}.Application", return_value=mock_app):
            with patch(f"{MODULE}.emit_info"):
                result = menu.run()
        assert result is False

    @patch(f"{MODULE}.set_awaiting_user_input")
    @patch(f"{MODULE}.run_custom_server_form", return_value=True)
    @patch("sys.stdout")
    def test_run_custom_server(self, mock_stdout, mock_form, mock_set_input):
        menu = make_menu()

        mock_app = MagicMock()

        # Make the app.run set pending_custom
        def fake_run(**kwargs):
            menu.result = "pending_custom"

        mock_app.run = fake_run

        with patch(f"{MODULE}.Application", return_value=mock_app):
            with patch.dict("sys.modules", {"code_puppy.agent": MagicMock()}):
                result = menu.run()
        assert result is True

    @patch(f"{MODULE}.set_awaiting_user_input")
    @patch(f"{MODULE}.prompt_for_server_config", return_value={"name": "srv"})
    @patch(f"{MODULE}.install_catalog_server", return_value=True)
    @patch("sys.stdout")
    def test_run_catalog_install(
        self, mock_stdout, mock_install, mock_prompt, mock_set_input
    ):
        menu = make_menu()
        srv = FakeServer()

        mock_app = MagicMock()

        def fake_run(**kwargs):
            menu.result = "pending_install"
            menu.pending_server = srv

        mock_app.run = fake_run

        with patch(f"{MODULE}.Application", return_value=mock_app):
            with patch.dict("sys.modules", {"code_puppy.agent": MagicMock()}):
                result = menu.run()
        assert result is True

    @patch(f"{MODULE}.set_awaiting_user_input")
    @patch(f"{MODULE}.prompt_for_server_config", return_value=None)
    @patch("sys.stdout")
    def test_run_catalog_config_cancelled(
        self, mock_stdout, mock_prompt, mock_set_input
    ):
        menu = make_menu()
        srv = FakeServer()

        mock_app = MagicMock()

        def fake_run(**kwargs):
            menu.result = "pending_install"
            menu.pending_server = srv

        mock_app.run = fake_run

        with patch(f"{MODULE}.Application", return_value=mock_app):
            result = menu.run()
        assert result is False

    @patch(f"{MODULE}.set_awaiting_user_input")
    @patch(f"{MODULE}.run_custom_server_form", return_value=False)
    @patch("sys.stdout")
    def test_run_custom_server_fails(self, mock_stdout, mock_form, mock_set_input):
        menu = make_menu()

        mock_app = MagicMock()

        def fake_run(**kwargs):
            menu.result = "pending_custom"

        mock_app.run = fake_run

        with patch(f"{MODULE}.Application", return_value=mock_app):
            result = menu.run()
        assert result is False


class TestRunMcpInstallMenu:
    @patch(f"{MODULE}.MCPInstallMenu")
    def test_delegates_to_menu(self, MockMenu):
        from code_puppy.command_line.mcp.install_menu import run_mcp_install_menu

        mock_instance = MagicMock()
        mock_instance.run.return_value = True
        MockMenu.return_value = mock_instance

        result = run_mcp_install_menu(MagicMock())
        assert result is True
        MockMenu.assert_called_once()


class TestRenderNavigationHints:
    def test_categories_mode(self):
        menu = make_menu()
        menu.view_mode = "categories"
        lines = []
        menu._render_navigation_hints(lines)
        text = "".join(str(t[1]) for t in lines)
        assert "Browse Servers" in text
        assert "Cancel" in text

    def test_servers_mode(self):
        menu = make_menu()
        menu.view_mode = "servers"
        lines = []
        menu._render_navigation_hints(lines)
        text = "".join(str(t[1]) for t in lines)
        assert "Install Server" in text
        assert "Back" in text


class TestRenderCustomServerDetails:
    def test_renders(self):
        menu = make_menu()
        lines = menu._render_custom_server_details()
        text = "".join(str(t[1]) for t in lines)
        assert "Custom" in text
        assert "stdio" in text
        assert "http" in text
        assert "sse" in text


class TestKeyHandlers:
    def test_handle_up_categories(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "categories"
        menu.selected_category_idx = 2
        menu._handle_up()
        assert menu.selected_category_idx == 1

    def test_handle_up_categories_at_top(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "categories"
        menu.selected_category_idx = 0
        menu._handle_up()
        assert menu.selected_category_idx == 0

    def test_handle_up_servers(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "servers"
        menu.current_servers = [FakeServer(), FakeServer()]
        menu.selected_server_idx = 1
        menu._handle_up()
        assert menu.selected_server_idx == 0

    def test_handle_up_servers_at_top(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "servers"
        menu.current_servers = [FakeServer()]
        menu.selected_server_idx = 0
        menu._handle_up()
        assert menu.selected_server_idx == 0

    def test_handle_down_categories(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "categories"
        menu.selected_category_idx = 0
        menu._handle_down()
        assert menu.selected_category_idx == 1

    def test_handle_down_categories_at_bottom(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "categories"
        menu.selected_category_idx = len(menu.categories) - 1
        menu._handle_down()
        assert menu.selected_category_idx == len(menu.categories) - 1

    def test_handle_down_servers(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "servers"
        menu.current_servers = [FakeServer(), FakeServer()]
        menu.selected_server_idx = 0
        menu._handle_down()
        assert menu.selected_server_idx == 1

    def test_handle_down_servers_at_bottom(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "servers"
        menu.current_servers = [FakeServer()]
        menu.selected_server_idx = 0
        menu._handle_down()
        assert menu.selected_server_idx == 0

    def test_handle_left_categories(self):
        menu = make_menu(catalog_categories=[f"Cat{i}" for i in range(20)])
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "categories"
        menu.current_page = 1
        menu._handle_left()
        assert menu.current_page == 0
        assert menu.selected_category_idx == 0

    def test_handle_left_at_first_page(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.current_page = 0
        menu._handle_left()
        assert menu.current_page == 0

    def test_handle_left_servers(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "servers"
        menu.current_servers = [FakeServer(name=f"s{i}") for i in range(20)]
        menu.current_page = 1
        menu._handle_left()
        assert menu.current_page == 0
        assert menu.selected_server_idx == 0

    def test_handle_right_categories(self):
        menu = make_menu(catalog_categories=[f"Cat{i}" for i in range(20)])
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "categories"
        menu.current_page = 0
        menu._handle_right()
        assert menu.current_page == 1

    def test_handle_right_at_last_page(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "categories"
        menu.current_page = 0  # only 3 categories, fits on 1 page
        menu._handle_right()
        assert menu.current_page == 0

    def test_handle_right_servers(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "servers"
        menu.current_servers = [FakeServer(name=f"s{i}") for i in range(20)]
        menu.current_page = 0
        menu._handle_right()
        assert menu.current_page == 1
        assert menu.selected_server_idx == 12  # PAGE_SIZE

    def test_handle_enter_categories(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.selected_category_idx = 1  # "Code"
        result = menu._handle_enter()
        assert result is False
        assert menu.view_mode == "servers"

    def test_handle_enter_custom_server(self):
        menu = make_menu()
        menu.selected_category_idx = 0
        result = menu._handle_enter()
        assert result is True
        assert menu.result == "pending_custom"

    def test_handle_enter_servers(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_servers = [FakeServer()]
        menu.selected_server_idx = 0
        result = menu._handle_enter()
        assert result is True
        assert menu.result == "pending_install"

    def test_handle_back_in_servers(self):
        menu = make_menu()
        menu.view_mode = "servers"
        menu.current_category = "Code"
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu._handle_back()
        assert menu.view_mode == "categories"

    def test_handle_back_in_categories(self):
        menu = make_menu()
        menu.view_mode = "categories"
        menu._handle_back()
        assert menu.view_mode == "categories"  # no change

    def test_reload_mcp_servers_success(self):
        menu = make_menu()
        with patch.dict("sys.modules", {"code_puppy.agent": MagicMock()}):
            menu._reload_mcp_servers()  # should not raise

    def test_reload_mcp_servers_import_error(self):
        menu = make_menu()
        # Don't mock code_puppy.agent - it should raise ImportError
        menu._reload_mcp_servers()  # should not raise


class TestUpdateDisplay:
    def test_categories_mode(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "categories"
        menu.update_display()
        assert menu.menu_control.text is not None
        assert menu.preview_control.text is not None

    def test_servers_mode(self):
        menu = make_menu()
        menu.menu_control = MagicMock()
        menu.preview_control = MagicMock()
        menu.view_mode = "servers"
        menu.current_category = "Code"
        menu.current_servers = [FakeServer()]
        menu.update_display()
        assert menu.menu_control.text is not None
