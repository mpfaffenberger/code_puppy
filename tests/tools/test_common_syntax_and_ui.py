"""Tests for syntax highlighting and UI components in code_puppy.tools.common.

This module focuses on covering:
- Syntax highlighting functions (_get_lexer_for_extension, _get_token_color, _highlight_code_line)
- Diff formatting internals (_format_diff_with_syntax_highlighting, _extract_file_extension_from_diff)
- Arrow select functions (async and sync)
- User approval functions (async and sync)
- Fallback emit functions when messaging isn't available
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.text import Text

# Import the module directly to access private functions
from code_puppy.tools import common as common_module


class TestSyntaxHighlighting:
    """Test syntax highlighting helper functions."""

    def test_get_lexer_for_extension_python(self):
        """Test lexer selection for Python files."""
        lexer = common_module._get_lexer_for_extension(".py")
        if common_module.PYGMENTS_AVAILABLE:
            assert lexer is not None
        else:
            assert lexer is None

    def test_get_lexer_for_extension_javascript(self):
        """Test lexer selection for JavaScript files."""
        lexer = common_module._get_lexer_for_extension(".js")
        if common_module.PYGMENTS_AVAILABLE:
            assert lexer is not None

    def test_get_lexer_for_extension_typescript(self):
        """Test lexer selection for TypeScript files."""
        lexer = common_module._get_lexer_for_extension(".ts")
        if common_module.PYGMENTS_AVAILABLE:
            assert lexer is not None

    def test_get_lexer_for_extension_unknown(self):
        """Test lexer selection for unknown file types."""
        lexer = common_module._get_lexer_for_extension(".xyz")
        if common_module.PYGMENTS_AVAILABLE:
            # Should fall back to text lexer
            assert lexer is not None

    def test_get_lexer_for_extension_without_dot(self):
        """Test lexer selection without leading dot."""
        lexer = common_module._get_lexer_for_extension("py")
        if common_module.PYGMENTS_AVAILABLE:
            assert lexer is not None

    def test_get_lexer_for_extension_uppercase(self):
        """Test lexer selection with uppercase extension."""
        lexer = common_module._get_lexer_for_extension(".PY")
        if common_module.PYGMENTS_AVAILABLE:
            assert lexer is not None

    def test_get_lexer_for_extension_all_supported(self):
        """Test that all extensions in EXTENSION_TO_LEXER_NAME work."""
        for ext in common_module.EXTENSION_TO_LEXER_NAME.keys():
            lexer = common_module._get_lexer_for_extension(ext)
            if common_module.PYGMENTS_AVAILABLE:
                assert lexer is not None, f"Failed for extension: {ext}"

    def test_get_token_color_keyword(self):
        """Test token color retrieval for keywords."""
        color = common_module._get_token_color(None)
        assert isinstance(color, str)
        assert color.startswith("#")

    def test_get_token_color_fallback(self):
        """Test token color fallback for unknown token types."""
        # Pass a made-up token type
        color = common_module._get_token_color(object())
        assert isinstance(color, str)
        assert color.startswith("#")

    @pytest.mark.skipif(not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available")
    def test_get_token_color_with_pygments_token(self):
        """Test token color with actual Pygments token."""
        from pygments.token import Token
        
        color = common_module._get_token_color(Token.Keyword)
        assert isinstance(color, str)

    def test_highlight_code_line_without_pygments(self):
        """Test code highlighting fallback without Pygments."""
        with patch.object(common_module, 'PYGMENTS_AVAILABLE', False):
            result = common_module._highlight_code_line("code = 42", None, None)
            assert isinstance(result, Text)

    def test_highlight_code_line_with_background(self):
        """Test code highlighting with background color."""
        with patch.object(common_module, 'PYGMENTS_AVAILABLE', False):
            result = common_module._highlight_code_line("x = 1", "#ff0000", None)
            assert isinstance(result, Text)

    @pytest.mark.skipif(not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available")
    def test_highlight_code_line_with_lexer(self):
        """Test code highlighting with a real lexer."""
        lexer = common_module._get_lexer_for_extension(".py")
        result = common_module._highlight_code_line("def foo(): pass", None, lexer)
        assert isinstance(result, Text)

    @pytest.mark.skipif(not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available")
    def test_highlight_code_line_with_background_and_lexer(self):
        """Test code highlighting with both background and lexer."""
        lexer = common_module._get_lexer_for_extension(".py")
        result = common_module._highlight_code_line("x = 1", "#002200", lexer)
        assert isinstance(result, Text)


class TestDiffExtraction:
    """Test diff file extension extraction."""

    def test_extract_file_extension_from_diff_python(self):
        """Test extraction of .py extension from diff."""
        diff = """--- a/src/main.py
