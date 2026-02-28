"""Tests for remaining coverage gaps in code_puppy/tools/common.py."""

from unittest.mock import patch

import pytest
from rich.text import Text


class TestPygmentsImportFallback:
    def test_pygments_available(self):
        from code_puppy.tools.common import PYGMENTS_AVAILABLE

        assert isinstance(PYGMENTS_AVAILABLE, bool)


class TestShouldSuppressBrowser:
    def test_in_pytest(self):
        from code_puppy.tools.common import should_suppress_browser

        # We're running under pytest, so PYTEST_CURRENT_TEST is set
        assert should_suppress_browser() is True

    @patch.dict("os.environ", {"HEADLESS": "true"}, clear=False)
    def test_headless(self):
        from code_puppy.tools.common import should_suppress_browser

        assert should_suppress_browser() is True


class TestShouldIgnorePath:
    def test_ignore_pycache(self):
        from code_puppy.tools.common import should_ignore_path

        assert should_ignore_path("__pycache__/foo.pyc")

    def test_allow_normal(self):
        from code_puppy.tools.common import should_ignore_path

        assert not should_ignore_path("src/main.py")

    def test_ignore_node_modules(self):
        from code_puppy.tools.common import should_ignore_path

        assert should_ignore_path("node_modules/foo")


class TestShouldIgnoreDirPath:
    def test_ignore_git(self):
        from code_puppy.tools.common import should_ignore_dir_path

        assert should_ignore_dir_path(".git")

    def test_allow_src(self):
        from code_puppy.tools.common import should_ignore_dir_path

        assert not should_ignore_dir_path("src")


class TestGetLexerForExtension:
    def test_known_extension(self):
        from code_puppy.tools.common import _get_lexer_for_extension

        lexer = _get_lexer_for_extension(".py")
        assert lexer is not None

    def test_unknown_extension(self):
        from code_puppy.tools.common import _get_lexer_for_extension

        lexer = _get_lexer_for_extension(".xyz_unknown")
        assert lexer is not None


class TestGetTokenColor:
    def test_keyword(self):
        from pygments.token import Token

        from code_puppy.tools.common import _get_token_color

        color = _get_token_color(Token.Keyword)
        assert isinstance(color, str)

    def test_unknown(self):
        from pygments.token import Token

        from code_puppy.tools.common import _get_token_color

        color = _get_token_color(Token)
        assert isinstance(color, str)


class TestHighlightCodeLine:
    def test_basic(self):
        from code_puppy.tools.common import (
            _get_lexer_for_extension,
            _highlight_code_line,
        )

        lexer = _get_lexer_for_extension(".py")
        result = _highlight_code_line("x = 1", None, lexer)
        assert isinstance(result, Text)

    def test_with_bg(self):
        from code_puppy.tools.common import (
            _get_lexer_for_extension,
            _highlight_code_line,
        )

        lexer = _get_lexer_for_extension(".py")
        result = _highlight_code_line("x = 1", "#002200", lexer)
        assert isinstance(result, Text)


class TestExtractFileExtension:
    def test_python(self):
        from code_puppy.tools.common import _extract_file_extension_from_diff

        ext = _extract_file_extension_from_diff("--- a/foo.py\n+++ b/foo.py")
        assert ext == ".py"

    def test_no_extension(self):
        from code_puppy.tools.common import _extract_file_extension_from_diff

        ext = _extract_file_extension_from_diff("")
        assert ext == ".txt"  # fallback


class TestBrightenHex:
    def test_brighten(self):
        from code_puppy.tools.common import brighten_hex

        result = brighten_hex("#004400", 1.5)
        assert result.startswith("#")

    def test_invalid(self):
        from code_puppy.tools.common import brighten_hex

        with pytest.raises(ValueError):
            brighten_hex("invalid", 1.5)


class TestFormatDiffWithSyntaxHighlighting:
    def test_basic_diff(self):
        from code_puppy.tools.common import _format_diff_with_syntax_highlighting

        diff = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 def hello():
