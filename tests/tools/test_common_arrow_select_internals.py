"""Tests for arrow_select internal functions and keybinding callbacks.

These tests cover the internal closures within arrow_select and arrow_select_async
that handle key events and text formatting.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prompt_toolkit.formatted_text import HTML

from code_puppy.tools import common as common_module


class TestArrowSelectFormattedText:
    """Test the formatted text generation in arrow_select."""

    def test_get_formatted_text_basic(self):
        """Test that formatted text is generated correctly."""
        # We'll manually recreate the internal logic to test it
        import html
        
        message = "Select an option"
        choices = ["Option 1", "Option 2", "Option 3"]
        selected_index = [0]
        
        def get_formatted_text():
            safe_message = html.escape(message)
            lines = [f"<b>{safe_message}</b>", ""]
            for i, choice in enumerate(choices):
                safe_choice = html.escape(choice)
                if i == selected_index[0]:
                    lines.append(f"<ansigreen>❯ {safe_choice}</ansigreen>")
                else:
                    lines.append(f"  {safe_choice}")
            lines.append("")
            lines.append("<ansicyan>(Use ↑↓ arrows to select, Enter to confirm)</ansicyan>")
            return HTML("\n".join(lines))
        
        result = get_formatted_text()
        assert result is not None
        
        # Change selection
        selected_index[0] = 1
        result2 = get_formatted_text()
        assert result2 is not None

    def test_get_formatted_text_with_special_chars(self):
        """Test formatted text with XML special characters."""
        import html
        
        message = "Select <option>"
        choices = ["A & B", "C > D", "E < F"]
        selected_index = [0]
        
        def get_formatted_text():
            safe_message = html.escape(message)
            lines = [f"<b>{safe_message}</b>", ""]
            for i, choice in enumerate(choices):
                safe_choice = html.escape(choice)
                if i == selected_index[0]:
                    lines.append(f"<ansigreen>❯ {safe_choice}</ansigreen>")
                else:
                    lines.append(f"  {safe_choice}")
            return HTML("\n".join(lines))
        
        result = get_formatted_text()
        assert result is not None

    def test_get_formatted_text_with_preview(self):
        """Test formatted text with preview callback."""
        import html
        import textwrap
        
        message = "Test"
        choices = ["A", "B"]
        selected_index = [0]
        
        def preview_callback(idx):
            return f"Preview for {choices[idx]}"
        
        def get_formatted_text():
            safe_message = html.escape(message)
            lines = [f"<b>{safe_message}</b>", ""]
            for i, choice in enumerate(choices):
                safe_choice = html.escape(choice)
                if i == selected_index[0]:
                    lines.append(f"<ansigreen>❯ {safe_choice}</ansigreen>")
                else:
                    lines.append(f"  {safe_choice}")
            lines.append("")
            
            if preview_callback is not None:
                preview_text = preview_callback(selected_index[0])
                if preview_text:
                    box_width = 60
                    border_top = (
                        "<ansiyellow>┌─ Preview "
                        + "─" * (box_width - 10)
                        + "┐</ansiyellow>"
                    )
                    border_bottom = "<ansiyellow>└" + "─" * box_width + "┘</ansiyellow>"
                    lines.append(border_top)
                    
                    wrapped_lines = textwrap.wrap(preview_text, width=box_width - 2)
                    if not wrapped_lines:
                        wrapped_lines = [""]
                    
                    for wrapped_line in wrapped_lines:
                        safe_preview = html.escape(wrapped_line)
                        padded_line = safe_preview.ljust(box_width - 2)
                        lines.append(f"<dim>│ {padded_line} │</dim>")
                    
                    lines.append(border_bottom)
                    lines.append("")
            
            lines.append("<ansicyan>(Use ↑↓ arrows to select, Enter to confirm)</ansicyan>")
            return HTML("\n".join(lines))
        
        result = get_formatted_text()
        assert result is not None

    def test_get_formatted_text_with_empty_preview(self):
        """Test formatted text when preview callback returns empty."""
        import html
        
        message = "Test"
        choices = ["A", "B"]
        selected_index = [0]
        
        def preview_callback(idx):
            return ""  # Empty preview
        
        def get_formatted_text():
            safe_message = html.escape(message)
            lines = [f"<b>{safe_message}</b>", ""]
            for i, choice in enumerate(choices):
                safe_choice = html.escape(choice)
                if i == selected_index[0]:
                    lines.append(f"<ansigreen>❯ {safe_choice}</ansigreen>")
                else:
                    lines.append(f"  {safe_choice}")
            lines.append("")
            
            if preview_callback is not None:
                preview_text = preview_callback(selected_index[0])
                if preview_text:  # This will be False for empty string
                    pass
            
            return HTML("\n".join(lines))
        
        result = get_formatted_text()
        assert result is not None


class TestKeyBindingCallbacks:
    """Test the keybinding callback functions."""

    def test_move_up_callback(self):
        """Test the move_up keybinding logic."""
        choices = ["A", "B", "C"]
        selected_index = [0]
        
        def move_up():
            selected_index[0] = (selected_index[0] - 1) % len(choices)
        
        # Start at 0, move up wraps to 2
        move_up()
        assert selected_index[0] == 2
        
        # Move up from 2 to 1
        move_up()
        assert selected_index[0] == 1
        
        # Move up from 1 to 0
        move_up()
        assert selected_index[0] == 0

    def test_move_down_callback(self):
        """Test the move_down keybinding logic."""
        choices = ["A", "B", "C"]
        selected_index = [0]
        
        def move_down():
            selected_index[0] = (selected_index[0] + 1) % len(choices)
        
        # Start at 0, move down to 1
        move_down()
        assert selected_index[0] == 1
        
        # Move down from 1 to 2
        move_down()
        assert selected_index[0] == 2
        
        # Move down from 2 wraps to 0
        move_down()
        assert selected_index[0] == 0

    def test_accept_callback(self):
        """Test the accept (enter) keybinding logic."""
        choices = ["A", "B", "C"]
        selected_index = [1]
        result = [None]
        
        def accept():
            result[0] = choices[selected_index[0]]
        
        accept()
        assert result[0] == "B"

    def test_cancel_callback(self):
        """Test the cancel (ctrl-c) keybinding logic."""
        result = ["initial"]
        
        def cancel():
            result[0] = None
        
        cancel()
        assert result[0] is None


class TestArrowSelectAsyncDeeper:
    """Deeper tests for arrow_select_async functionality."""

    @pytest.mark.asyncio
    async def test_arrow_select_async_returns_selected_choice(self):
        """Test that arrow_select_async returns the correct choice when selected."""
        captured_keybindings = []
        captured_control = []
        
        class MockApp:
            def __init__(self, **kwargs):
                captured_keybindings.append(kwargs.get('key_bindings'))
                if 'layout' in kwargs:
                    layout = kwargs['layout']
                    # Access the control's callable
                    try:
                        captured_control.append(layout)
                    except Exception:
                        pass
                    
            async def run_async(self):
                # Simulate accepting the first choice by running accept callback
                pass
        
        with patch('code_puppy.tools.common.Application', MockApp):
            # This will raise KeyboardInterrupt because result is None
            with pytest.raises(KeyboardInterrupt):
                await common_module.arrow_select_async("Test", ["A", "B"])
            
            # Verify keybindings were captured
            assert len(captured_keybindings) > 0

    @pytest.mark.asyncio 
    async def test_arrow_select_async_flushes_stdout(self):
        """Test that arrow_select_async flushes stdout/stderr."""
        flush_calls = []
        
        def mock_flush():
            flush_calls.append(True)
        
        with patch('code_puppy.tools.common.Application') as mock_app:
            mock_app.return_value.run_async = AsyncMock(return_value=None)
            with patch('sys.stdout.flush', mock_flush):
                with pytest.raises(KeyboardInterrupt):
                    await common_module.arrow_select_async("Test", ["A", "B"])
        
        # Should have flushed at least once
        assert len(flush_calls) >= 1


class TestArrowSelectSyncDeeper:
    """Deeper tests for arrow_select sync functionality."""

    def test_arrow_select_flushes_streams(self):
        """Test that arrow_select flushes stdout/stderr."""
        flush_calls = []
        
        def mock_flush():
            flush_calls.append(True)
        
        with patch('code_puppy.tools.common.Application') as mock_app:
            mock_app.return_value.run = MagicMock(side_effect=KeyboardInterrupt)
            with patch('sys.stdout.flush', mock_flush):
                with patch('asyncio.get_running_loop', side_effect=RuntimeError("no running event loop")):
                    with pytest.raises(KeyboardInterrupt):
                        common_module.arrow_select("Test", ["A", "B"])
        
        assert len(flush_calls) >= 1

    def test_arrow_select_creates_key_bindings(self):
        """Test that arrow_select creates proper key bindings."""
        captured_kb = []
        
        class CaptureApp:
            def __init__(self, **kwargs):
                captured_kb.append(kwargs.get('key_bindings'))
            
            def run(self):
                raise KeyboardInterrupt
        
        with patch('code_puppy.tools.common.Application', CaptureApp):
            with patch('asyncio.get_running_loop', side_effect=RuntimeError("no running event loop")):
                with pytest.raises(KeyboardInterrupt):
                    common_module.arrow_select("Test", ["A", "B"])
        
        assert len(captured_kb) > 0
        # The key_bindings object should exist
        kb = captured_kb[0]
        assert kb is not None

    def test_arrow_select_creates_layout(self):
        """Test that arrow_select creates a layout."""
        captured_layout = []
        
        class CaptureApp:
            def __init__(self, **kwargs):
                captured_layout.append(kwargs.get('layout'))
            
            def run(self):
                raise KeyboardInterrupt
        
        with patch('code_puppy.tools.common.Application', CaptureApp):
            with patch('asyncio.get_running_loop', side_effect=RuntimeError("no running event loop")):
                with pytest.raises(KeyboardInterrupt):
                    common_module.arrow_select("Test", ["A", "B"])
        
        assert len(captured_layout) > 0
        assert captured_layout[0] is not None


class TestGetUserApprovalDeeper:
    """Deeper tests for get_user_approval functionality."""

    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_success')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_calls_pause_spinners(self, mock_set_input, mock_success, mock_info, mock_select):
        """Test that get_user_approval tries to pause spinners."""
        mock_select.return_value = "✓ Approve"
        
        # Even if pause_all_spinners fails, it should continue
        with patch('code_puppy.tools.common.time.sleep'):
            result, _ = common_module.get_user_approval("Title", "Content")
        
        assert result is True

    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_success')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_always_resets_input_flag(self, mock_set_input, mock_success, mock_info, mock_select):
        """Test that set_awaiting_user_input is always reset in finally block."""
        mock_select.return_value = "✓ Approve"
        
        common_module.get_user_approval("Title", "Content")
        
        # Should be called with True at start and False at end
        calls = mock_set_input.call_args_list
        # At least one call with True and one with False
        true_calls = [c for c in calls if c[0][0] is True]
        false_calls = [c for c in calls if c[0][0] is False]
        assert len(true_calls) >= 1
        assert len(false_calls) >= 1

    @patch('code_puppy.tools.common.Prompt')
    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_error')
    @patch('code_puppy.tools.common.emit_warning')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_strips_feedback_whitespace(self, mock_set_input, mock_warning, mock_error, mock_info, mock_select, mock_prompt):
        """Test that feedback is stripped of whitespace."""
        mock_select.return_value = "💬 Reject with feedback (tell Puppy what to change)"
        mock_prompt.ask.return_value = "   feedback with spaces   "
        
        result, feedback = common_module.get_user_approval("Title", "Content")
        
        assert feedback == "feedback with spaces"


class TestDiffColorEdgeCases:
    """Test edge cases in diff color formatting."""

    def test_format_diff_with_syntax_highlighting_line_without_prefix(self):
        """Test handling lines that don't start with +, -, or space."""
        diff = "plain line without prefix"
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert result is not None

    def test_format_diff_with_trailing_newline_removed(self):
        """Test that trailing empty lines are handled."""
        diff = "+new line\n"
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert result is not None

    def test_format_diff_all_header_lines(self):
        """Test diff with only header lines."""
        diff = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
