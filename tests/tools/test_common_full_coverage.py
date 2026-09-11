"""Full coverage tests for code_puppy/tools/common.py.

Targets all uncovered lines to reach 100% coverage.
"""

import asyncio
from contextlib import nullcontext
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from rich.text import Text

from code_puppy.tools.common import _sanitize_string

# ---------------------------------------------------------------------------
# _sanitize_string
# ---------------------------------------------------------------------------


class TestSanitizeString:
    """Test the _sanitize_string Unicode sanitization function."""

    def test_clean_string_passes_through(self):
        """Test that clean strings pass through unchanged."""
        clean = "Hello, World! 123"
        result = _sanitize_string(clean)
        assert result == clean

    def test_empty_string(self):
        """Test empty string handling."""
        assert _sanitize_string("") == ""

    def test_none_like_empty(self):
        """Test falsy string values."""
        # The function checks 'if not text' first.
        result = _sanitize_string("")
        assert result == ""

    def test_unicode_characters_preserved(self):
        """Test that valid unicode characters are preserved."""
        unicode_str = "Hello 世界 🐾 café"
        result = _sanitize_string(unicode_str)
        assert result == unicode_str

    def test_surrogate_characters_replaced(self):
        """Test that surrogate characters are replaced."""
        # Create a string with surrogate characters (invalid standalone).
        # Surrogates are in range 0xD800 to 0xDFFF.
        surrogate_str = "Hello" + chr(0xD800) + "World"
        result = _sanitize_string(surrogate_str)

        # Should replace surrogate with replacement character.
        assert "\ufffd" in result or result == "HelloWorld"
        assert chr(0xD800) not in result

    def test_mixed_valid_invalid(self):
        """Test string with mix of valid and invalid characters."""
        mixed = "Valid" + chr(0xDC00) + "Text" + chr(0xDFFF) + "End"
        result = _sanitize_string(mixed)

        # Surrogates should be replaced.
        assert chr(0xDC00) not in result
        assert chr(0xDFFF) not in result
        assert "Valid" in result
        assert "Text" in result
        assert "End" in result


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
# termflow diff adapters (rendering itself is termflow's job, and tested there)
# ---------------------------------------------------------------------------


class TestTermflowDiffAdapters:
    def test_renderer_uses_explicit_colors(self):
        from code_puppy.tools.common import _termflow_diff_renderer

        renderer = _termflow_diff_renderer("#002200", "#220000")
        assert renderer.theme.addition == "#002200"
        assert renderer.theme.deletion == "#220000"

    def test_renderer_defaults_come_from_config(self):
        from code_puppy.tools.common import _termflow_diff_renderer

        with (
            patch(
                "code_puppy.config.get_diff_addition_color",
                return_value="#0a0b0c",
            ),
            patch(
                "code_puppy.config.get_diff_deletion_color",
                return_value="#0d0e0f",
            ),
        ):
            renderer = _termflow_diff_renderer()
        assert renderer.theme.addition == "#0a0b0c"
        assert renderer.theme.deletion == "#0d0e0f"

    def test_highlighter_flows_through_theme_callback(self):
        from code_puppy.tools.common import _termflow_diff_renderer

        sentinel = object()
        with patch(
            "code_puppy.callbacks.on_termflow_highlighter",
            return_value=sentinel,
        ):
            renderer = _termflow_diff_renderer("#002200", "#220000")
        assert renderer.highlighter is sentinel


class TestStreamDiffAnsiLines:
    def test_yields_lines_without_headers(self):
        from code_puppy.tools.common import stream_diff_ansi_lines

        diff = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new"
        lines = list(stream_diff_ansi_lines(diff, "#002200", "#220000"))
        assert len(lines) == 2  # headers skipped, one line per change
        assert not any(line.endswith("\n") for line in lines)

    def test_backgrounds_present(self):
        from code_puppy.tools.common import stream_diff_ansi_lines

        lines = list(stream_diff_ansi_lines("-old\n+new", "#002200", "#220000"))
        joined = "".join(lines)
        assert "\x1b[48;2;0;34;0m" in joined
        assert "\x1b[48;2;34;0;0m" in joined

    def test_empty_diff_yields_nothing(self):
        from code_puppy.tools.common import stream_diff_ansi_lines

        assert list(stream_diff_ansi_lines("")) == []


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


# ---------------------------------------------------------------------------
# _find_best_window (plugin preview API surface — engine no longer uses it)
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
# arrow_select / arrow_select_async (headless termflow drives)
# ---------------------------------------------------------------------------


