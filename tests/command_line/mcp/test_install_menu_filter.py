"""Tests for the live text-filter added to /mcp install menu.

The full TUI is exercised elsewhere; here we only test the pure-Python
filter logic that powers it. We avoid touching the prompt-toolkit app and
instead directly drive the helper methods on ``MCPInstallMenu``.

These tests are intentionally hermetic \u2014 the catalog and manager are
swapped out for tiny stand-ins so the existing (pre-broken) test pollution
in ``test_install_menu.py`` doesn't leak in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
from unittest.mock import patch

import pytest

from code_puppy.command_line.mcp.install_menu import (
    CUSTOM_SERVER_CATEGORY,
    MCPInstallMenu,
)


@dataclass
class _FakeServer:
    """Stand-in for ``MCPServerTemplate`` with just the fields we filter on."""

    name: str
    display_name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    type: str = "http"
    verified: bool = False
    popular: bool = False
    config: dict = field(default_factory=dict)
    example_usage: str = ""

    def get_environment_vars(self):
        return []

    def get_command_line_args(self):
        return []

    def get_requirements(self):
        @dataclass
        class _R:
            required_tools: list = field(default_factory=list)
        return _R()


class _FakeCatalog:
    """Catalog stub returning a fixed map of category \u2192 servers."""

    def __init__(self, by_category):
        self._by_category = by_category

    def list_categories(self):
        return list(self._by_category.keys())

    def get_by_category(self, category):
        return list(self._by_category.get(category, []))


@pytest.fixture
def menu():
    """Build an MCPInstallMenu with a deterministic fake catalog."""
    walmart = [
        _FakeServer(
            name="shelly-mcp-server",
            display_name="Shelly",
            description="Workforce planning analytics",
            tags=["analytics", "internal"],
        ),
        _FakeServer(
            name="ark-mcp-server",
            display_name="Ark",
            description="Documentation lookup tool",
            tags=["docs", "search"],
        ),
        _FakeServer(
            name="mcp-jira",
            display_name="JIRA",
            description="Issue tracker integration",
            tags=["tickets", "atlassian"],
        ),
    ]
    code = [
        _FakeServer(
            name="github",
            display_name="GitHub",
            description="GitHub API access",
            tags=["git", "code"],
        ),
    ]
    fake_catalog = _FakeCatalog(
        {"Walmart MCP Marketplace": walmart, "Code": code}
    )

    # Patch the import done inside _initialize_catalog
    with patch(
        "code_puppy.mcp_.server_registry_catalog.catalog", fake_catalog
    ):
        m = MCPInstallMenu(manager=object())
    # In real use ``update_display`` is wired to prompt-toolkit controls
    # that exist after .run(). For these unit tests we never call .run(),
    # so silence the redraw side-effect to keep mutator helpers focused
    # on the state they manage.
    m.update_display = lambda: None
    return m


class TestFilterCategories:
    def test_no_filter_returns_all_categories(self, menu):
        # Custom + the two from the fake catalog
        assert len(menu._visible_categories()) == 3
        assert CUSTOM_SERVER_CATEGORY in menu._visible_categories()

    def test_filter_matches_substring(self, menu):
        menu.filter_text = "walmart"
        out = menu._visible_categories()
        # Walmart MCP Marketplace + Custom (always shown)
        assert "Walmart MCP Marketplace" in out
        assert CUSTOM_SERVER_CATEGORY in out
        assert "Code" not in out

    def test_custom_category_always_visible(self, menu):
        menu.filter_text = "zzz_no_match_for_anything"
        out = menu._visible_categories()
        # Custom survives even when nothing else matches \u2014 user can always
        # fall back to a hand-rolled config.
        assert out == [CUSTOM_SERVER_CATEGORY]


class TestFilterServers:
    def test_no_filter_returns_all_servers(self, menu):
        menu.view_mode = "servers"
        menu.current_category = "Walmart MCP Marketplace"
        menu.current_servers = menu.catalog.get_by_category(
            "Walmart MCP Marketplace"
        )
        assert len(menu._visible_servers()) == 3

    def test_filter_by_display_name(self, menu):
        menu.view_mode = "servers"
        menu.current_category = "Walmart MCP Marketplace"
        menu.current_servers = menu.catalog.get_by_category(
            "Walmart MCP Marketplace"
        )
        menu.filter_text = "jira"
        out = menu._visible_servers()
        assert len(out) == 1
        assert out[0].display_name == "JIRA"

    def test_filter_by_description(self, menu):
        menu.view_mode = "servers"
        menu.current_category = "Walmart MCP Marketplace"
        menu.current_servers = menu.catalog.get_by_category(
            "Walmart MCP Marketplace"
        )
        menu.filter_text = "documentation"
        out = menu._visible_servers()
        assert len(out) == 1
        assert out[0].name == "ark-mcp-server"

    def test_filter_by_tag(self, menu):
        menu.view_mode = "servers"
        menu.current_category = "Walmart MCP Marketplace"
        menu.current_servers = menu.catalog.get_by_category(
            "Walmart MCP Marketplace"
        )
        menu.filter_text = "atlassian"
        out = menu._visible_servers()
        assert len(out) == 1
        assert out[0].name == "mcp-jira"

    def test_filter_by_underlying_name(self, menu):
        menu.view_mode = "servers"
        menu.current_category = "Walmart MCP Marketplace"
        menu.current_servers = menu.catalog.get_by_category(
            "Walmart MCP Marketplace"
        )
        # display_name is "Shelly" but underlying name is shelly-mcp-server
        menu.filter_text = "mcp-server"
        out = menu._visible_servers()
        names = {s.name for s in out}
        assert "shelly-mcp-server" in names
        assert "ark-mcp-server" in names

    def test_multi_term_filter_is_AND(self, menu):
        menu.view_mode = "servers"
        menu.current_category = "Walmart MCP Marketplace"
        menu.current_servers = menu.catalog.get_by_category(
            "Walmart MCP Marketplace"
        )
        # Both terms must appear somewhere in the haystack
        menu.filter_text = "shelly workforce"
        out = menu._visible_servers()
        assert len(out) == 1
        assert out[0].name == "shelly-mcp-server"


class TestFilterMutators:
    def test_append_clamps_selection(self, menu):
        # Simulate user already in servers view at index 2
        menu.view_mode = "servers"
        menu.current_category = "Walmart MCP Marketplace"
        menu.current_servers = menu.catalog.get_by_category(
            "Walmart MCP Marketplace"
        )
        menu.selected_server_idx = 2

        # Type "jira" \u2014 only one server matches, idx must clamp to 0
        for ch in "jira":
            menu._append_filter_char(ch)
        assert menu.filter_text == "jira"
        assert menu.selected_server_idx == 0
        assert menu.current_page == 0

    def test_delete_filter_char(self, menu):
        menu.filter_text = "abc"
        menu._delete_filter_char()
        assert menu.filter_text == "ab"

    def test_delete_filter_char_empty_noop(self, menu):
        menu.filter_text = ""
        menu._delete_filter_char()
        assert menu.filter_text == ""

    def test_clear_filter(self, menu):
        menu.filter_text = "jira"
        menu._clear_filter()
        assert menu.filter_text == ""

    def test_append_ignores_non_printable(self, menu):
        menu._append_filter_char("\x07")  # bell
        menu._append_filter_char("")
        assert menu.filter_text == ""


class TestFilterPreservedAcrossViewChange:
    def test_filter_survives_enter_category(self, menu):
        # User types a filter while browsing categories
        menu.filter_text = "marketplace"
        # Walmart MCP Marketplace is the only non-custom match
        visible_cats = menu._visible_categories()
        assert "Walmart MCP Marketplace" in visible_cats
        # Force-position selection on Walmart MCP Marketplace
        menu.selected_category_idx = visible_cats.index("Walmart MCP Marketplace")

        # Enter the category \u2014 the filter should still be active
        menu._enter_category()
        assert menu.view_mode == "servers"
        # Filter remains; if no servers match "marketplace", visible is empty
        assert menu.filter_text == "marketplace"