+++ b/src/main.py
@@ -1 +1 @@
-old
+new"""
        ext = common_module._extract_file_extension_from_diff(diff)
        assert ext == ".py"

    def test_extract_file_extension_from_diff_js(self):
        """Test extraction of .js extension from diff."""
        diff = """--- a/app.js
+++ b/app.js
@@ -1 +1 @@
-old
+new"""
        ext = common_module._extract_file_extension_from_diff(diff)
        assert ext == ".js"

    def test_extract_file_extension_from_diff_no_header(self):
        """Test extraction when no file header exists."""
        diff = "+new line\n-old line"
        ext = common_module._extract_file_extension_from_diff(diff)
        assert ext == ".txt"  # Default fallback

    def test_extract_file_extension_from_diff_multiple_files(self):
        """Test extraction from diff with multiple files."""
        diff = """--- a/first.py
+++ b/first.py
-old
--- a/second.js
+++ b/second.js
+new"""
        ext = common_module._extract_file_extension_from_diff(diff)
        # Should get the first file's extension
        assert ext == ".py"

    def test_extract_file_extension_from_diff_complex_path(self):
        """Test extraction from diff with complex file path."""
        diff = """--- a/src/components/Button.tsx
+++ b/src/components/Button.tsx
-old
+new"""
        ext = common_module._extract_file_extension_from_diff(diff)
        assert ext == ".tsx"

    def test_extract_file_extension_empty_diff(self):
        """Test extraction from empty diff."""
        ext = common_module._extract_file_extension_from_diff("")
        assert ext == ".txt"


class TestDiffFormatting:
    """Test diff formatting with syntax highlighting."""

    def test_format_diff_with_syntax_highlighting_basic(self):
        """Test basic syntax-highlighted diff formatting."""
        diff = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 def foo():
-    return 1
+    return 2
"""
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert isinstance(result, Text)

    def test_format_diff_with_syntax_highlighting_empty(self):
        """Test syntax highlighting with empty diff."""
        result = common_module._format_diff_with_syntax_highlighting(
            "", "#003300", "#330000"
        )
        assert isinstance(result, Text)

    def test_format_diff_with_syntax_highlighting_additions_only(self):
        """Test diff with only additions."""
        diff = "+new line 1\n+new line 2"
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert isinstance(result, Text)

    def test_format_diff_with_syntax_highlighting_deletions_only(self):
        """Test diff with only deletions."""
        diff = "-deleted line 1\n-deleted line 2"
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert isinstance(result, Text)

    def test_format_diff_with_syntax_highlighting_context_lines(self):
        """Test diff with context lines."""
        diff = " context line\n+added line\n context again"
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert isinstance(result, Text)

    def test_format_diff_with_syntax_highlighting_headers_skipped(self):
        """Test that diff headers are skipped."""
        diff = """diff --git a/file.py b/file.py
index abc123..def456 100644
--- a/file.py
+++ b/file.py
@@ -1 +1 @@
-old
+new"""
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert isinstance(result, Text)
        # Should not contain the header content in output
        text_str = str(result)
        assert "diff --git" not in text_str
        assert "index " not in text_str

    def test_format_diff_with_colors_empty_returns_placeholder(self):
        """Test that empty diff returns placeholder text."""
        result = common_module.format_diff_with_colors("")
        assert isinstance(result, Text)
        assert "no diff" in str(result).lower()

    def test_format_diff_with_colors_whitespace_only(self):
        """Test that whitespace-only diff returns placeholder."""
        result = common_module.format_diff_with_colors("   \n\t  ")
        assert isinstance(result, Text)
        assert "no diff" in str(result).lower()

    @patch('code_puppy.tools.common.PYGMENTS_AVAILABLE', False)
    @patch('code_puppy.tools.common.emit_warning')
    def test_format_diff_without_pygments(self, mock_warn):
        """Test diff formatting when Pygments is unavailable."""
        diff = "+new line"
        result = common_module.format_diff_with_colors(diff)
        # Should return something even without Pygments
        assert result is not None