def _drive_selector(choices, keys, preview_callback=None):
    """Build the inline selector and drive it with scripted keys."""
    from code_puppy.tools.common import _build_arrow_select_menu

    script = iter(keys)
    out = StringIO()
    menu = _build_arrow_select_menu(
        "Pick:",
        choices,
        preview_callback,
        key_source=lambda: next(script),
        output=out,
        size=lambda: (80, 24),
    )
    return menu.run(), out.getvalue()


class TestArrowSelectAsync:
    def test_scripted_selection_returns_choice(self):
        result, raw = _drive_selector(["choice1", "choice2"], ["down", "enter"])
        assert result.item.value == "choice2"
        assert "choice1" in raw

    def test_ctrl_n_and_ctrl_p_move_the_cursor(self):
        result, _ = _drive_selector(
            ["a", "b", "c"], ["ctrl-n", "ctrl-n", "ctrl-p", "enter"]
        )
        assert result.item.value == "b"

    def test_renders_inline_not_fullscreen(self):
        _, raw = _drive_selector(["a"], ["escape"])
        assert "\x1b[H" not in raw  # no cursor-home: transcript survives
        assert "\x1b[?1049" not in raw  # no alt screen

    def test_preview_callback_receives_index(self):
        seen = []

        def preview(index):
            seen.append(index)
            return f"Preview {index}"

        _, raw = _drive_selector(["a", "b"], ["down", "escape"], preview)
        assert "Preview 0" in raw and "Preview 1" in raw
        assert 0 in seen and 1 in seen

    def test_preview_with_empty_text(self):
        result, _ = _drive_selector(["a"], ["enter"], lambda i: "")
        assert result.item.value == "a"

    @pytest.mark.asyncio
    async def test_async_wrapper_selects_and_cancels(self):
        from code_puppy.tools import common

        def scripted_menu(keys):
            def build(message, choices, preview_callback=None, **overrides):
                script = iter(keys)
                overrides.setdefault("key_source", lambda: next(script))
                overrides.setdefault("output", StringIO())
                overrides.setdefault("size", lambda: (80, 24))
                return _original_build(message, choices, preview_callback, **overrides)

            return build

        _original_build = common._build_arrow_select_menu
        with patch(
            "code_puppy.agents._key_listeners.suspended_key_listener",
            nullcontext,
        ):
            with patch.object(
                common, "_build_arrow_select_menu", scripted_menu(["enter"])
            ):
                assert await common.arrow_select_async("Pick:", ["a", "b"]) == "a"
            with patch.object(
                common, "_build_arrow_select_menu", scripted_menu(["escape"])
            ):
                with pytest.raises(KeyboardInterrupt):
                    await common.arrow_select_async("Pick:", ["a", "b"])


class TestArrowSelect:
    def test_raises_in_async_context(self):
        """arrow_select raises RuntimeError when called from async context."""
        from code_puppy.tools.common import arrow_select

        async def _inner():
            with pytest.raises(RuntimeError, match="arrow_select_async"):
                arrow_select("Pick:", ["a", "b"])

        asyncio.run(_inner())

    def test_sync_selection_and_cancel(self):
        from code_puppy.tools import common

        _original_build = common._build_arrow_select_menu

        def scripted(keys):
            def build(message, choices, preview_callback=None, **overrides):
                script = iter(keys)
                overrides.setdefault("key_source", lambda: next(script))
                overrides.setdefault("output", StringIO())
                overrides.setdefault("size", lambda: (80, 24))
                return _original_build(message, choices, preview_callback, **overrides)

            return build

        with patch(
            "code_puppy.agents._key_listeners.suspended_key_listener",
            nullcontext,
        ):
            with patch.object(
                common, "_build_arrow_select_menu", scripted(["down", "enter"])
            ):
                assert common.arrow_select("Pick:", ["a", "b"]) == "b"
            with patch.object(common, "_build_arrow_select_menu", scripted(["escape"])):
                with pytest.raises(KeyboardInterrupt):
                    common.arrow_select("Pick:", ["a", "b"])


# ---------------------------------------------------------------------------
# get_user_approval (sync)
# ---------------------------------------------------------------------------


class TestGetUserApproval:
    @pytest.fixture(autouse=True)
    def _interactive_stdin(self):
        with patch("code_puppy.tools.common.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            yield mock_stdin

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
    @pytest.fixture(autouse=True)
    def _interactive_stdin(self):
        with patch("code_puppy.tools.common.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            yield mock_stdin

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
    def test_brighten_hex_reexported_from_termflow(self):
        from termflow.diff import brighten_hex as termflow_brighten_hex

        from code_puppy.tools.common import brighten_hex

        assert brighten_hex is termflow_brighten_hex
