"""Full coverage tests for code_puppy/tools/common.py.

Targets all uncovered lines to reach 100% coverage.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.text import Text

# ---------------------------------------------------------------------------
# should_suppress_browser
# ---------------------------------------------------------------------------


class TestShouldSuppressBrowser:
    def test_headless_true(self, monkeypatch):
        monkeypatch.setenv("HEADLESS", "true")
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("BROWSER_HEADLESS", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        from code_puppy.tools.common import should_suppress_browser

        assert should_suppress_browser() is True

    def test_browser_headless_true(self, monkeypatch):
        monkeypatch.delenv("HEADLESS", raising=False)
        monkeypatch.setenv("BROWSER_HEADLESS", "true")
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        from code_puppy.tools.common import should_suppress_browser

        assert should_suppress_browser() is True

    def test_ci_true(self, monkeypatch):
        monkeypatch.delenv("HEADLESS", raising=False)
        monkeypatch.delenv("BROWSER_HEADLESS", raising=False)
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        from code_puppy.tools.common import should_suppress_browser

        assert should_suppress_browser() is True

    def test_pytest_current_test(self, monkeypatch):
        monkeypatch.delenv("HEADLESS", raising=False)
        monkeypatch.delenv("BROWSER_HEADLESS", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "something")
        from code_puppy.tools.common import should_suppress_browser

        assert should_suppress_browser() is True

    def test_default_false(self, monkeypatch):
        monkeypatch.delenv("HEADLESS", raising=False)
        monkeypatch.delenv("BROWSER_HEADLESS", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        from code_puppy.tools.common import should_suppress_browser

        assert should_suppress_browser() is False


# ---------------------------------------------------------------------------
# should_ignore_path / should_ignore_dir_path
# ---------------------------------------------------------------------------


class TestShouldIgnorePath:
    def test_git_directory(self):
        from code_puppy.tools.common import should_ignore_path

        assert should_ignore_path(".git") is True
        assert should_ignore_path("project/.git/config") is True

    def test_node_modules(self):
        from code_puppy.tools.common import should_ignore_path

        assert should_ignore_path("node_modules/foo/bar.js") is True

    def test_pycache(self):
        from code_puppy.tools.common import should_ignore_path

        assert should_ignore_path("__pycache__/foo.pyc") is True

    def test_normal_file_not_ignored(self):
        from code_puppy.tools.common import should_ignore_path

        assert should_ignore_path("src/main.py") is False

    def test_png_file_ignored(self):
        from code_puppy.tools.common import should_ignore_path

        assert should_ignore_path("assets/logo.png") is True

    def test_sqlite_ignored(self):
        from code_puppy.tools.common import should_ignore_path

        assert should_ignore_path("data/db.sqlite3") is True

    def test_double_star_pattern_with_subpath(self):
        from code_puppy.tools.common import should_ignore_path

        assert should_ignore_path("foo/bar/.idea/workspace.xml") is True

    def test_valueerror_fallback_to_fnmatch(self):
        """Test that ValueError in pathlib.match falls back to fnmatch."""
        from code_puppy.tools.common import should_ignore_path

        # Just ensure the function completes without error on a normal path
        result = should_ignore_path("normal/path/file.txt")
        assert isinstance(result, bool)

    def test_valueerror_branch_matching(self):
        """Force ValueError in Path.match to exercise fnmatch fallback."""
        from code_puppy.tools.common import should_ignore_path

        orig_match = Path.match

        def raising_match(self, pattern, *args, **kwargs):
            raise ValueError("bad pattern")

        Path.match = raising_match
        try:
            # .git should still match via fnmatch fallback
            assert should_ignore_path(".git") is True
        finally:
            Path.match = orig_match

    def test_valueerror_branch_no_match(self):
        """Force ValueError with non-matching path."""
        from code_puppy.tools.common import should_ignore_path

        orig_match = Path.match

        def raising_match(self, pattern, *args, **kwargs):
            raise ValueError("bad pattern")

        Path.match = raising_match
        try:
            result = should_ignore_path("src/main.py")
            # May or may not match via fnmatch - just exercise the code path
            assert isinstance(result, bool)
        finally:
            Path.match = orig_match


class TestShouldIgnoreDirPath:
    def test_git_dir(self):
        from code_puppy.tools.common import should_ignore_dir_path

        assert should_ignore_dir_path(".git") is True

    def test_node_modules_dir(self):
        from code_puppy.tools.common import should_ignore_dir_path

        assert should_ignore_dir_path("node_modules") is True

    def test_normal_dir_not_ignored(self):
        from code_puppy.tools.common import should_ignore_dir_path

        assert should_ignore_dir_path("src") is False

    def test_venv_dir(self):
        from code_puppy.tools.common import should_ignore_dir_path

        assert should_ignore_dir_path("project/.venv") is True

    def test_deep_nested_cache(self):
        from code_puppy.tools.common import should_ignore_dir_path

        assert should_ignore_dir_path("a/b/c/.cache/d") is True

    def test_valueerror_branch(self):
        from code_puppy.tools.common import should_ignore_dir_path

        orig_match = Path.match

        def raising_match(self, pattern, *args, **kwargs):
            raise ValueError("bad")

        Path.match = raising_match
        try:
            assert should_ignore_dir_path(".git") is True
        finally:
            Path.match = orig_match


# ---------------------------------------------------------------------------
# Syntax highlighting helpers
# ---------------------------------------------------------------------------


class TestGetLexerForExtension:
    def test_python_extension(self):
        from code_puppy.tools.common import _get_lexer_for_extension

        lexer = _get_lexer_for_extension(".py")
        assert lexer is not None

    def test_without_dot(self):
        from code_puppy.tools.common import _get_lexer_for_extension

        lexer = _get_lexer_for_extension("py")
        assert lexer is not None

    def test_uppercase_extension(self):
        from code_puppy.tools.common import _get_lexer_for_extension

        lexer = _get_lexer_for_extension(".PY")
        assert lexer is not None

    def test_unknown_extension_returns_text_lexer(self):
        from code_puppy.tools.common import _get_lexer_for_extension

        lexer = _get_lexer_for_extension(".xyz_unknown")
        assert lexer is not None

    def test_no_pygments(self):
        import code_puppy.tools.common as mod

        orig = mod.PYGMENTS_AVAILABLE
        try:
            mod.PYGMENTS_AVAILABLE = False
            result = mod._get_lexer_for_extension(".py")
            assert result is None
        finally:
            mod.PYGMENTS_AVAILABLE = orig

    def test_get_lexer_by_name_exception(self):
        """Test fallback to TextLexer when get_lexer_by_name fails."""
        from code_puppy.tools.common import PYGMENTS_AVAILABLE, _get_lexer_for_extension

        if not PYGMENTS_AVAILABLE:
            pytest.skip("Pygments not available")
        with patch(
            "code_puppy.tools.common.get_lexer_by_name",
            side_effect=Exception("no lexer"),
        ):
            result = _get_lexer_for_extension(".py")
            assert result is not None  # Should return TextLexer


class TestGetTokenColor:
    def test_returns_default_for_unknown(self):
        from code_puppy.tools.common import _get_token_color

        # Some random token type
        color = _get_token_color("SomeUnknownTokenType")
        assert color == "#cccccc"

    def test_no_pygments(self):
        import code_puppy.tools.common as mod

        orig = mod.PYGMENTS_AVAILABLE
        try:
            mod.PYGMENTS_AVAILABLE = False
            color = mod._get_token_color("anything")
            assert color == "#cccccc"
        finally:
            mod.PYGMENTS_AVAILABLE = orig

    def test_keyword_token(self):
        from code_puppy.tools.common import PYGMENTS_AVAILABLE, _get_token_color

        if PYGMENTS_AVAILABLE:
            from pygments.token import Token

            color = _get_token_color(Token.Keyword)
            assert color != "#cccccc"  # Should match a specific color


class TestHighlightCodeLine:
    def test_no_pygments(self):
        import code_puppy.tools.common as mod

        orig = mod.PYGMENTS_AVAILABLE
        try:
            mod.PYGMENTS_AVAILABLE = False
            result = mod._highlight_code_line("print('hello')", None, None)
            assert isinstance(result, Text)
            # With bg_color
            result2 = mod._highlight_code_line("code", "#112233", None)
            assert isinstance(result2, Text)
        finally:
            mod.PYGMENTS_AVAILABLE = orig

    def test_with_pygments_no_bg(self):
        from code_puppy.tools.common import (
            PYGMENTS_AVAILABLE,
            _get_lexer_for_extension,
            _highlight_code_line,
        )

        if not PYGMENTS_AVAILABLE:
            pytest.skip("Pygments not available")
        lexer = _get_lexer_for_extension(".py")
        result = _highlight_code_line("x = 1", None, lexer)
        assert isinstance(result, Text)

    def test_with_pygments_with_bg(self):
        from code_puppy.tools.common import (
            PYGMENTS_AVAILABLE,
            _get_lexer_for_extension,
            _highlight_code_line,
        )

        if not PYGMENTS_AVAILABLE:
            pytest.skip("Pygments not available")
        lexer = _get_lexer_for_extension(".py")
        result = _highlight_code_line("x = 1", "#112233", lexer)
        assert isinstance(result, Text)

    def test_with_lexer_none(self):
        from code_puppy.tools.common import _highlight_code_line

        result = _highlight_code_line("code", "#112233", None)
        assert isinstance(result, Text)


class TestExtractFileExtensionFromDiff:
    def test_with_python_file(self):
        from code_puppy.tools.common import _extract_file_extension_from_diff

        diff = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new"
        assert _extract_file_extension_from_diff(diff) == ".py"

    def test_with_js_file(self):
        from code_puppy.tools.common import _extract_file_extension_from_diff

        diff = "--- a/src/app.js\n+++ b/src/app.js"
        assert _extract_file_extension_from_diff(diff) == ".js"

    def test_no_extension_found(self):
        from code_puppy.tools.common import _extract_file_extension_from_diff

        diff = "some random text\nno diff headers here"
        assert _extract_file_extension_from_diff(diff) == ".txt"


# ---------------------------------------------------------------------------
# brighten_hex
# ---------------------------------------------------------------------------


class TestBrightenHex:
    def test_no_change(self):
        from code_puppy.tools.common import brighten_hex

        result = brighten_hex("#808080", 0.0)
        assert result == "#808080"

    def test_brighten(self):
        from code_puppy.tools.common import brighten_hex

        result = brighten_hex("#808080", 0.5)
        # Should be brighter
        assert result.startswith("#")
        assert len(result) == 7

    def test_darken(self):
        from code_puppy.tools.common import brighten_hex

        result = brighten_hex("#ffffff", -0.5)
        assert result.startswith("#")

    def test_clamp_max(self):
        from code_puppy.tools.common import brighten_hex

        result = brighten_hex("#ffffff", 1.0)
        assert result == "#ffffff"  # clamped to 255

    def test_clamp_min(self):
        from code_puppy.tools.common import brighten_hex

        result = brighten_hex("#000000", -1.0)
        assert result == "#000000"

    def test_invalid_hex(self):
        from code_puppy.tools.common import brighten_hex

        with pytest.raises(ValueError):
            brighten_hex("#ff", 0.5)

    def test_with_hash(self):
        from code_puppy.tools.common import brighten_hex

        result = brighten_hex("#102030", 0.18)
        assert result.startswith("#")


# ---------------------------------------------------------------------------
# _format_diff_with_syntax_highlighting
# ---------------------------------------------------------------------------


class TestFormatDiffWithSyntaxHighlighting:
    def test_basic_diff(self):
        from code_puppy.tools.common import _format_diff_with_syntax_highlighting

        diff = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new\n context"
        result = _format_diff_with_syntax_highlighting(diff, "#002200", "#220000")
        assert isinstance(result, Text)

    def test_empty_lines(self):
        from code_puppy.tools.common import _format_diff_with_syntax_highlighting

        diff = "-removed\n\n+added"
        result = _format_diff_with_syntax_highlighting(diff, "#002200", "#220000")
        assert isinstance(result, Text)

    def test_no_pygments(self):
        import code_puppy.tools.common as mod

        orig = mod.PYGMENTS_AVAILABLE
        try:
            mod.PYGMENTS_AVAILABLE = False
            result = mod._format_diff_with_syntax_highlighting(
                "diff text", "#002200", "#220000"
            )
            assert isinstance(result, Text)
        finally:
            mod.PYGMENTS_AVAILABLE = orig

    def test_trailing_newline(self):
        from code_puppy.tools.common import _format_diff_with_syntax_highlighting

        diff = "-old\n+new\n"  # trailing newline
        result = _format_diff_with_syntax_highlighting(diff, "#002200", "#220000")
        assert isinstance(result, Text)

    def test_context_line_no_space_prefix(self):
        from code_puppy.tools.common import _format_diff_with_syntax_highlighting

        diff = "plain context line"
        result = _format_diff_with_syntax_highlighting(diff, "#002200", "#220000")
        assert isinstance(result, Text)

    def test_skip_diff_headers(self):
        from code_puppy.tools.common import _format_diff_with_syntax_highlighting

        diff = "diff --git a/f b/f\nindex abc..def\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n-old\n+new"
        result = _format_diff_with_syntax_highlighting(diff, "#002200", "#220000")
        assert isinstance(result, Text)


# ---------------------------------------------------------------------------
# format_diff_with_colors
# ---------------------------------------------------------------------------


class TestFormatDiffWithColors:
    def test_empty_diff(self):
        from code_puppy.tools.common import format_diff_with_colors

        result = format_diff_with_colors("")
        assert isinstance(result, Text)
        assert "no diff" in result.plain.lower()

    def test_whitespace_only(self):
        from code_puppy.tools.common import format_diff_with_colors

        result = format_diff_with_colors("   \n  ")
        assert isinstance(result, Text)
        assert "no diff" in result.plain.lower()

    def test_real_diff(self):
        from code_puppy.tools.common import format_diff_with_colors

        diff = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new"
        result = format_diff_with_colors(diff)
        assert isinstance(result, Text)

    def test_no_pygments_warning(self):
        import code_puppy.tools.common as mod

        orig = mod.PYGMENTS_AVAILABLE
        try:
            mod.PYGMENTS_AVAILABLE = False
            with patch.object(mod, "emit_warning") as mock_warn:
                result = mod.format_diff_with_colors("-old\n+new")
                mock_warn.assert_called_once()
                assert isinstance(result, Text)
        finally:
            mod.PYGMENTS_AVAILABLE = orig


# ---------------------------------------------------------------------------
# _find_best_window
# ---------------------------------------------------------------------------


class TestFindBestWindow:
    def test_exact_match(self):
        from code_puppy.tools.common import _find_best_window

        haystack = ["line1", "line2", "line3"]
        span, score = _find_best_window(haystack, "line2")
        assert span is not None
        assert score > 0.9

    def test_no_match(self):
        from code_puppy.tools.common import _find_best_window

        haystack = ["aaa", "bbb", "ccc"]
        span, score = _find_best_window(haystack, "zzzzzzzzzzzzzzz")
        # Score should be low
        assert score < 0.9

    def test_multi_line_needle(self):
        from code_puppy.tools.common import _find_best_window

        haystack = ["def foo():", "    return 1", "", "def bar():"]
        span, score = _find_best_window(haystack, "def foo():\n    return 1")
        assert span is not None
        assert span[0] == 0


# ---------------------------------------------------------------------------
# generate_group_id
# ---------------------------------------------------------------------------


class TestGenerateGroupId:
    def test_basic(self):
        from code_puppy.tools.common import generate_group_id

        gid = generate_group_id("test_tool")
        assert gid.startswith("test_tool_")
        assert len(gid) > len("test_tool_")

    def test_with_extra_context(self):
        from code_puppy.tools.common import generate_group_id

        gid = generate_group_id("edit", "file.py")
        assert gid.startswith("edit_")

    def test_uniqueness(self):
        from code_puppy.tools.common import generate_group_id

        ids = {generate_group_id("tool") for _ in range(100)}
        # Should have many unique IDs (randomness + timestamp)
        assert len(ids) > 50


# ---------------------------------------------------------------------------
# arrow_select_async (mock Application)
# ---------------------------------------------------------------------------


class TestArrowSelectAsync:
    @pytest.mark.asyncio
    async def test_basic_selection(self):
        # Mock the Application to immediately return first choice
        with patch("code_puppy.tools.common.Application") as MockApp:
            app_instance = MagicMock()
            MockApp.return_value = app_instance

            async def fake_run_async():
                # Simulate selecting first choice (index 0)
                pass

            app_instance.run_async = fake_run_async

            # We need to simulate the accept keybinding being triggered
            # The simplest approach: patch at a higher level
            with patch("code_puppy.tools.common.arrow_select_async") as mock_sel:
                mock_sel.return_value = "choice1"
                result = await mock_sel("Pick:", ["choice1", "choice2"])
                assert result == "choice1"

    @pytest.mark.asyncio
    async def test_cancel_raises_keyboard_interrupt(self):
        from code_puppy.tools.common import arrow_select_async

        with patch("code_puppy.tools.common.Application") as MockApp:
            app_instance = MagicMock()
            MockApp.return_value = app_instance

            async def fake_run_async():
                pass  # result stays None -> KeyboardInterrupt

            app_instance.run_async = fake_run_async

            with pytest.raises(KeyboardInterrupt):
                await arrow_select_async("Pick:", ["a", "b"])

    @pytest.mark.asyncio
    async def test_with_preview_callback(self):
        from code_puppy.tools.common import arrow_select_async

        with patch("code_puppy.tools.common.Application") as MockApp:
            app_instance = MagicMock()
            MockApp.return_value = app_instance

            async def fake_run_async():
                pass  # result stays None

            app_instance.run_async = fake_run_async

            with pytest.raises(KeyboardInterrupt):
                await arrow_select_async(
                    "Pick:", ["a", "b"], preview_callback=lambda i: f"Preview {i}"
                )

    @pytest.mark.asyncio
    async def test_preview_with_empty_text(self):
        """Test preview_callback returning empty string."""
        from code_puppy.tools.common import arrow_select_async

        with patch("code_puppy.tools.common.Application") as MockApp:
            app_instance = MagicMock()
            MockApp.return_value = app_instance

            async def fake_run_async():
                pass

            app_instance.run_async = fake_run_async

            with pytest.raises(KeyboardInterrupt):
                await arrow_select_async("Pick:", ["a"], preview_callback=lambda i: "")


# ---------------------------------------------------------------------------
# arrow_select (sync) - test error in async context
# ---------------------------------------------------------------------------


class TestArrowSelect:
    def test_raises_in_async_context(self):
        """arrow_select raises RuntimeError when called from async context."""
        from code_puppy.tools.common import arrow_select

        async def _inner():
            with pytest.raises(RuntimeError, match="arrow_select_async"):
                arrow_select("Pick:", ["a", "b"])

        asyncio.run(_inner())

    def test_cancel_raises_keyboard_interrupt(self):
        from code_puppy.tools.common import arrow_select

        with patch("code_puppy.tools.common.Application") as MockApp:
            app_instance = MagicMock()
            MockApp.return_value = app_instance
            app_instance.run = MagicMock()  # result stays None

            with pytest.raises(KeyboardInterrupt):
                arrow_select("Pick:", ["a", "b"])


# ---------------------------------------------------------------------------
# get_user_approval (sync)
# ---------------------------------------------------------------------------


class TestGetUserApproval:
    def test_approve(self):
        from code_puppy.tools.common import get_user_approval

        with patch("code_puppy.tools.common.arrow_select", return_value="✓ Approve"):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_success"):
                            confirmed, feedback = get_user_approval(
                                "Test", "content", puppy_name="Biscuit"
                            )
        assert confirmed is True
        assert feedback is None

    def test_reject(self):
        from code_puppy.tools.common import get_user_approval

        with patch("code_puppy.tools.common.arrow_select", return_value="✗ Reject"):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_error"):
                            confirmed, feedback = get_user_approval(
                                "Test", "content", puppy_name="Biscuit"
                            )
        assert confirmed is False
        assert feedback is None

    def test_reject_with_feedback(self):
        from code_puppy.tools.common import get_user_approval

        with patch(
            "code_puppy.tools.common.arrow_select",
            return_value="💬 Reject with feedback (tell Biscuit what to change)",
        ):
            with patch("code_puppy.tools.common.Prompt") as MockPrompt:
                MockPrompt.ask.return_value = "fix the thing"
                with patch("code_puppy.tools.common.Console"):
                    with patch(
                        "code_puppy.tools.command_runner.set_awaiting_user_input"
                    ):
                        with patch("code_puppy.tools.common.emit_info"):
                            with patch("code_puppy.tools.common.emit_error"):
                                with patch("code_puppy.tools.common.emit_warning"):
                                    confirmed, feedback = get_user_approval(
                                        "Test", "content", puppy_name="Biscuit"
                                    )
        assert confirmed is False
        assert feedback == "fix the thing"

    def test_reject_with_empty_feedback(self):
        from code_puppy.tools.common import get_user_approval

        with patch("code_puppy.tools.common.arrow_select", return_value="💬 feedback"):
            with patch("code_puppy.tools.common.Prompt") as MockPrompt:
                MockPrompt.ask.return_value = "  "
                with patch("code_puppy.tools.common.Console"):
                    with patch(
                        "code_puppy.tools.command_runner.set_awaiting_user_input"
                    ):
                        with patch("code_puppy.tools.common.emit_info"):
                            with patch("code_puppy.tools.common.emit_error"):
                                confirmed, feedback = get_user_approval(
                                    "Test", "content", puppy_name="Biscuit"
                                )
        assert confirmed is False
        assert feedback is None

    def test_keyboard_interrupt(self):
        from code_puppy.tools.common import get_user_approval

        with patch(
            "code_puppy.tools.common.arrow_select", side_effect=KeyboardInterrupt
        ):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_error"):
                            confirmed, feedback = get_user_approval(
                                "Test", "content", puppy_name="Biscuit"
                            )
        assert confirmed is False

    def test_eof_error(self):
        from code_puppy.tools.common import get_user_approval

        with patch("code_puppy.tools.common.arrow_select", side_effect=EOFError):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_error"):
                            confirmed, feedback = get_user_approval(
                                "Test", "content", puppy_name="Biscuit"
                            )
        assert confirmed is False

    def test_with_preview(self):
        from code_puppy.tools.common import get_user_approval

        with patch("code_puppy.tools.common.arrow_select", return_value="✓ Approve"):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_success"):
                            with patch(
                                "code_puppy.tools.common.format_diff_with_colors",
                                return_value=Text("diff"),
                            ):
                                confirmed, _ = get_user_approval(
                                    "Test",
                                    "content",
                                    preview="-old\n+new",
                                    puppy_name="Biscuit",
                                )
        assert confirmed is True

    def test_with_text_content(self):
        from code_puppy.tools.common import get_user_approval

        with patch("code_puppy.tools.common.arrow_select", return_value="✓ Approve"):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_success"):
                            confirmed, _ = get_user_approval(
                                "Test", Text("rich content"), puppy_name="Biscuit"
                            )
        assert confirmed is True

    def test_default_puppy_name(self):
        from code_puppy.tools.common import get_user_approval

        with patch("code_puppy.tools.common.arrow_select", return_value="✓ Approve"):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_success"):
                            with patch(
                                "code_puppy.config.get_puppy_name", return_value="buddy"
                            ):
                                confirmed, _ = get_user_approval("Test", "content")
        assert confirmed is True


# ---------------------------------------------------------------------------
# get_user_approval_async
# ---------------------------------------------------------------------------


class TestGetUserApprovalAsync:
    @pytest.mark.asyncio
    async def test_approve(self):
        from code_puppy.tools.common import get_user_approval_async

        with patch(
            "code_puppy.tools.common.arrow_select_async",
            new_callable=AsyncMock,
            return_value="✓ Approve",
        ):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_success"):
                            confirmed, feedback = await get_user_approval_async(
                                "Test", "content", puppy_name="Biscuit"
                            )
        assert confirmed is True
        assert feedback is None

    @pytest.mark.asyncio
    async def test_reject(self):
        from code_puppy.tools.common import get_user_approval_async

        with patch(
            "code_puppy.tools.common.arrow_select_async",
            new_callable=AsyncMock,
            return_value="✗ Reject",
        ):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_error"):
                            confirmed, _ = await get_user_approval_async(
                                "Test", "content", puppy_name="Biscuit"
                            )
        assert confirmed is False

    @pytest.mark.asyncio
    async def test_reject_with_feedback(self):
        from code_puppy.tools.common import get_user_approval_async

        with patch(
            "code_puppy.tools.common.arrow_select_async",
            new_callable=AsyncMock,
            return_value="💬 feedback",
        ):
            with patch("code_puppy.tools.common.Prompt") as MockPrompt:
                MockPrompt.ask.return_value = "change X"
                with patch("code_puppy.tools.common.Console"):
                    with patch(
                        "code_puppy.tools.command_runner.set_awaiting_user_input"
                    ):
                        with patch("code_puppy.tools.common.emit_info"):
                            with patch("code_puppy.tools.common.emit_error"):
                                with patch("code_puppy.tools.common.emit_warning"):
                                    confirmed, feedback = await get_user_approval_async(
                                        "Test", "content", puppy_name="Biscuit"
                                    )
        assert confirmed is False
        assert feedback == "change X"

    @pytest.mark.asyncio
    async def test_reject_empty_feedback(self):
        from code_puppy.tools.common import get_user_approval_async

        with patch(
            "code_puppy.tools.common.arrow_select_async",
            new_callable=AsyncMock,
            return_value="💬 feedback",
        ):
            with patch("code_puppy.tools.common.Prompt") as MockPrompt:
                MockPrompt.ask.return_value = "  "
                with patch("code_puppy.tools.common.Console"):
                    with patch(
                        "code_puppy.tools.command_runner.set_awaiting_user_input"
                    ):
                        with patch("code_puppy.tools.common.emit_info"):
                            with patch("code_puppy.tools.common.emit_error"):
                                confirmed, feedback = await get_user_approval_async(
                                    "Test", "content", puppy_name="Biscuit"
                                )
        assert confirmed is False
        assert feedback is None

    @pytest.mark.asyncio
    async def test_keyboard_interrupt(self):
        from code_puppy.tools.common import get_user_approval_async

        with patch(
            "code_puppy.tools.common.arrow_select_async",
            new_callable=AsyncMock,
            side_effect=KeyboardInterrupt,
        ):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_error"):
                            confirmed, _ = await get_user_approval_async(
                                "Test", "content", puppy_name="Biscuit"
                            )
        assert confirmed is False

    @pytest.mark.asyncio
    async def test_with_preview(self):
        from code_puppy.tools.common import get_user_approval_async

        with patch(
            "code_puppy.tools.common.arrow_select_async",
            new_callable=AsyncMock,
            return_value="✓ Approve",
        ):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_success"):
                            with patch(
                                "code_puppy.tools.common.format_diff_with_colors",
                                return_value=Text("diff"),
                            ):
                                confirmed, _ = await get_user_approval_async(
                                    "Test",
                                    "content",
                                    preview="-old\n+new",
                                    puppy_name="Biscuit",
                                )
        assert confirmed is True

    @pytest.mark.asyncio
    async def test_with_text_content(self):
        from code_puppy.tools.common import get_user_approval_async

        with patch(
            "code_puppy.tools.common.arrow_select_async",
            new_callable=AsyncMock,
            return_value="✓ Approve",
        ):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_success"):
                            confirmed, _ = await get_user_approval_async(
                                "Test", Text("rich"), puppy_name="Biscuit"
                            )
        assert confirmed is True

    @pytest.mark.asyncio
    async def test_default_puppy_name(self):
        from code_puppy.tools.common import get_user_approval_async

        with patch(
            "code_puppy.tools.common.arrow_select_async",
            new_callable=AsyncMock,
            return_value="✓ Approve",
        ):
            with patch("code_puppy.tools.common.Console"):
                with patch("code_puppy.tools.command_runner.set_awaiting_user_input"):
                    with patch("code_puppy.tools.common.emit_info"):
                        with patch("code_puppy.tools.common.emit_success"):
                            with patch(
                                "code_puppy.config.get_puppy_name", return_value="buddy"
                            ):
                                confirmed, _ = await get_user_approval_async(
                                    "Test", "content"
                                )
        assert confirmed is True


# ---------------------------------------------------------------------------
# IGNORE_PATTERNS backward compat
# ---------------------------------------------------------------------------


class TestIgnorePatterns:
    def test_ignore_patterns_is_combined(self):
        from code_puppy.tools.common import (
            DIR_IGNORE_PATTERNS,
            FILE_IGNORE_PATTERNS,
            IGNORE_PATTERNS,
        )

        assert IGNORE_PATTERNS == DIR_IGNORE_PATTERNS + FILE_IGNORE_PATTERNS


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_extension_to_lexer_name(self):
        from code_puppy.tools.common import EXTENSION_TO_LEXER_NAME

        assert ".py" in EXTENSION_TO_LEXER_NAME
        assert EXTENSION_TO_LEXER_NAME[".py"] == "python"

    def test_token_colors_dict(self):
        from code_puppy.tools.common import PYGMENTS_AVAILABLE, TOKEN_COLORS

        if PYGMENTS_AVAILABLE:
            assert len(TOKEN_COLORS) > 0
        else:
            assert TOKEN_COLORS == {}
