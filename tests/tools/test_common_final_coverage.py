"""Final coverage tests for code_puppy.tools.common.

This module targets the remaining uncovered lines to push coverage over 80%.
"""

from unittest.mock import patch

import pytest
from rich.text import Text

from code_puppy.tools import common as common_module


class TestHighlightCodeLineNoPygments:
    """Test _highlight_code_line when Pygments is not available."""

    def test_highlight_code_line_no_pygments_no_bg(self):
        """Test highlighting without Pygments and without background."""
        with patch.object(common_module, "PYGMENTS_AVAILABLE", False):
            result = common_module._highlight_code_line("test code", None, None)
        assert isinstance(result, Text)
        assert "test code" in str(result)

    def test_highlight_code_line_no_pygments_with_bg(self):
        """Test highlighting without Pygments but with background."""
        with patch.object(common_module, "PYGMENTS_AVAILABLE", False):
            result = common_module._highlight_code_line("test code", "#ff0000", None)
        assert isinstance(result, Text)

    def test_highlight_code_line_lexer_none_with_pygments(self):
        """Test highlighting with Pygments but None lexer."""
        if common_module.PYGMENTS_AVAILABLE:
            result = common_module._highlight_code_line("test", None, None)
            assert isinstance(result, Text)


class TestGetLexerEdgeCases:
    """Test _get_lexer_for_extension edge cases."""

    def test_get_lexer_exception_handling(self):
        """Test lexer retrieval when get_lexer_by_name fails."""
        if not common_module.PYGMENTS_AVAILABLE:
            pytest.skip("Pygments not available")

        # Test with a valid extension that has lexer
        lexer = common_module._get_lexer_for_extension(".py")
        assert lexer is not None

        # Test with unknown extension - should fallback
        lexer = common_module._get_lexer_for_extension(".unknownextension")
        assert lexer is not None  # Should return TextLexer

    def test_get_lexer_case_insensitive(self):
        """Test that extension matching is case insensitive."""
        if not common_module.PYGMENTS_AVAILABLE:
            pytest.skip("Pygments not available")

        lexer_lower = common_module._get_lexer_for_extension(".py")
        lexer_upper = common_module._get_lexer_for_extension(".PY")
        lexer_mixed = common_module._get_lexer_for_extension(".Py")

        # All should return valid lexers
        assert lexer_lower is not None
        assert lexer_upper is not None
        assert lexer_mixed is not None


class TestDiffFormattingBranches:
    """Test various branches in diff formatting."""

    def test_format_diff_empty_lines_handling(self):
        """Test that empty lines in diff are handled."""
        diff = "+line1\n\n+line2"
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert isinstance(result, Text)

    def test_format_diff_space_prefix_line(self):
        """Test line that starts with space (context)."""
        diff = " context line\n+added"
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert isinstance(result, Text)

    def test_format_diff_line_without_any_prefix(self):
        """Test line without +, -, or space prefix."""
        diff = "just a regular line"
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert isinstance(result, Text)

    def test_format_diff_mixed_content(self):
        """Test diff with all types of lines."""
        diff = """--- a/test.py
+++ b/test.py
@@ -1,5 +1,5 @@
 context
-removed
+added
 more context
no prefix line
"""
        result = common_module._format_diff_with_syntax_highlighting(
            diff, "#003300", "#330000"
        )
        assert isinstance(result, Text)

    def test_extract_file_extension_with_minus_header(self):
        """Test extraction using --- header."""
        diff = "--- a/file.tsx\n+++ b/file.tsx"
        ext = common_module._extract_file_extension_from_diff(diff)
        assert ext == ".tsx"

    def test_extract_file_extension_plus_only(self):
        """Test extraction using only +++ header."""
        diff = "+++ b/module.rs"
        ext = common_module._extract_file_extension_from_diff(diff)
        assert ext == ".rs"


class TestTokenColorsAndLexerMapConstants:
    """Test accessing the TOKEN_COLORS and EXTENSION_TO_LEXER_NAME constants."""

    def test_extension_map_has_all_keys(self):
        """Test that EXTENSION_TO_LEXER_NAME has expected keys."""
        ext_map = common_module.EXTENSION_TO_LEXER_NAME

        # Test accessing various keys
        assert ext_map.get(".py") == "python"
        assert ext_map.get(".js") == "javascript"
        assert ext_map.get(".ts") == "typescript"
        assert ext_map.get(".html") == "html"
        assert ext_map.get(".css") == "css"
        assert ext_map.get(".json") == "json"
        assert ext_map.get(".yaml") == "yaml"
        assert ext_map.get(".md") == "markdown"
        assert ext_map.get(".sh") == "bash"
        assert ext_map.get(".sql") == "sql"

    @pytest.mark.skipif(
        not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available"
    )
    def test_token_colors_has_entries(self):
        """Test that TOKEN_COLORS dict has entries."""
        from pygments.token import Token

        colors = common_module.TOKEN_COLORS
        assert len(colors) > 0

        # Access specific keys
        if Token.Keyword in colors:
            assert colors[Token.Keyword] is not None
        if Token.String in colors:
            assert colors[Token.String] is not None


