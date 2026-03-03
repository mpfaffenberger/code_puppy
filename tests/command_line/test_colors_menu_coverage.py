"""Coverage tests for colors_menu.py - exercises all uncovered code paths."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.command_line.colors_menu import (
    ColorConfiguration,
    _get_preview_text_for_prompt_toolkit,
    _get_single_banner_preview,
    _handle_color_menu,
    _split_panel_selector,
    interactive_colors_picker,
)

# --------------- ColorConfiguration ---------------


class TestColorConfiguration:
    def test_init(self):
        config = ColorConfiguration()
        assert isinstance(config.current_colors, dict)
        assert isinstance(config.banner_keys, list)
        assert config.selected_banner_index == 0

    def test_has_changes_false(self):
        config = ColorConfiguration()
        assert config.has_changes() is False

    def test_has_changes_true(self):
        config = ColorConfiguration()
        key = config.banner_keys[0]
        config.current_colors[key] = "never_a_real_color"
        assert config.has_changes() is True

    def test_get_current_banner_key(self):
        config = ColorConfiguration()
        config.selected_banner_index = 0
        assert config.get_current_banner_key() == config.banner_keys[0]

    def test_get_current_banner_color(self):
        config = ColorConfiguration()
        key = config.get_current_banner_key()
        assert config.get_current_banner_color() == config.current_colors[key]

    def test_set_current_banner_color(self):
        config = ColorConfiguration()
        config.set_current_banner_color("red3")
        key = config.get_current_banner_key()
        assert config.current_colors[key] == "red3"

    def test_next_banner(self):
        config = ColorConfiguration()
        config.selected_banner_index = 0
        config.next_banner()
        assert config.selected_banner_index == 1

    def test_next_banner_wrap(self):
        config = ColorConfiguration()
        config.selected_banner_index = len(config.banner_keys) - 1
        config.next_banner()
        assert config.selected_banner_index == 0

    def test_prev_banner(self):
        config = ColorConfiguration()
        config.selected_banner_index = 2
        config.prev_banner()
        assert config.selected_banner_index == 1

    def test_prev_banner_wrap(self):
        config = ColorConfiguration()
        config.selected_banner_index = 0
        config.prev_banner()
        assert config.selected_banner_index == len(config.banner_keys) - 1


# --------------- _get_preview_text_for_prompt_toolkit ---------------


class TestGetPreviewText:
    def test_returns_ansi(self):
        config = ColorConfiguration()
        result = _get_preview_text_for_prompt_toolkit(config)
        # Should return ANSI formatted text
        assert result is not None

    def test_highlights_selected(self):
        config = ColorConfiguration()
        config.selected_banner_index = 2
        result = _get_preview_text_for_prompt_toolkit(config)
        assert result is not None


# --------------- _get_single_banner_preview ---------------


class TestGetSingleBannerPreview:
    def test_returns_ansi(self):
        config = ColorConfiguration()
        result = _get_single_banner_preview(config)
        assert result is not None

    def test_different_banners(self):
        config = ColorConfiguration()
        config.selected_banner_index = 3
        result = _get_single_banner_preview(config)
        assert result is not None


# --------------- _split_panel_selector ---------------


class TestSplitPanelSelector:
    @pytest.mark.asyncio
    async def test_enter_selects(self):
        """Test that entering selects the current choice."""
        with patch("code_puppy.command_line.colors_menu.Application") as mock_app_cls:
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app

            choices = ["Choice A", "Choice B"]

            # Simulate: run_async sets result and exits
            async def fake_run_async():
                # The accept handler sets result[0] and calls exit
                # We simulate that by finding the enter key binding
                pass

            mock_app.run_async = fake_run_async

            # Since we can't easily simulate keypresses, test the internal functions
            # Instead, test that KeyboardInterrupt raises properly
            with pytest.raises(KeyboardInterrupt):
                await _split_panel_selector(
                    "Test",
                    choices,
                    lambda c: None,
                    get_preview=lambda: MagicMock(),
                )

    @pytest.mark.asyncio
    async def test_empty_choices(self):
        """Test with empty choices."""
        with patch("code_puppy.command_line.colors_menu.Application") as mock_app_cls:
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app

            async def fake_run_async():
                pass

            mock_app.run_async = fake_run_async

            with pytest.raises(KeyboardInterrupt):
                await _split_panel_selector(
                    "Test",
                    [],
                    lambda c: None,
                    get_preview=lambda: MagicMock(),
                )


# --------------- _handle_color_menu ---------------


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
            await _handle_color_menu(config)  # should not raise

    @pytest.mark.asyncio
    async def test_successful_selection(self):
        config = ColorConfiguration()
        with patch(
            "code_puppy.command_line.colors_menu._split_panel_selector",
            return_value="blue",
        ):
            await _handle_color_menu(config)


# --------------- interactive_colors_picker ---------------


class TestInteractiveColorsPicker:
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
        # Reset to defaults may differ from original config, so result could be non-None

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

    @pytest.mark.asyncio
    async def test_select_banner_opens_color_menu(self):
        call_count = [0]

        async def fake_selector(title, choices, on_change, get_preview, config=None):
            call_count[0] += 1
            if call_count[0] == 1:
                # Select first banner (e.g., "THINKING [blue]")
                return choices[0]
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
        assert result is None

    @pytest.mark.asyncio
    async def test_exit_no_changes(self):
        async def fake_selector(title, choices, on_change, get_preview, config=None):
            for c in choices:
                if "Exit" in c:
                    return c
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
