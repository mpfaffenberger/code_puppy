"""Tests for code_puppy.messaging.terminal_theme."""

from __future__ import annotations

import pytest

from code_puppy.messaging.terminal_theme import (
    detect_terminal_bg,
    resolve_code_theme,
)


# ---------------------------------------------------------------------------
# detect_terminal_bg
# ---------------------------------------------------------------------------


class TestDetectTerminalBg:
    def test_default_is_dark_with_no_signal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("COLORFGBG", raising=False)
        monkeypatch.delenv("CODE_PUPPY_TERMINAL_BG", raising=False)
        assert detect_terminal_bg() == "dark"

    def test_default_arg_is_honored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COLORFGBG", raising=False)
        monkeypatch.delenv("CODE_PUPPY_TERMINAL_BG", raising=False)
        assert detect_terminal_bg(default="light") == "light"

    @pytest.mark.parametrize("value", ["light", "LIGHT", "  light  "])
    def test_env_override_light(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("CODE_PUPPY_TERMINAL_BG", value)
        # Even if COLORFGBG disagrees, the override wins.
        monkeypatch.setenv("COLORFGBG", "15;0")
        assert detect_terminal_bg() == "light"

    @pytest.mark.parametrize("value", ["dark", "DARK"])
    def test_env_override_dark(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("CODE_PUPPY_TERMINAL_BG", value)
        monkeypatch.setenv("COLORFGBG", "0;15")  # would normally mean light
        assert detect_terminal_bg() == "dark"

    def test_env_override_bogus_falls_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CODE_PUPPY_TERMINAL_BG", "neon-magenta")
        monkeypatch.setenv("COLORFGBG", "15;0")
        # Bogus override is ignored, COLORFGBG kicks in.
        assert detect_terminal_bg() == "dark"

    @pytest.mark.parametrize("bg_idx", ["0", "1", "2", "3", "4", "5", "6", "8"])
    def test_colorfgbg_dark_indices(
        self, monkeypatch: pytest.MonkeyPatch, bg_idx: str
    ) -> None:
        monkeypatch.delenv("CODE_PUPPY_TERMINAL_BG", raising=False)
        monkeypatch.setenv("COLORFGBG", f"15;{bg_idx}")
        assert detect_terminal_bg() == "dark"

    @pytest.mark.parametrize("bg_idx", ["7", "9", "10", "11", "12", "13", "14", "15"])
    def test_colorfgbg_light_indices(
        self, monkeypatch: pytest.MonkeyPatch, bg_idx: str
    ) -> None:
        monkeypatch.delenv("CODE_PUPPY_TERMINAL_BG", raising=False)
        monkeypatch.setenv("COLORFGBG", f"0;{bg_idx}")
        assert detect_terminal_bg() == "light"

    def test_colorfgbg_three_segments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Some terminals emit "fg;default;bg" — take the last segment.
        monkeypatch.delenv("CODE_PUPPY_TERMINAL_BG", raising=False)
        monkeypatch.setenv("COLORFGBG", "0;default;15")
        assert detect_terminal_bg() == "light"

    def test_colorfgbg_empty_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CODE_PUPPY_TERMINAL_BG", raising=False)
        monkeypatch.setenv("COLORFGBG", "")
        assert detect_terminal_bg(default="light") == "light"

    def test_colorfgbg_garbage_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CODE_PUPPY_TERMINAL_BG", raising=False)
        monkeypatch.setenv("COLORFGBG", "this-is-not-an-fgbg")
        # Last token "this-is-not-an-fgbg" isn't in dark set → classified as light.
        # We're documenting current behavior; weird inputs lean light, which
        # is the safer choice if a user explicitly set something weird.
        assert detect_terminal_bg() == "light"


# ---------------------------------------------------------------------------
# resolve_code_theme
# ---------------------------------------------------------------------------


class TestResolveCodeTheme:
    def test_none_resolves_via_detection_dark(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("COLORFGBG", raising=False)
        monkeypatch.delenv("CODE_PUPPY_TERMINAL_BG", raising=False)
        assert resolve_code_theme(None) == "ansi_dark"

    def test_system_resolves_via_detection_light(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CODE_PUPPY_TERMINAL_BG", "light")
        assert resolve_code_theme("system") == "ansi_light"

    def test_system_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CODE_PUPPY_TERMINAL_BG", "dark")
        assert resolve_code_theme("SYSTEM") == "ansi_dark"

    @pytest.mark.parametrize("name", ["monokai", "github-dark", "solarized-light"])
    def test_explicit_override_passthrough(self, name: str) -> None:
        # Explicit values bypass detection entirely.
        assert resolve_code_theme(name) == name

    def test_whitespace_is_stripped(self) -> None:
        assert resolve_code_theme("  monokai  ") == "monokai"

    def test_empty_string_falls_back_to_detection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CODE_PUPPY_TERMINAL_BG", "light")
        assert resolve_code_theme("") == "ansi_light"


# ---------------------------------------------------------------------------
# install_accessible_markdown_styles
# ---------------------------------------------------------------------------


class TestInstallAccessibleMarkdownStyles:
    """Patches Rich's hardcoded markdown.code / markdown.kbd defaults.

    These tests mutate `rich.themes.DEFAULT.styles`, which is process-global.
    Each test snapshots and restores the affected keys to keep things hermetic.
    """

    @pytest.fixture(autouse=True)
    def _restore_styles(self):
        from rich import themes

        snapshot = {
            "markdown.code": themes.DEFAULT.styles.get("markdown.code"),
            "markdown.kbd": themes.DEFAULT.styles.get("markdown.kbd"),
        }
        yield
        for key, value in snapshot.items():
            if value is None:
                themes.DEFAULT.styles.pop(key, None)
            else:
                themes.DEFAULT.styles[key] = value

    def test_patches_markdown_code_to_bold_reverse(self) -> None:
        from rich import themes
        from rich.style import Style

        from code_puppy.messaging.terminal_theme import (
            install_accessible_markdown_styles,
        )

        install_accessible_markdown_styles()
        patched = themes.DEFAULT.styles["markdown.code"]
        assert patched == Style(bold=True, reverse=True)

    def test_patches_markdown_kbd_to_bold_reverse(self) -> None:
        from rich import themes
        from rich.style import Style

        from code_puppy.messaging.terminal_theme import (
            install_accessible_markdown_styles,
        )

        install_accessible_markdown_styles()
        patched = themes.DEFAULT.styles["markdown.kbd"]
        assert patched == Style(bold=True, reverse=True)

    def test_patched_style_uses_no_color_slot(self) -> None:
        """No specific ANSI color = nothing for a theme to mismatch."""
        from rich import themes

        from code_puppy.messaging.terminal_theme import (
            install_accessible_markdown_styles,
        )

        install_accessible_markdown_styles()
        patched = themes.DEFAULT.styles["markdown.code"]
        assert patched.color is None
        assert patched.bgcolor is None

    def test_patched_style_is_bold_for_redundancy(self) -> None:
        """Bold provides a non-color signal (WCAG 1.4.1)."""
        from rich import themes

        from code_puppy.messaging.terminal_theme import (
            install_accessible_markdown_styles,
        )

        install_accessible_markdown_styles()
        assert themes.DEFAULT.styles["markdown.code"].bold is True

    def test_patched_style_uses_reverse(self) -> None:
        """Reverse guarantees fg/bg contrast in any user palette."""
        from rich import themes

        from code_puppy.messaging.terminal_theme import (
            install_accessible_markdown_styles,
        )

        install_accessible_markdown_styles()
        assert themes.DEFAULT.styles["markdown.code"].reverse is True

    def test_idempotent(self) -> None:
        """Calling twice yields the same final state."""
        from rich import themes

        from code_puppy.messaging.terminal_theme import (
            install_accessible_markdown_styles,
        )

        install_accessible_markdown_styles()
        first = themes.DEFAULT.styles["markdown.code"]
        install_accessible_markdown_styles()
        second = themes.DEFAULT.styles["markdown.code"]
        assert first == second

    def test_new_console_inherits_patched_style(self) -> None:
        """End-to-end: a fresh Console sees the patched style at render time."""
        from rich.console import Console
        from rich.style import Style

        from code_puppy.messaging.terminal_theme import (
            install_accessible_markdown_styles,
        )

        install_accessible_markdown_styles()
        console = Console()
        assert console.get_style("markdown.code") == Style(bold=True, reverse=True)