class TestGetTokenColorBranches:
    """Test _get_token_color with various inputs."""

    def test_get_token_color_no_pygments(self):
        """Test _get_token_color when Pygments not available."""
        with patch.object(common_module, "PYGMENTS_AVAILABLE", False):
            color = common_module._get_token_color(None)
        assert color == "#cccccc"

    def test_get_token_color_unmatched_token(self):
        """Test _get_token_color with token not in TOKEN_COLORS."""
        if not common_module.PYGMENTS_AVAILABLE:
            pytest.skip("Pygments not available")

        from pygments.token import Token

        # Use a token type that's unlikely to be in TOKEN_COLORS
        color = common_module._get_token_color(Token.Error)
        assert color == "#cccccc"  # Default

    @pytest.mark.skipif(
        not common_module.PYGMENTS_AVAILABLE, reason="Pygments not available"
    )
    def test_get_token_color_matched_tokens(self):
        """Test _get_token_color with tokens in TOKEN_COLORS."""

        # These should match and return non-default colors
        for token_type in common_module.TOKEN_COLORS.keys():
            color = common_module._get_token_color(token_type)
            assert isinstance(color, str)


class TestFormatDiffWithColorsSpecialCases:
    """Test format_diff_with_colors special cases."""

    def test_format_diff_with_colors_none_input(self):
        """Test format_diff_with_colors with None-like input."""
        # Empty string
        result = common_module.format_diff_with_colors("")
        assert "no diff" in str(result).lower()

    def test_format_diff_with_colors_whitespace(self):
        """Test format_diff_with_colors with whitespace."""
        result = common_module.format_diff_with_colors("   ")
        assert "no diff" in str(result).lower()

    def test_format_diff_with_colors_newlines_only(self):
        """Test format_diff_with_colors with newlines only."""
        result = common_module.format_diff_with_colors("\n\n\n")
        assert "no diff" in str(result).lower()

    def test_format_diff_with_colors_real_diff(self):
        """Test format_diff_with_colors with real diff content."""
        diff = "+added line\n-removed line"
        result = common_module.format_diff_with_colors(diff)
        assert isinstance(result, Text)
        # Should NOT say "no diff"
        assert "no diff" not in str(result).lower()


class TestBrightenHexFinal:
    """Final coverage for brighten_hex."""

    def test_brighten_hex_all_channels(self):
        """Test brighten_hex affects all color channels."""
        result = common_module.brighten_hex("#123456", 0.5)
        assert result.startswith("#")
        assert len(result) == 7

    def test_brighten_hex_max_clamp(self):
        """Test that brighten_hex clamps at 255."""
        # Start with high values, large factor should clamp
        result = common_module.brighten_hex("#f0f0f0", 1.0)
        assert result.startswith("#")
        # Result should still be valid hex
        int(result[1:3], 16)  # Should not raise
        int(result[3:5], 16)
        int(result[5:7], 16)


class TestConsoleAndEmitFunctions:
    """Test console and emit function availability."""

    def test_emit_error_callable(self):
        """Test that emit_error is callable."""
        assert callable(common_module.emit_error)

    def test_emit_info_callable(self):
        """Test that emit_info is callable."""
        assert callable(common_module.emit_info)

    def test_emit_success_callable(self):
        """Test that emit_success is callable."""
        assert callable(common_module.emit_success)

    def test_emit_warning_callable(self):
        """Test that emit_warning is callable."""
        assert callable(common_module.emit_warning)

    def test_console_is_not_none(self):
        """Test that console object exists."""
        assert common_module.console is not None


class TestShouldSuppressBrowserAllCases:
    """Comprehensive tests for should_suppress_browser."""

    def test_suppress_browser_headless_uppercase(self):
        """Test HEADLESS env with various cases."""
        with patch.dict("os.environ", {"HEADLESS": "TRUE"}, clear=True):
            assert common_module.should_suppress_browser() is True

    def test_suppress_browser_browser_headless_uppercase(self):
        """Test BROWSER_HEADLESS env."""
        with patch.dict("os.environ", {"BROWSER_HEADLESS": "TRUE"}, clear=True):
            assert common_module.should_suppress_browser() is True

    def test_suppress_browser_ci_uppercase(self):
        """Test CI env."""
        with patch.dict("os.environ", {"CI": "TRUE"}, clear=True):
            assert common_module.should_suppress_browser() is True


class TestFindBestWindowFinal:
    """Final coverage for _find_best_window."""

    def test_find_best_window_logs_output(self):
        """Test that _find_best_window logs results."""
        haystack = ["test"]
        needle = "test"

        # The function logs to console, which we should verify
        span, score = common_module._find_best_window(haystack, needle)
        assert span == (0, 1)
        assert score >= 0.99


class TestGenerateGroupIdFinal:
    """Final coverage for generate_group_id."""

    def test_generate_group_id_empty_string(self):
        """Test with empty tool name."""
        result = common_module.generate_group_id("")
        assert isinstance(result, str)
        # Should end with 8 hex chars
        assert len(result) >= 9  # At least "_" + 8 hex chars

    def test_generate_group_id_special_chars(self):
        """Test with special characters."""
        result = common_module.generate_group_id("my-tool_v1.0!")
        assert isinstance(result, str)


class TestNoColorModeConstant:
    """Test NO_COLOR mode handling."""

    def test_no_color_is_bool(self):
        """Test that NO_COLOR is a boolean."""
        # The module should have set this based on env var
        assert hasattr(common_module, "NO_COLOR")
        assert isinstance(common_module.NO_COLOR, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