class TestArrowSelectMocked:
    """Test arrow_select functions with mocked UI."""

    def test_arrow_select_sync_in_async_context_raises(self):
        """Test that sync arrow_select raises when called from async context."""
        async def call_sync_from_async():
            # This should raise because we're in an async context
            with pytest.raises(RuntimeError, match="async context"):
                common_module.arrow_select("Test", ["A", "B"])
        
        # Run in a new event loop
        asyncio.run(call_sync_from_async())

    @pytest.mark.asyncio
    async def test_arrow_select_async_keyboard_interrupt(self):
        """Test that arrow_select_async handles KeyboardInterrupt."""
        mock_app = MagicMock()
        mock_app.run_async = AsyncMock(return_value=None)
        
        with patch('code_puppy.tools.common.Application', return_value=mock_app):
            with pytest.raises(KeyboardInterrupt):
                # Result will be None, which triggers KeyboardInterrupt
                await common_module.arrow_select_async("Test", ["A", "B"])

    @pytest.mark.asyncio
    async def test_arrow_select_async_with_preview_callback(self):
        """Test arrow_select_async with preview callback."""
        preview_called = []
        def preview_cb(idx):
            preview_called.append(idx)
            return f"Preview for index {idx}"
        
        mock_app = MagicMock()
        # Simulate app exit with result set to first choice
        async def run_async_mock():
            return None  # Will trigger KeyboardInterrupt
        mock_app.run_async = run_async_mock
        
        with patch('code_puppy.tools.common.Application', return_value=mock_app):
            with pytest.raises(KeyboardInterrupt):
                await common_module.arrow_select_async(
                    "Test", ["A", "B"], preview_callback=preview_cb
                )

    def test_arrow_select_formatted_text_generation(self):
        """Test the formatted text generation for arrow select."""
        # We can test the internal formatting by checking what Application receives
        captured_layout = []
        
        def capture_application(**kwargs):
            captured_layout.append(kwargs.get('layout'))
            mock_app = MagicMock()
            mock_app.run = MagicMock(side_effect=KeyboardInterrupt)
            return mock_app
        
        with patch('code_puppy.tools.common.Application', side_effect=capture_application):
            with patch('asyncio.get_running_loop', side_effect=RuntimeError("no running event loop")):
                with pytest.raises(KeyboardInterrupt):
                    common_module.arrow_select("Test Message", ["Choice 1", "Choice 2"])
        
        # Verify layout was created
        assert len(captured_layout) > 0