-    print("old")
+    print("new")
     return True
"""
        result = _format_diff_with_syntax_highlighting(
            diff, addition_color="#003300", deletion_color="#330000"
        )
        assert isinstance(result, Text)

    def test_empty_diff(self):
        from code_puppy.tools.common import _format_diff_with_syntax_highlighting

        result = _format_diff_with_syntax_highlighting(
            "", addition_color="#003300", deletion_color="#330000"
        )
        assert isinstance(result, Text)

    def test_custom_colors(self):
        from code_puppy.tools.common import _format_diff_with_syntax_highlighting

        diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n context"
        result = _format_diff_with_syntax_highlighting(
            diff, addition_color="#00ff00", deletion_color="#ff0000"
        )
        assert isinstance(result, Text)

    def test_empty_lines(self):
        from code_puppy.tools.common import _format_diff_with_syntax_highlighting

        diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n\n-old\n+new"
        result = _format_diff_with_syntax_highlighting(
            diff, addition_color="#003300", deletion_color="#330000"
        )
        assert isinstance(result, Text)


class TestFormatDiffWithColors:
    def test_basic(self):
        from code_puppy.tools.common import format_diff_with_colors

        diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new"
        result = format_diff_with_colors(diff)
        assert isinstance(result, (Text, str))


class TestGetUserApproval:
    @patch("code_puppy.tools.common.arrow_select", return_value="\u2713 Approve")
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    def test_approved(
        self, mock_sleep, mock_await, mock_emit, MockConsole, mock_select
    ):
        from code_puppy.tools.common import get_user_approval

        approved, feedback = get_user_approval("Test", "content", puppy_name="Rex")
        assert approved is True
        assert feedback is None

    @patch("code_puppy.tools.common.arrow_select", return_value="\u2717 Reject")
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    def test_rejected(
        self, mock_sleep, mock_await, mock_emit, MockConsole, mock_select
    ):
        from code_puppy.tools.common import get_user_approval

        approved, feedback = get_user_approval("Test", "content", puppy_name="Rex")
        assert approved is False

    @patch(
        "code_puppy.tools.common.arrow_select",
        return_value="\U0001f4ac Reject with feedback (tell Rex what to change)",
    )
    @patch("code_puppy.tools.common.Prompt")
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    def test_rejected_with_feedback(
        self, mock_sleep, mock_await, mock_emit, MockConsole, MockPrompt, mock_select
    ):
        from code_puppy.tools.common import get_user_approval

        MockPrompt.ask.return_value = "fix it"
        approved, feedback = get_user_approval("Test", "content", puppy_name="Rex")
        assert approved is False
        assert feedback == "fix it"

    @patch("code_puppy.tools.common.arrow_select", side_effect=KeyboardInterrupt)
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.common.emit_error")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    def test_keyboard_interrupt(
        self, mock_sleep, mock_await, mock_err, mock_emit, MockConsole, mock_select
    ):
        from code_puppy.tools.common import get_user_approval

        approved, feedback = get_user_approval("Test", "content", puppy_name="Rex")
        assert approved is False

    @patch("code_puppy.tools.common.arrow_select", return_value="\u2713 Approve")
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    def test_with_preview(
        self, mock_sleep, mock_await, mock_emit, MockConsole, mock_select
    ):
        from code_puppy.tools.common import get_user_approval

        approved, _ = get_user_approval(
            "Test",
            "content",
            preview="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new",
            puppy_name="Rex",
        )
        assert approved is True

    @patch("code_puppy.tools.common.arrow_select", return_value="\u2713 Approve")
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    def test_with_text_content(
        self, mock_sleep, mock_await, mock_emit, MockConsole, mock_select
    ):
        from code_puppy.tools.common import get_user_approval

        approved, _ = get_user_approval("Test", Text("hello"), puppy_name="Rex")
        assert approved is True

    @patch("code_puppy.tools.common.arrow_select", return_value="\u2713 Approve")
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    @patch("code_puppy.config.get_puppy_name", return_value="buddy")
    def test_default_puppy_name(
        self, mock_name, mock_sleep, mock_await, mock_emit, MockConsole, mock_select
    ):
        from code_puppy.tools.common import get_user_approval

        approved, _ = get_user_approval("Test", "content")
        assert approved is True


class TestGetUserApprovalAsync:
    @pytest.mark.asyncio
    @patch("code_puppy.tools.common.arrow_select_async", return_value="\u2713 Approve")
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    async def test_approved(
        self, mock_sleep, mock_await, mock_emit, MockConsole, mock_select
    ):
        from code_puppy.tools.common import get_user_approval_async

        approved, feedback = await get_user_approval_async(
            "Test", "content", puppy_name="Rex"
        )
        assert approved is True

    @pytest.mark.asyncio
    @patch("code_puppy.tools.common.arrow_select_async", return_value="\u2717 Reject")
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    async def test_rejected(
        self, mock_sleep, mock_await, mock_emit, MockConsole, mock_select
    ):
        from code_puppy.tools.common import get_user_approval_async

        approved, _ = await get_user_approval_async("Test", "content", puppy_name="Rex")
        assert approved is False

    @pytest.mark.asyncio
    @patch("code_puppy.tools.common.arrow_select_async", return_value="feedback")
    @patch("code_puppy.tools.common.Prompt")
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    async def test_rejected_feedback(
        self, mock_sleep, mock_await, mock_emit, MockConsole, MockPrompt, mock_select
    ):
        from code_puppy.tools.common import get_user_approval_async

        MockPrompt.ask.return_value = "fix"
        approved, feedback = await get_user_approval_async(
            "Test", "content", puppy_name="Rex"
        )
        assert approved is False
        assert feedback == "fix"

    @pytest.mark.asyncio
    @patch("code_puppy.tools.common.arrow_select_async", side_effect=KeyboardInterrupt)
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.common.emit_error")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    async def test_interrupt(
        self, mock_sleep, mock_await, mock_err, mock_emit, MockConsole, mock_select
    ):
        from code_puppy.tools.common import get_user_approval_async

        approved, _ = await get_user_approval_async("Test", "content", puppy_name="Rex")
        assert approved is False

    @pytest.mark.asyncio
    @patch("code_puppy.tools.common.arrow_select_async", return_value="\u2713 Approve")
    @patch("code_puppy.tools.common.Console")
    @patch("code_puppy.tools.common.emit_info")
    @patch("code_puppy.tools.command_runner.set_awaiting_user_input")
    @patch("time.sleep")
    async def test_with_preview(
        self, mock_sleep, mock_await, mock_emit, MockConsole, mock_select
    ):
        from code_puppy.tools.common import get_user_approval_async

        approved, _ = await get_user_approval_async(
            "Test",
            "content",
            preview="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new",
            puppy_name="Rex",
        )
        assert approved is True


class TestFindBestWindow:
    def test_exact_match(self):
        from code_puppy.tools.common import _find_best_window

        lines = ["line1", "line2", "line3", "line4", "line5"]
        span, score = _find_best_window(lines, "line2\nline3")
        assert span is not None
        assert span == (1, 3)
        assert score > 0.5

    def test_no_match(self):
        from code_puppy.tools.common import _find_best_window

        lines = ["aaa", "bbb", "ccc"]
        span, score = _find_best_window(lines, "xyz\nqrs\ntuv\nwww")
        # score should be low
        assert isinstance(score, float)

    def test_single_line(self):
        from code_puppy.tools.common import _find_best_window

        lines = ["hello world", "foo bar"]
        span, score = _find_best_window(lines, "hello world")
        assert span == (0, 1)


class TestGenerateGroupId:
    def test_basic(self):
        from code_puppy.tools.common import generate_group_id

        gid = generate_group_id("test_tool")
        assert "test_tool" in gid

    def test_with_context(self):
        from code_puppy.tools.common import generate_group_id

        gid = generate_group_id("test_tool", "extra")
        assert "test_tool" in gid
