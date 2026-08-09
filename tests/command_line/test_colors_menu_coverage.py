"""Coverage tests for colors_menu.py - exercises all uncovered code paths."""

from unittest.mock import AsyncMock, patch
import pytest
from code_puppy.command_line.colors_menu import (
    ColorConfiguration,
    _get_preview_text_for_prompt_toolkit,
    _get_single_banner_preview,
    _handle_color_menu,
    interactive_colors_picker,
)


class TestColorConfiguration:
    def test_get_current_banner_color(self):
        config = ColorConfiguration()
        key = config.get_current_banner_key()
        assert config.get_current_banner_color() == config.current_colors[key]

    def test_has_changes_false(self):
        config = ColorConfiguration()
        assert config.has_changes() is False

    def test_next_banner(self):
        config = ColorConfiguration()
        config.selected_banner_index = 0
        config.next_banner()
        assert config.selected_banner_index == 1

    def test_prev_banner(self):
        config = ColorConfiguration()
        config.selected_banner_index = 2
        config.prev_banner()
        assert config.selected_banner_index == 1

    def test_set_current_banner_color(self):
        config = ColorConfiguration()
        config.set_current_banner_color("red3")
        key = config.get_current_banner_key()
        assert config.current_colors[key] == "red3"


class TestGetSingleBannerPreview:
    def test_returns_ansi(self):
        config = ColorConfiguration()
        result = _get_single_banner_preview(config)
        assert result is not None


class TestHandleColorMenu:
    @pytest.mark.asyncio
    async def test_cancel_restores_color(self):
        config = ColorConfiguration()
        original_color = config.get_current_banner_color()

        with patch(
            "code_puppy.command_line.colors_menu._split_panel_selector",
            side_effect=KeyboardInterrupt,
        ):
            await _handle_color_menu(config)

        assert config.get_current_banner_color() == original_color

    @pytest.mark.asyncio
    async def test_exception_handled(self):
        config = ColorConfiguration()
        with patch(
            "code_puppy.command_line.colors_menu._split_panel_selector",
            side_effect=RuntimeError("boom"),
        ):
            await _handle_color_menu(config)


class TestInteractiveColorsPicker:
    @pytest.mark.asyncio
    async def test_discard_and_exit(self):
        async def fake_selector(title, choices, on_change, get_preview, config=None):
            if config:
                config.current_colors[config.banner_keys[0]] = "never_real"
            for c in choices:
                if "Discard" in c:
                    return c
            return "❌ Exit"

        with (
            patch(
                "code_puppy.command_line.colors_menu._split_panel_selector",
                side_effect=fake_selector,
            ),
            patch("code_puppy.tools.command_runner.set_awaiting_user_input"),
            patch("sys.stdout"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await interactive_colors_picker()
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        with (
            patch(
                "code_puppy.command_line.colors_menu._split_panel_selector",
                side_effect=RuntimeError("boom"),
            ),
            patch("code_puppy.tools.command_runner.set_awaiting_user_input"),
            patch("sys.stdout"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await interactive_colors_picker()
        assert result is None

    @pytest.mark.asyncio
    async def test_reset_all(self):
        call_count = [0]

        async def fake_selector(title, choices, on_change, get_preview, config=None):
            call_count[0] += 1
            if call_count[0] == 1:
                for c in choices:
                    if "Reset All" in c:
                        return c
                return choices[0]
            raise KeyboardInterrupt

        with (
            patch(
                "code_puppy.command_line.colors_menu._split_panel_selector",
                side_effect=fake_selector,
            ),
            patch("code_puppy.tools.command_runner.set_awaiting_user_input"),
            patch("sys.stdout"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await interactive_colors_picker()

    @pytest.mark.asyncio
    async def test_returns_none_on_cancel(self):
        with (
            patch(
                "code_puppy.command_line.colors_menu._split_panel_selector",
                side_effect=KeyboardInterrupt,
            ),
            patch("code_puppy.tools.command_runner.set_awaiting_user_input"),
            patch("sys.stdout"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await interactive_colors_picker()
        assert result is None

    @pytest.mark.asyncio
    async def test_save_and_exit(self):
        call_count = [0]

        async def fake_selector(title, choices, on_change, get_preview, config=None):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: change a color, return a banner to trigger color menu
                if config:
                    config.current_colors[config.banner_keys[0]] = "never_real"
                # Return first banner choice to enter color submenu
                return choices[0]
            if call_count[0] == 2:
                # Second call (from color submenu or re-loop): save should be available now
                for c in choices:
                    if "Save" in c:
                        return c
                return choices[-1]
            raise KeyboardInterrupt

        with (
            patch(
                "code_puppy.command_line.colors_menu._split_panel_selector",
                side_effect=fake_selector,
            ),
            patch(
                "code_puppy.command_line.colors_menu._handle_color_menu",
                new_callable=AsyncMock,
            ),
            patch("code_puppy.tools.command_runner.set_awaiting_user_input"),
            patch("sys.stdout"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await interactive_colors_picker()
        assert result is not None

    @pytest.mark.asyncio
    async def test_separator_ignored(self):
        call_count = [0]

        async def fake_selector(title, choices, on_change, get_preview, config=None):
            call_count[0] += 1
            if call_count[0] == 1:
                for c in choices:
                    if "───" in c:
                        return c
                return choices[0]
            raise KeyboardInterrupt

        with (
            patch(
                "code_puppy.command_line.colors_menu._split_panel_selector",
                side_effect=fake_selector,
            ),
            patch("code_puppy.tools.command_runner.set_awaiting_user_input"),
            patch("sys.stdout"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await interactive_colors_picker()
        assert result is None


class TestGetPreviewText:
    def test_returns_ansi(self):
        config = ColorConfiguration()
        result = _get_preview_text_for_prompt_toolkit(config)
        # Should return ANSI formatted text
        assert result is not None