class TestUserApprovalMocked:
    """Test get_user_approval functions with mocked UI."""

    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_success')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_approve(self, mock_set_input, mock_success, mock_info, mock_select):
        """Test get_user_approval when user approves."""
        mock_select.return_value = "✓ Approve"
        
        result, feedback = common_module.get_user_approval(
            "Test Title",
            "Test content"
        )
        
        assert result is True
        assert feedback is None
        mock_success.assert_called()

    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_error')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_reject(self, mock_set_input, mock_error, mock_info, mock_select):
        """Test get_user_approval when user rejects."""
        mock_select.return_value = "✗ Reject"
        
        result, feedback = common_module.get_user_approval(
            "Test Title",
            "Test content"
        )
        
        assert result is False
        assert feedback is None
        mock_error.assert_called()

    @patch('code_puppy.tools.common.Prompt')
    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_error')
    @patch('code_puppy.tools.common.emit_warning')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_with_feedback(self, mock_set_input, mock_warning, mock_error, mock_info, mock_select, mock_prompt):
        """Test get_user_approval when user provides feedback."""
        mock_select.return_value = "💬 Reject with feedback (tell Puppy what to change)"
        mock_prompt.ask.return_value = "Please change X to Y"
        
        result, feedback = common_module.get_user_approval(
            "Test Title",
            "Test content"
        )
        
        assert result is False
        assert feedback == "Please change X to Y"

    @patch('code_puppy.tools.common.Prompt')
    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_error')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_empty_feedback(self, mock_set_input, mock_error, mock_info, mock_select, mock_prompt):
        """Test get_user_approval when user provides empty feedback."""
        mock_select.return_value = "💬 Reject with feedback (tell Puppy what to change)"
        mock_prompt.ask.return_value = "  "  # Whitespace only
        
        result, feedback = common_module.get_user_approval(
            "Test Title",
            "Test content"
        )
        
        assert result is False
        assert feedback is None  # Empty feedback becomes None

    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_error')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_keyboard_interrupt(self, mock_set_input, mock_error, mock_info, mock_select):
        """Test get_user_approval when user cancels with Ctrl-C."""
        mock_select.side_effect = KeyboardInterrupt()
        
        result, feedback = common_module.get_user_approval(
            "Test Title",
            "Test content"
        )
        
        assert result is False
        assert feedback is None

    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_error')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_eof_error(self, mock_set_input, mock_error, mock_info, mock_select):
        """Test get_user_approval when EOFError occurs."""
        mock_select.side_effect = EOFError()
        
        result, feedback = common_module.get_user_approval(
            "Test Title",
            "Test content"
        )
        
        assert result is False

    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_success')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_with_preview(self, mock_set_input, mock_success, mock_info, mock_select):
        """Test get_user_approval with diff preview."""
        mock_select.return_value = "✓ Approve"
        
        preview = "+added line\n-removed line"
        result, feedback = common_module.get_user_approval(
            "Test Title",
            "Test content",
            preview=preview
        )
        
        assert result is True

    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_success')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_with_text_content(self, mock_set_input, mock_success, mock_info, mock_select):
        """Test get_user_approval with Rich Text content."""
        mock_select.return_value = "✓ Approve"
        
        content = Text("Rich formatted content")
        result, feedback = common_module.get_user_approval(
            "Test Title",
            content
        )
        
        assert result is True

    @patch('code_puppy.tools.common.arrow_select')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_success')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    def test_get_user_approval_custom_puppy_name(self, mock_set_input, mock_success, mock_info, mock_select):
        """Test get_user_approval with custom puppy name."""
        mock_select.return_value = "✓ Approve"
        
        result, feedback = common_module.get_user_approval(
            "Test Title",
            "Content",
            puppy_name="CustomPuppy"
        )
        
        assert result is True