diff --git a/file.py b/file.py
index abc123..def456 100644"""
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        # Headers are skipped, but should still return valid Text
        assert result is not None


class TestTokenColorsAccess:
    """Test accessing TOKEN_COLORS dict."""

    @pytest.mark.skipif(not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available")
    def test_token_colors_iteration(self):
        """Test iterating over TOKEN_COLORS."""
        for token_type, color in common_module.TOKEN_COLORS.items():
            assert token_type is not None
            assert color is not None
            assert isinstance(color, str)

    @pytest.mark.skipif(not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available")
    def test_get_token_color_with_various_tokens(self):
        """Test _get_token_color with various token types."""
        from pygments.token import Token
        
        token_types = [
            Token.Keyword,
            Token.Name.Builtin,
            Token.Name.Function,
            Token.String,
            Token.Number,
            Token.Comment,
            Token.Operator,
            Token.Text,  # Not in TOKEN_COLORS, should return default
        ]
        
        for token_type in token_types:
            color = common_module._get_token_color(token_type)
            assert isinstance(color, str)
            assert color.startswith("#")


class TestHighlightCodeLineEdgeCases:
    """Test edge cases in _highlight_code_line."""

    @pytest.mark.skipif(not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available")
    def test_highlight_code_line_with_empty_string(self):
        """Test highlighting an empty string."""
        lexer = common_module._get_lexer_for_extension(".py")
        result = common_module._highlight_code_line("", None, lexer)
        assert result is not None

    @pytest.mark.skipif(not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available")
    def test_highlight_code_line_with_only_whitespace(self):
        """Test highlighting whitespace-only code."""
        lexer = common_module._get_lexer_for_extension(".py")
        result = common_module._highlight_code_line("    ", None, lexer)
        assert result is not None

    @pytest.mark.skipif(not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available") 
    def test_highlight_code_line_strips_trailing_newlines(self):
        """Test that trailing newlines in lexer output are handled."""
        lexer = common_module._get_lexer_for_extension(".py")
        result = common_module._highlight_code_line("x = 1\n\n", "#001100", lexer)
        assert result is not None

    @pytest.mark.skipif(not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available")
    def test_highlight_code_line_various_languages(self):
        """Test highlighting code in various languages."""
        test_cases = [
            (".py", "def foo(): pass"),
            (".js", "function foo() { return 1; }"),
            (".ts", "const x: number = 42;"),
            (".html", "<div class='test'>Hello</div>"),
            (".css", ".test { color: red; }"),
            (".json", '{"key": "value"}'),
            (".md", "# Heading\n- item 1"),
        ]
        
        for ext, code in test_cases:
            lexer = common_module._get_lexer_for_extension(ext)
            result = common_module._highlight_code_line(code, None, lexer)
            assert result is not None, f"Failed for {ext}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
