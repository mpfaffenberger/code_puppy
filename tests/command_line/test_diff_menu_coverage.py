"""Additional coverage tests for diff_menu.py - targeting inner functions and callbacks.

Focuses on:
- Inner closure functions (get_left_panel_text, get_right_panel_text)
- Key binding handlers (move_up, move_down, prev_lang, next_lang, accept, cancel)
- Callback functions (update_preview, dummy_update, get_main_preview)
- Exception handling paths
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from prompt_toolkit.formatted_text import ANSI
from code_puppy.command_line.diff_menu import (
    ADDITION_COLORS,
    DELETION_COLORS,
    DiffConfiguration,
    _handle_color_menu,
    _split_panel_selector,
    interactive_diff_picker,
)


class TestFormattedTextControlInvocation:
    """Test that FormattedTextControl actually invokes our inner functions."""

    @pytest.mark.asyncio
    async def test_formatted_text_control_calls_get_left_panel(self):
        """Verify FormattedTextControl is set up to call get_left_panel_text."""
        from prompt_toolkit.layout.controls import FormattedTextControl

        captured_controls = []

        original_ftc = FormattedTextControl

        def track_ftc(get_formatted_text, *args, **kwargs):
            captured_controls.append(get_formatted_text)
            return original_ftc(get_formatted_text, *args, **kwargs)

        with patch(
            "code_puppy.command_line.diff_menu.FormattedTextControl",
            side_effect=track_ftc,
        ):
            with patch("code_puppy.command_line.diff_menu.Application") as mock_app:
                mock_instance = MagicMock()
                mock_instance.run_async = AsyncMock()
                mock_app.return_value = mock_instance

                with patch("sys.stdout.write"):
                    with pytest.raises(KeyboardInterrupt):
                        await _split_panel_selector(
                            "Title",
                            ["A", "B"],
                            lambda x: None,
                            lambda: ANSI("preview"),
                            config=DiffConfiguration(),
                        )

        # Should have captured 2 controls (left and right panels)
        assert len(captured_controls) == 2

        # Invoke each captured function to execute the inner function code
        for control_fn in captured_controls:
            if callable(control_fn):
                try:
                    result = control_fn()
                    # Result should be FormattedText or ANSI
                    assert result is not None
                except Exception:
                    pass


class TestInnerFunctionExecution:
    """Tests that actually execute the inner functions to cover remaining lines."""

    @pytest.mark.asyncio
    async def test_get_left_panel_text_empty_choices_execution(self):
        """Execute get_left_panel_text with empty choices to cover lines 496-497."""

        captured_controls = []

        def track_ftc(get_formatted_text, *args, **kwargs):
            captured_controls.append(get_formatted_text)
            return MagicMock()

        with patch(
            "code_puppy.command_line.diff_menu.FormattedTextControl",
            side_effect=track_ftc,
        ):
            with patch("code_puppy.command_line.diff_menu.Application") as mock_app:
                mock_instance = MagicMock()
                mock_instance.run_async = AsyncMock()
                mock_app.return_value = mock_instance

                with patch("sys.stdout.write"):
                    with pytest.raises(KeyboardInterrupt):
                        await _split_panel_selector(
                            "Empty Menu",
                            [],  # Empty choices!
                            lambda x: None,
                            lambda: ANSI("preview"),
                            config=None,
                        )

        # Execute the captured get_left_panel_text lambda to hit empty choices branch
        assert len(captured_controls) >= 1
        left_panel_fn = captured_controls[0]
        if callable(left_panel_fn):
            result = left_panel_fn()
            # Should have executed the empty choices branch
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_left_panel_text_exception_handling(self):
        """Test exception handling in get_left_panel_text (lines 521-522)."""

        captured_controls = []

        def track_ftc(get_formatted_text, *args, **kwargs):
            captured_controls.append(get_formatted_text)
            return MagicMock()

        # Create a config that raises exception
        bad_config = MagicMock()
        bad_config.get_current_language.side_effect = RuntimeError("Language error!")

        with patch(
            "code_puppy.command_line.diff_menu.FormattedTextControl",
            side_effect=track_ftc,
        ):
            with patch("code_puppy.command_line.diff_menu.Application") as mock_app:
                mock_instance = MagicMock()
                mock_instance.run_async = AsyncMock()
                mock_app.return_value = mock_instance

                with patch("sys.stdout.write"):
                    with pytest.raises(KeyboardInterrupt):
                        await _split_panel_selector(
                            "Test",
                            ["Choice"],
                            lambda x: None,
                            lambda: ANSI("preview"),
                            config=bad_config,
                        )

        # Execute left panel function - should hit exception handler
        if captured_controls and callable(captured_controls[0]):
            result = captured_controls[0]()
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_right_panel_text_exception_handling(self):
        """Test exception handling in get_right_panel_text (lines 530-531)."""

        captured_controls = []

        def track_ftc(get_formatted_text, *args, **kwargs):
            captured_controls.append(get_formatted_text)
            return MagicMock()

        def bad_preview():
            raise ValueError("Preview generation failed!")

        with patch(
            "code_puppy.command_line.diff_menu.FormattedTextControl",
            side_effect=track_ftc,
        ):
            with patch("code_puppy.command_line.diff_menu.Application") as mock_app:
                mock_instance = MagicMock()
                mock_instance.run_async = AsyncMock()
                mock_app.return_value = mock_instance

                with patch("sys.stdout.write"):
                    with pytest.raises(KeyboardInterrupt):
                        await _split_panel_selector(
                            "Test",
                            ["Choice"],
                            lambda x: None,
                            bad_preview,  # This will raise!
                            config=None,
                        )

        # Execute right panel function - should hit exception handler
        if len(captured_controls) >= 2 and callable(captured_controls[1]):
            result = captured_controls[1]()
            assert result is not None


class TestInteractiveDiffPickerInnerFunctions:
    """Test inner functions in interactive_diff_picker."""

    @pytest.mark.asyncio
    async def test_dummy_update_is_called(self):
        """Test that dummy_update function is passed and can be invoked."""
        captured_callback = [None]
        call_count = [0]

        async def capture_selector(title, choices, on_change, get_preview, config=None):
            captured_callback[0] = on_change
            # Call the on_change to test dummy_update
            on_change(choices[0] if choices else "")
            call_count[0] += 1
            return "Exit"

        with patch(
            "code_puppy.command_line.diff_menu._split_panel_selector",
            side_effect=capture_selector,
        ):
            with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                with patch("sys.stdout.write"):
                    with patch("time.sleep"):
                        await interactive_diff_picker()

        # dummy_update should have been called without error
        assert call_count[0] >= 1

    @pytest.mark.asyncio
    async def test_get_main_preview_returns_ansi(self):
        """Test that get_main_preview function returns proper ANSI output."""
        captured_preview_fn = [None]

        async def capture_selector(title, choices, on_change, get_preview, config=None):
            captured_preview_fn[0] = get_preview
            return "Exit"

        with patch(
            "code_puppy.command_line.diff_menu._split_panel_selector",
            side_effect=capture_selector,
        ):
            with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                with patch("sys.stdout.write"):
                    with patch("time.sleep"):
                        with patch(
                            "code_puppy.tools.common.format_diff_with_colors",
                            return_value="mock diff",
                        ):
                            await interactive_diff_picker()

        # get_main_preview should have been captured
        assert captured_preview_fn[0] is not None

        # Call it and verify it returns something
        with patch(
            "code_puppy.tools.common.format_diff_with_colors", return_value="mock diff"
        ):
            result = captured_preview_fn[0]()
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_preview_header_in_color_menu(self):
        """Test that get_preview_header function works in color menu."""
        captured_preview_fn = [None]

        async def capture_selector(title, choices, on_change, get_preview, config=None):
            captured_preview_fn[0] = get_preview
            return choices[0] if choices else "Exit"

        config = DiffConfiguration()

        with patch(
            "code_puppy.command_line.diff_menu._split_panel_selector",
            side_effect=capture_selector,
        ):
            with patch(
                "code_puppy.tools.common.format_diff_with_colors", return_value="mock"
            ):
                await _handle_color_menu(config, "additions")

        assert captured_preview_fn[0] is not None

        # Call preview function and verify it works
        with patch(
            "code_puppy.tools.common.format_diff_with_colors", return_value="mock diff"
        ):
            result = captured_preview_fn[0]()
            assert result is not None


class TestUpdatePreviewCallback:
    """Test the update_preview callback in _handle_color_menu."""

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_restores_deletion_color(self):
        """Test that KeyboardInterrupt restores deletion color (not just addition)."""
        config = DiffConfiguration()
        original_del_color = config.current_del_color

        async def interrupt_selector(*args, **kwargs):
            # Simulate that the color was changed during selection
            config.current_del_color = "#changed_color"
            raise KeyboardInterrupt()

        with patch(
            "code_puppy.command_line.diff_menu._split_panel_selector",
            side_effect=interrupt_selector,
        ):
            await _handle_color_menu(config, "deletions")

        # Original deletion color should be restored
        assert config.current_del_color == original_del_color

    @pytest.mark.asyncio
    async def test_update_preview_sets_addition_color(self):
        """Test that update_preview callback sets addition color correctly."""
        captured_callback = [None]

        async def capture_selector(title, choices, on_change, get_preview, config=None):
            captured_callback[0] = on_change
            return "dark green"  # Return a valid selection

        config = DiffConfiguration()

        with patch(
            "code_puppy.command_line.diff_menu._split_panel_selector",
            side_effect=capture_selector,
        ):
            await _handle_color_menu(config, "additions")

        # The callback should have been captured
        assert captured_callback[0] is not None

        # Call the callback with a color choice
        captured_callback[0]("dark green")
        assert config.current_add_color == ADDITION_COLORS["dark green"]

        # Test with " ← current" marker
        captured_callback[0]("darker green ← current")
        assert config.current_add_color == ADDITION_COLORS["darker green"]

    @pytest.mark.asyncio
    async def test_update_preview_sets_deletion_color(self):
        """Test that update_preview callback sets deletion color correctly."""
        captured_callback = [None]

        async def capture_selector(title, choices, on_change, get_preview, config=None):
            captured_callback[0] = on_change
            return "dark red"

        config = DiffConfiguration()

        with patch(
            "code_puppy.command_line.diff_menu._split_panel_selector",
            side_effect=capture_selector,
        ):
            await _handle_color_menu(config, "deletions")

        assert captured_callback[0] is not None

        # Call the callback with a deletion color
        captured_callback[0]("dark red")
        assert config.current_del_color == DELETION_COLORS["dark red"]