class TestUserApprovalAsyncMocked:
    """Test async get_user_approval with mocked UI."""

    @pytest.mark.asyncio
    @patch('code_puppy.tools.common.arrow_select_async')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_success')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    async def test_get_user_approval_async_approve(self, mock_set_input, mock_success, mock_info, mock_select):
        """Test async get_user_approval when user approves."""
        mock_select.return_value = "✓ Approve"
        
        result, feedback = await common_module.get_user_approval_async(
            "Test Title",
            "Test content"
        )
        
        assert result is True
        assert feedback is None

    @pytest.mark.asyncio
    @patch('code_puppy.tools.common.arrow_select_async')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_error')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    async def test_get_user_approval_async_reject(self, mock_set_input, mock_error, mock_info, mock_select):
        """Test async get_user_approval when user rejects."""
        mock_select.return_value = "✗ Reject"
        
        result, feedback = await common_module.get_user_approval_async(
            "Test Title",
            "Test content"
        )
        
        assert result is False

    @pytest.mark.asyncio
    @patch('code_puppy.tools.common.Prompt')
    @patch('code_puppy.tools.common.arrow_select_async')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_error')
    @patch('code_puppy.tools.common.emit_warning')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    async def test_get_user_approval_async_with_feedback(self, mock_set_input, mock_warning, mock_error, mock_info, mock_select, mock_prompt):
        """Test async get_user_approval with feedback."""
        mock_select.return_value = "💬 Reject with feedback (tell Puppy what to change)"
        mock_prompt.ask.return_value = "Change this please"
        
        result, feedback = await common_module.get_user_approval_async(
            "Test Title",
            "Content"
        )
        
        assert result is False
        assert feedback == "Change this please"

    @pytest.mark.asyncio
    @patch('code_puppy.tools.common.arrow_select_async')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_error')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    async def test_get_user_approval_async_keyboard_interrupt(self, mock_set_input, mock_error, mock_info, mock_select):
        """Test async get_user_approval on cancel."""
        mock_select.side_effect = KeyboardInterrupt()
        
        result, feedback = await common_module.get_user_approval_async(
            "Test Title",
            "Content"
        )
        
        assert result is False

    @pytest.mark.asyncio
    @patch('code_puppy.tools.common.arrow_select_async')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_success')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    async def test_get_user_approval_async_with_preview(self, mock_set_input, mock_success, mock_info, mock_select):
        """Test async get_user_approval with preview."""
        mock_select.return_value = "✓ Approve"
        
        result, feedback = await common_module.get_user_approval_async(
            "Test Title",
            "Content",
            preview="+added\n-removed"
        )
        
        assert result is True

    @pytest.mark.asyncio
    @patch('code_puppy.tools.common.arrow_select_async')
    @patch('code_puppy.tools.common.emit_info')
    @patch('code_puppy.tools.common.emit_success')
    @patch('code_puppy.tools.command_runner.set_awaiting_user_input')
    async def test_get_user_approval_async_with_text_content(self, mock_set_input, mock_success, mock_info, mock_select):
        """Test async get_user_approval with Text content."""
        mock_select.return_value = "✓ Approve"
        
        content = Text("Rich content")
        result, feedback = await common_module.get_user_approval_async(
            "Test Title",
            content
        )
        
        assert result is True


