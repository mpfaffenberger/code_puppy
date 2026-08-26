"""Headless tests for the termflow MCP install menu."""

from io import StringIO
from unittest.mock import MagicMock, patch

from code_puppy.command_line.mcp import install_menu as im


class FakeServer:
    def __init__(
        self,
        name="files",
        display_name="File Server",
        server_type="stdio",
        verified=True,
        popular=True,
    ):
        self.name = name
        self.display_name = display_name
        self.type = server_type
        self.verified = verified
        self.popular = popular
        self.description = "Serves files over MCP."
        self.tags = ["files", "fs"]
        self.example_usage = "read a file"

    def get_environment_vars(self):
        return ["FILES_TOKEN"]

    def get_command_line_args(self):
        return [{"name": "root", "required": True, "default": "/tmp"}]

    def get_requirements(self):
        req = MagicMock()
        req.required_tools = ["npx"]
        return req


class FakeCatalog:
    def __init__(self, servers=None):
        self._servers = servers if servers is not None else [FakeServer()]

    def list_categories(self):
        return ["Storage"]

    def get_by_category(self, category):
        return self._servers


def keys(*sequence):
    script = iter(sequence)
    return {
        "key_source": lambda: next(script),
        "output": StringIO(),
        "size": lambda: (110, 30),
    }


def scripted(factory, scripts):
    scripts = iter(scripts)

    def build(*args, **kw):
        return factory(*args, **keys(*next(scripts)))

    return build


class TestLoadCatalog:
    def test_custom_category_is_always_first(self):
        catalog, categories = im.load_catalog()
        assert categories[0] == im.CUSTOM_SERVER_CATEGORY

    def test_import_error_still_offers_custom(self):
        import builtins

        real_import = builtins.__import__

        def broken(name, *args, **kwargs):
            if "server_registry_catalog" in name:
                raise ImportError("nope")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=broken):
            catalog, categories = im.load_catalog()
        assert catalog is None
        assert categories == [im.CUSTOM_SERVER_CATEGORY]


class TestDetails:
    def test_category_details_lists_popular(self):
        text = im.category_details(FakeCatalog(), "Storage")
        assert "1 servers available" in text
        assert "File Server" in text

    def test_custom_category_details(self):
        text = im.category_details(None, im.CUSTOM_SERVER_CATEGORY)
        assert "stdio" in text and "http" in text and "sse" in text

    def test_server_details_shows_env_and_args(self):
        text = im.server_details(FakeServer())
        assert "File Server" in text
        assert "FILES_TOKEN" in text
        assert "root" in text
        assert "Verified" in text

    def test_category_icons(self):
        assert im.get_category_icon(im.CUSTOM_SERVER_CATEGORY) == "[+]"
        assert im.get_category_icon("Storage") == "[S]"
        assert im.get_category_icon("Mystery") == "[ ]"


class TestMenus:
    def test_categories_menu_returns_selection(self):
        menu = im.build_categories_menu(
            FakeCatalog(),
            [im.CUSTOM_SERVER_CATEGORY, "Storage"],
            **keys("down", "enter"),
        )
        assert menu.run().item.value == "Storage"

    def test_servers_menu_returns_server(self):
        server = FakeServer()
        menu = im.build_servers_menu("Storage", [server], **keys("enter"))
        assert menu.run().item.value is server


class TestBrowseFlow:
    def test_pick_catalog_server(self):
        server = FakeServer()
        catalog = FakeCatalog([server])
        result = im.run_browse_flow(
            catalog,
            [im.CUSTOM_SERVER_CATEGORY, "Storage"],
            categories_menu_factory=scripted(
                im.build_categories_menu, [["down", "enter"]]
            ),
            servers_menu_factory=scripted(im.build_servers_menu, [["enter"]]),
        )
        assert result is server

    def test_pick_custom(self):
        result = im.run_browse_flow(
            FakeCatalog(),
            [im.CUSTOM_SERVER_CATEGORY, "Storage"],
            categories_menu_factory=scripted(im.build_categories_menu, [["enter"]]),
        )
        assert result == "custom"

    def test_escape_in_servers_returns_to_categories(self):
        result = im.run_browse_flow(
            FakeCatalog(),
            [im.CUSTOM_SERVER_CATEGORY, "Storage"],
            categories_menu_factory=scripted(
                im.build_categories_menu, [["down", "enter"], ["escape"]]
            ),
            servers_menu_factory=scripted(im.build_servers_menu, [["escape"]]),
        )
        assert result is None

    def test_cancel_returns_none(self):
        result = im.run_browse_flow(
            FakeCatalog(),
            [im.CUSTOM_SERVER_CATEGORY],
            categories_menu_factory=scripted(im.build_categories_menu, [["escape"]]),
        )
        assert result is None


class TestRunMcpInstallMenu:
    def _session(self):
        mock = patch("code_puppy.command_line.menu_session.menu_session")
        return mock

    def test_custom_selection_runs_form(self):
        with (
            patch.object(im, "load_catalog", return_value=(FakeCatalog(), ["x"])),
            patch.object(im, "run_browse_flow", return_value="custom"),
            patch.object(im, "run_custom_server_form", return_value=True) as mock_form,
            patch.object(im, "_reload_mcp_servers") as mock_reload,
            self._session(),
        ):
            assert im.run_mcp_install_menu(MagicMock()) is True
        mock_form.assert_called_once()
        mock_reload.assert_called_once()

    def test_catalog_selection_prompts_and_installs(self):
        server = FakeServer()
        mgr = MagicMock()
        with (
            patch.object(im, "load_catalog", return_value=(FakeCatalog(), ["x"])),
            patch.object(im, "run_browse_flow", return_value=server),
            patch.object(
                im, "prompt_for_server_config", return_value={"name": "files"}
            ) as mock_prompt,
            patch.object(
                im, "install_catalog_server", return_value=True
            ) as mock_install,
            patch.object(im, "_reload_mcp_servers") as mock_reload,
            self._session(),
        ):
            assert im.run_mcp_install_menu(mgr) is True
        mock_prompt.assert_called_once_with(mgr, server)
        mock_install.assert_called_once()
        mock_reload.assert_called_once()

    def test_config_prompt_cancel_aborts(self):
        with (
            patch.object(im, "load_catalog", return_value=(FakeCatalog(), ["x"])),
            patch.object(im, "run_browse_flow", return_value=FakeServer()),
            patch.object(im, "prompt_for_server_config", return_value=None),
            patch.object(im, "install_catalog_server") as mock_install,
            self._session(),
        ):
            assert im.run_mcp_install_menu(MagicMock()) is False
        mock_install.assert_not_called()

    def test_browse_cancel_returns_false(self):
        with (
            patch.object(im, "load_catalog", return_value=(FakeCatalog(), ["x"])),
            patch.object(im, "run_browse_flow", return_value=None),
            self._session(),
        ):
            assert im.run_mcp_install_menu(MagicMock()) is False
