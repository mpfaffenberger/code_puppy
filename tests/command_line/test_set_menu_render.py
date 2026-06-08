"""Tests for ``code_puppy.command_line.set_menu_render``.

These are pure render tests -- no prompt_toolkit Application is spun
up. Both panels return a list of ``(style, text)`` tuples that we
flatten to a search target.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from code_puppy.command_line.pagination import get_page_bounds, get_total_pages
from code_puppy.command_line.set_menu_render import (
    render_left_panel,
    render_right_panel,
)
from code_puppy.command_line.set_menu_settings import Setting, SettingsCategory


@dataclass(frozen=True)
class _Entry:
    """Minimal stand-in for set_menu._Entry to keep this test free of
    that module's import surface."""

    category: SettingsCategory
    setting: Setting


def _flatten(panel_lines):
    """Concatenate every (style, text) tuple's text for substring lookup."""
    return "".join(text for _, text in panel_lines)


def _styles_with(panel_lines, needle):
    """Return the styles attached to any segment containing ``needle``."""
    return [style for style, text in panel_lines if needle in text]


# ---------------------------------------------------------------------------
# (Default) prefix on the left panel
# ---------------------------------------------------------------------------


class TestLeftPanelDefaultPrefix:
    def _entry_for(self, getter_return):
        category = SettingsCategory(name="Behavior")
        setting = Setting(
            key="some_key",
            display_name="Some Key",
            description="x",
            type_hint="bool",
            effective_getter=lambda: getter_return,
        )
        return _Entry(category=category, setting=setting)

    def test_prefix_appears_when_value_is_default(self):
        entry = self._entry_for("true")
        with patch(
            "code_puppy.command_line.set_menu_render.is_default_value",
            return_value=True,
        ):
            panel = render_left_panel(
                [entry],
                page=0,
                selected_idx=0,
                search_text="",
                in_search_mode=False,
                search_buffer="",
                page_size=12,
                page_bounds=get_page_bounds,
                total_pages_fn=get_total_pages,
            )
        assert "(Default) " in _flatten(panel)

    def test_prefix_absent_when_value_is_user_set(self):
        entry = self._entry_for("true")
        with patch(
            "code_puppy.command_line.set_menu_render.is_default_value",
            return_value=False,
        ):
            panel = render_left_panel(
                [entry],
                page=0,
                selected_idx=0,
                search_text="",
                in_search_mode=False,
                search_buffer="",
                page_size=12,
                page_bounds=get_page_bounds,
                total_pages_fn=get_total_pages,
            )
        assert "(Default) " not in _flatten(panel)

    def test_prefix_uses_dim_italic_style(self):
        entry = self._entry_for("true")
        with patch(
            "code_puppy.command_line.set_menu_render.is_default_value",
            return_value=True,
        ):
            panel = render_left_panel(
                [entry],
                page=0,
                selected_idx=1,  # not selected -> non-bold style
                search_text="",
                in_search_mode=False,
                search_buffer="",
                page_size=12,
                page_bounds=get_page_bounds,
                total_pages_fn=get_total_pages,
            )
        styles = _styles_with(panel, "(Default) ")
        assert any("ansibrightblack" in s and "italic" in s for s in styles)


# ---------------------------------------------------------------------------
# (Default) prefix on the right details panel
# ---------------------------------------------------------------------------


class TestRightPanelDefaultPrefix:
    def _entry_for(self, getter_return):
        category = SettingsCategory(name="Behavior")
        setting = Setting(
            key="some_key",
            display_name="Some Key",
            description="x",
            type_hint="bool",
            effective_getter=lambda: getter_return,
        )
        return _Entry(category=category, setting=setting)

    def test_prefix_appears_when_value_is_default(self):
        entry = self._entry_for("true")
        with patch(
            "code_puppy.command_line.set_menu_render.is_default_value",
            return_value=True,
        ):
            panel = render_right_panel(entry)
        assert "(Default) " in _flatten(panel)

    def test_prefix_absent_when_value_is_user_set(self):
        entry = self._entry_for("true")
        with patch(
            "code_puppy.command_line.set_menu_render.is_default_value",
            return_value=False,
        ):
            panel = render_right_panel(entry)
        assert "(Default) " not in _flatten(panel)

    def test_prefix_absent_when_not_set(self):
        """No value -> '(not set)' branch, never '(Default) (not set)'."""
        entry = self._entry_for(None)
        with patch(
            "code_puppy.command_line.set_menu_render.is_default_value",
            return_value=False,
        ):
            panel = render_right_panel(entry)
        flat = _flatten(panel)
        assert "(not set)" in flat
        assert "(Default) " not in flat