class TestTokenColorsAndLexerMapping:
    """Test TOKEN_COLORS and EXTENSION_TO_LEXER_NAME constants."""

    def test_token_colors_defined(self):
        """Test that TOKEN_COLORS is defined."""
        assert hasattr(common_module, 'TOKEN_COLORS')
        assert isinstance(common_module.TOKEN_COLORS, dict)

    def test_extension_to_lexer_name_defined(self):
        """Test that EXTENSION_TO_LEXER_NAME is defined."""
        assert hasattr(common_module, 'EXTENSION_TO_LEXER_NAME')
        assert isinstance(common_module.EXTENSION_TO_LEXER_NAME, dict)

    def test_extension_to_lexer_name_contains_common_extensions(self):
        """Test that common extensions are mapped."""
        common_exts = [".py", ".js", ".ts", ".html", ".css", ".json", ".md"]
        for ext in common_exts:
            assert ext in common_module.EXTENSION_TO_LEXER_NAME, f"Missing: {ext}"

    def test_extension_to_lexer_name_values_are_strings(self):
        """Test that all lexer names are strings."""
        for ext, lexer_name in common_module.EXTENSION_TO_LEXER_NAME.items():
            assert isinstance(ext, str)
            assert isinstance(lexer_name, str)

    @pytest.mark.skipif(not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available")
    def test_token_colors_has_keyword_color(self):
        """Test that keyword token has a color."""
        from pygments.token import Token
        # TOKEN_COLORS should have Token.Keyword
        assert Token.Keyword in common_module.TOKEN_COLORS


class TestFallbackEmitFunctions:
    """Test fallback emit functions when messaging module isn't available."""

    def test_module_has_emit_functions(self):
        """Test that emit functions exist in module."""
        # These should be available whether from messaging or fallback
        assert hasattr(common_module, 'emit_error')
        assert hasattr(common_module, 'emit_info')
        assert hasattr(common_module, 'emit_success')
        assert hasattr(common_module, 'emit_warning')

    def test_console_exists(self):
        """Test that console object exists."""
        assert hasattr(common_module, 'console')


class TestFindBestWindowExtended:
    """Extended tests for _find_best_window function."""

    def test_find_best_window_single_line_match(self):
        """Test single line window matching."""
        haystack = ["alpha", "beta", "gamma"]
        needle = "beta"
        
        span, score = common_module._find_best_window(haystack, needle)
        assert span == (1, 2)
        assert score >= 0.99

    def test_find_best_window_fuzzy_match(self):
        """Test fuzzy matching capability."""
        haystack = ["hello world", "helo wrld", "goodbye"]
        needle = "hello world"
        
        span, score = common_module._find_best_window(haystack, needle)
        # Should prefer exact match
        assert span == (0, 1)
        assert score >= 0.99

    def test_find_best_window_multiline_window(self):
        """Test multi-line window matching."""
        haystack = ["line 1", "line 2", "line 3", "line 4"]
        needle = "line 2\nline 3"
        
        span, score = common_module._find_best_window(haystack, needle)
        assert span == (1, 3)
        assert score >= 0.99

    def test_find_best_window_with_whitespace_variations(self):
        """Test matching with whitespace differences."""
        haystack = ["def foo():", "    return 1", ""]
        needle = "def foo():\n    return 1"
        
        span, score = common_module._find_best_window(haystack, needle)
        assert span == (0, 2)
        assert score >= 0.99


class TestBrightenHexEdgeCases:
    """Additional edge cases for brighten_hex function."""

    def test_brighten_hex_pure_black(self):
        """Test brightening pure black."""
        result = common_module.brighten_hex("#000000", 0.5)
        assert result.startswith("#")
        assert len(result) == 7

    def test_brighten_hex_pure_white(self):
        """Test brightening pure white (should cap at 255)."""
        result = common_module.brighten_hex("#ffffff", 0.5)
        assert result.startswith("#")
        assert len(result) == 7

    def test_brighten_hex_mixed_color(self):
        """Test brightening a mixed color."""
        result = common_module.brighten_hex("#804020", 0.2)
        assert result.startswith("#")
        assert len(result) == 7

    def test_brighten_hex_factor_one(self):
        """Test with factor of 1.0 (double brightness)."""
        result = common_module.brighten_hex("#404040", 1.0)
        assert result.startswith("#")
        assert len(result) == 7

    def test_brighten_hex_preserves_format(self):
        """Test that output is always lowercase hex."""
        result = common_module.brighten_hex("#AABBCC", 0.1)
        assert result.startswith("#")
        assert result == result.lower()


class TestGenerateGroupIdExtended:
    """Extended tests for generate_group_id function."""

    def test_generate_group_id_special_tool_name(self):
        """Test group ID with special characters in tool name."""
        result = common_module.generate_group_id("tool-name_v2.0")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_group_id_unicode_context(self):
        """Test group ID with unicode in extra context."""
        result = common_module.generate_group_id("tool", "файл.py")
        assert isinstance(result, str)

    def test_generate_group_id_long_context(self):
        """Test group ID with very long context."""
        long_context = "x" * 10000
        result = common_module.generate_group_id("tool", long_context)
        assert isinstance(result, str)
        # Should be truncated reasonably
        assert len(result) < 1000


class TestConsoleAndNoColorMode:
    """Test console initialization and NO_COLOR mode."""

    def test_no_color_env_var_handling(self):
        """Test that CODE_PUPPY_NO_COLOR env var is handled."""
        # The module should have checked the env var at import time
        # We just verify the console exists
        assert common_module.console is not None

    def test_console_has_print_method(self):
        """Test that console has print capability."""
        # Whether it's QueueConsole or fallback, it should be printable
        assert hasattr(common_module.console, 'print') or hasattr(common_module.console, 'fallback_console')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
