"""Tests for the statusline plugin — config, prompt_patch, and command handler."""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_runner():
    """Reset runner module-level globals between tests."""
    from code_puppy.plugins.statusline import runner

    runner._cached_output = ""
    runner._last_run_monotonic = 0.0
    runner._running = False


# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------


class TestConfig:
    def setup_method(self):
        _reset_runner()

    def test_is_enabled_false_when_missing(self):
        from code_puppy.plugins.statusline.config import is_enabled

        with patch("code_puppy.plugins.statusline.config.get_value", return_value=None):
            assert is_enabled() is False

    @pytest.mark.parametrize(
        "val", ["1", "true", "True", "TRUE", "yes", "YES", "on", "ON"]
    )
    def test_is_enabled_truthy_values(self, val):
        from code_puppy.plugins.statusline.config import is_enabled

        with patch("code_puppy.plugins.statusline.config.get_value", return_value=val):
            assert is_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "nope", ""])
    def test_is_enabled_falsy_values(self, val):
        from code_puppy.plugins.statusline.config import is_enabled

        with patch("code_puppy.plugins.statusline.config.get_value", return_value=val):
            assert is_enabled() is False

    def test_set_enabled_true(self):
        from code_puppy.plugins.statusline.config import set_enabled

        with patch("code_puppy.plugins.statusline.config.set_value") as mock_set:
            set_enabled(True)
            mock_set.assert_called_once_with("statusline_enabled", "true")

    def test_set_enabled_false(self):
        from code_puppy.plugins.statusline.config import set_enabled

        with patch("code_puppy.plugins.statusline.config.set_value") as mock_set:
            set_enabled(False)
            mock_set.assert_called_once_with("statusline_enabled", "false")

    def test_get_command_strips_whitespace(self):
        from code_puppy.plugins.statusline.config import get_command

        with patch(
            "code_puppy.plugins.statusline.config.get_value",
            return_value="  ~/bin/status.sh  ",
        ):
            assert get_command() == "~/bin/status.sh"

    def test_get_command_returns_empty_when_none(self):
        from code_puppy.plugins.statusline.config import get_command

        with patch("code_puppy.plugins.statusline.config.get_value", return_value=None):
            assert get_command() == ""

    def test_set_command(self):
        from code_puppy.plugins.statusline.config import set_command

        with patch("code_puppy.plugins.statusline.config.set_value") as mock_set:
            set_command("~/bin/status.sh")
            mock_set.assert_called_once_with("statusline_command", "~/bin/status.sh")

    def test_get_timeout_ms_default(self):
        from code_puppy.plugins.statusline.config import (
            DEFAULT_TIMEOUT_MS,
            get_timeout_ms,
        )

        with patch("code_puppy.plugins.statusline.config.get_value", return_value=None):
            assert get_timeout_ms() == DEFAULT_TIMEOUT_MS

    def test_get_timeout_ms_enforces_minimum(self):
        from code_puppy.plugins.statusline.config import get_timeout_ms

        with patch("code_puppy.plugins.statusline.config.get_value", return_value="50"):
            assert get_timeout_ms() == 100  # clamped to min

    def test_get_timeout_ms_invalid_falls_back(self):
        from code_puppy.plugins.statusline.config import (
            DEFAULT_TIMEOUT_MS,
            get_timeout_ms,
        )

        with patch(
            "code_puppy.plugins.statusline.config.get_value", return_value="notanumber"
        ):
            assert get_timeout_ms() == DEFAULT_TIMEOUT_MS

    def test_get_refresh_ms_default(self):
        from code_puppy.plugins.statusline.config import (
            DEFAULT_REFRESH_MS,
            get_refresh_ms,
        )

        with patch("code_puppy.plugins.statusline.config.get_value", return_value=None):
            assert get_refresh_ms() == DEFAULT_REFRESH_MS

    def test_get_refresh_ms_enforces_minimum(self):
        from code_puppy.plugins.statusline.config import get_refresh_ms

        with patch("code_puppy.plugins.statusline.config.get_value", return_value="10"):
            assert get_refresh_ms() == 200  # clamped to min

    def test_get_mode_valid(self):
        from code_puppy.plugins.statusline.config import get_mode

        for mode in ("replace", "above", "newline"):
            with patch(
                "code_puppy.plugins.statusline.config.get_value", return_value=mode
            ):
                assert get_mode() == mode

    def test_get_mode_normalises_case(self):
        from code_puppy.plugins.statusline.config import get_mode

        with patch(
            "code_puppy.plugins.statusline.config.get_value", return_value="REPLACE"
        ):
            assert get_mode() == "replace"

    def test_get_mode_falls_back_to_default_for_garbage(self):
        from code_puppy.plugins.statusline.config import DEFAULT_MODE, get_mode

        with patch(
            "code_puppy.plugins.statusline.config.get_value", return_value="bogus"
        ):
            assert get_mode() == DEFAULT_MODE

    def test_set_mode_valid(self):
        from code_puppy.plugins.statusline.config import set_mode

        with patch("code_puppy.plugins.statusline.config.set_value") as mock_set:
            set_mode("above")
            mock_set.assert_called_once_with("statusline_mode", "above")

    def test_set_mode_invalid_does_nothing(self):
        from code_puppy.plugins.statusline.config import set_mode

        with patch("code_puppy.plugins.statusline.config.set_value") as mock_set:
            set_mode("supermode")
            mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# prompt_patch.py — _render()
# ---------------------------------------------------------------------------


class TestRender:
    """Unit-test _render() in isolation from prompt_toolkit internals."""

    def _make_formatted_text(self, text=">>> "):
        """Return a minimal FormattedText-like list for the default prompt."""
        from prompt_toolkit.formatted_text import FormattedText

        return FormattedText([("class:arrow", text)])

    def test_render_returns_default_when_no_status_text(self):
        from code_puppy.plugins.statusline.prompt_patch import _render

        default = self._make_formatted_text()
        with patch(
            "code_puppy.plugins.statusline.prompt_patch.get_status_text",
            return_value="",
        ):
            result = _render(default, ">>> ")
        assert result is default

    def test_render_replace_mode_appends_arrow(self):
        from code_puppy.plugins.statusline.prompt_patch import _render

        default = self._make_formatted_text()
        with (
            patch(
                "code_puppy.plugins.statusline.prompt_patch.get_status_text",
                return_value="my status",
            ),
            patch(
                "code_puppy.plugins.statusline.prompt_patch.get_mode",
                return_value="replace",
            ),
        ):
            result = _render(default, ">>> ")

        fragments = list(result)
        # Arrow must be present
        assert any(">>>" in text for _, text in fragments)
        # Reconstruct the full rendered text — ANSI() may split chars across tuples
        full_text = "".join(text for _, text in fragments)
        assert "my status" in full_text

    def test_render_above_mode_includes_newline(self):
        from code_puppy.plugins.statusline.prompt_patch import _render

        default = self._make_formatted_text()
        with (
            patch(
                "code_puppy.plugins.statusline.prompt_patch.get_status_text",
                return_value="my status",
            ),
            patch(
                "code_puppy.plugins.statusline.prompt_patch.get_mode",
                return_value="above",
            ),
        ):
            result = _render(default, ">>> ")

        fragments = list(result)
        # Should contain a newline fragment between status and default prompt
        assert any("\n" in text for _, text in fragments)

    def test_render_newline_mode_pushes_arrow_down(self):
        from code_puppy.plugins.statusline.prompt_patch import _render

        default = self._make_formatted_text()
        with (
            patch(
                "code_puppy.plugins.statusline.prompt_patch.get_status_text",
                return_value="my status",
            ),
            patch(
                "code_puppy.plugins.statusline.prompt_patch.get_mode",
                return_value="newline",
            ),
        ):
            result = _render(default, ">>> ")

        fragments = list(result)
        assert any("\n" in text for _, text in fragments)
        assert any(">>>" in text for _, text in fragments)

    def test_render_uses_default_arrow_when_base_empty(self):
        from code_puppy.plugins.statusline.prompt_patch import _render, _DEFAULT_ARROW

        default = self._make_formatted_text()
        with (
            patch(
                "code_puppy.plugins.statusline.prompt_patch.get_status_text",
                return_value="status",
            ),
            patch(
                "code_puppy.plugins.statusline.prompt_patch.get_mode",
                return_value="replace",
            ),
        ):
            result = _render(default, "")

        fragments = list(result)
        assert any(_DEFAULT_ARROW in text for _, text in fragments)

    def test_render_survives_ansi_parse_exception(self):
        """If ANSI() blows up, _render should return the default prompt unchanged."""
        from code_puppy.plugins.statusline.prompt_patch import _render

        default = self._make_formatted_text()
        with (
            patch(
                "code_puppy.plugins.statusline.prompt_patch.get_status_text",
                return_value="bad\x1b[999m",
            ),
            patch(
                "code_puppy.plugins.statusline.prompt_patch.get_mode",
                return_value="replace",
            ),
            patch(
                "prompt_toolkit.formatted_text.to_formatted_text",
                side_effect=ValueError("bad ansi"),
            ),
        ):
            result = _render(default, ">>> ")

        assert result is default


# ---------------------------------------------------------------------------
# prompt_patch.py — install_prompt_patch()
# ---------------------------------------------------------------------------


class TestInstallPromptPatch:
    def test_idempotent(self):
        """Calling install_prompt_patch() twice must not double-wrap."""
        from code_puppy.plugins.statusline import prompt_patch
        import code_puppy.command_line.prompt_toolkit_completion as ptc

        # Clean slate
        if hasattr(ptc, prompt_patch._PATCH_ATTR):
            delattr(ptc, prompt_patch._PATCH_ATTR)

        original_fn = ptc.get_prompt_with_active_model

        prompt_patch.install_prompt_patch()
        patched_once = ptc.get_prompt_with_active_model

        prompt_patch.install_prompt_patch()
        patched_twice = ptc.get_prompt_with_active_model

        # Second call must not re-wrap
        assert patched_once is patched_twice

        # Restore
        ptc.get_prompt_with_active_model = original_fn
        delattr(ptc, prompt_patch._PATCH_ATTR)

    def test_patch_replaces_function(self):
        """After install, get_prompt_with_active_model should be a new callable."""
        from code_puppy.plugins.statusline import prompt_patch
        import code_puppy.command_line.prompt_toolkit_completion as ptc

        if hasattr(ptc, prompt_patch._PATCH_ATTR):
            delattr(ptc, prompt_patch._PATCH_ATTR)

        original_fn = ptc.get_prompt_with_active_model
        prompt_patch.install_prompt_patch()

        assert ptc.get_prompt_with_active_model is not original_fn

        # Restore
        ptc.get_prompt_with_active_model = original_fn
        delattr(ptc, prompt_patch._PATCH_ATTR)


# ---------------------------------------------------------------------------
# statusline_command.py
# ---------------------------------------------------------------------------


class TestStatuslineCommand:
    def setup_method(self):
        _reset_runner()

    def _call(self, command: str, name: str = "statusline"):
        from code_puppy.plugins.statusline.statusline_command import (
            handle_statusline_command,
        )

        return handle_statusline_command(command, name)

    # --- routing ---

    def test_ignores_other_commands(self):
        assert self._call("/foo bar", "foo") is None

    # --- status (default) ---

    def test_status_subcommand_emits_info(self):
        with patch(
            "code_puppy.plugins.statusline.statusline_command.emit_info"
        ) as mock_info:
            result = self._call("/statusline")
        assert result is True
        mock_info.assert_called_once()
        text = mock_info.call_args[0][0]
        assert "mode" in text

    # --- on ---

    def test_on_with_no_command_warns(self):
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.get_command",
                return_value="",
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.emit_warning"
            ) as mock_warn,
        ):
            result = self._call("/statusline on")
        assert result is True
        mock_warn.assert_called_once()

    def test_on_enables_when_command_is_set(self):
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.get_command",
                return_value="~/bin/status.sh",
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.set_enabled"
            ) as mock_enabled,
            patch(
                "code_puppy.plugins.statusline.statusline_command.runner.reset_cache"
            ),
            patch("code_puppy.plugins.statusline.statusline_command.emit_success"),
        ):
            result = self._call("/statusline on")
        assert result is True
        mock_enabled.assert_called_once_with(True)

    # --- off ---

    def test_off_disables(self):
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.set_enabled"
            ) as mock_enabled,
            patch("code_puppy.plugins.statusline.statusline_command.emit_warning"),
        ):
            result = self._call("/statusline off")
        assert result is True
        mock_enabled.assert_called_once_with(False)

    # --- mode ---

    def test_mode_valid_sets(self):
        for mode in ("replace", "above", "newline"):
            with (
                patch(
                    "code_puppy.plugins.statusline.statusline_command.config.set_mode"
                ) as mock_mode,
                patch("code_puppy.plugins.statusline.statusline_command.emit_success"),
            ):
                result = self._call(f"/statusline mode {mode}")
            assert result is True
            mock_mode.assert_called_once_with(mode)

    def test_mode_invalid_warns(self):
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command.emit_warning"
            ) as mock_warn,
            patch("code_puppy.plugins.statusline.statusline_command.emit_info"),
        ):
            result = self._call("/statusline mode supermode")
        assert result is True
        mock_warn.assert_called_once()

    def test_mode_missing_arg_warns(self):
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command.emit_warning"
            ) as mock_warn,
            patch("code_puppy.plugins.statusline.statusline_command.emit_info"),
        ):
            result = self._call("/statusline mode")
        assert result is True
        mock_warn.assert_called_once()

    # --- show ---

    def test_show_with_no_command_warns(self):
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.get_command",
                return_value="",
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.emit_warning"
            ) as mock_warn,
        ):
            result = self._call("/statusline show")
        assert result is True
        mock_warn.assert_called_once()

    def test_show_runs_and_emits(self):
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.get_command",
                return_value="echo hello",
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.runner.run_once_sync",
                return_value="hello world",
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.emit_info"
            ) as mock_info,
        ):
            result = self._call("/statusline show")
        assert result is True
        calls = [c[0][0] for c in mock_info.call_args_list]
        assert any("hello world" in c for c in calls)

    def test_show_emits_empty_placeholder(self):
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.get_command",
                return_value="echo",
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.runner.run_once_sync",
                return_value="",
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.emit_info"
            ) as mock_info,
        ):
            result = self._call("/statusline show")
        assert result is True
        calls = [c[0][0] for c in mock_info.call_args_list]
        assert any("(empty)" in c for c in calls)

    # --- json ---

    def test_json_emits_payload(self):
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command.payload.build_payload_json",
                return_value='{"cwd": "/tmp"}',
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.emit_info"
            ) as mock_info,
        ):
            result = self._call("/statusline json")
        assert result is True
        calls = [c[0][0] for c in mock_info.call_args_list]
        assert any('{"cwd"' in c for c in calls)

    # --- init ---

    def test_init_writes_script_and_enables(self, tmp_path):
        fake_path = tmp_path / "statusline.sh"
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command._default_script_path",
                return_value=fake_path,
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.set_command"
            ) as mock_cmd,
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.set_enabled"
            ) as mock_enabled,
            patch(
                "code_puppy.plugins.statusline.statusline_command.runner.reset_cache"
            ),
            patch("code_puppy.plugins.statusline.statusline_command.emit_success"),
            patch("code_puppy.plugins.statusline.statusline_command.emit_info"),
            patch(
                "code_puppy.plugins.statusline.statusline_command._has_jq",
                return_value=True,
            ),
        ):
            result = self._call("/statusline init")

        assert result is True
        assert fake_path.exists()
        mock_cmd.assert_called_once_with(str(fake_path))
        mock_enabled.assert_called_once_with(True)

    def test_init_warns_if_no_jq(self, tmp_path):
        fake_path = tmp_path / "statusline.sh"
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command._default_script_path",
                return_value=fake_path,
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.set_command"
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.config.set_enabled"
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.runner.reset_cache"
            ),
            patch("code_puppy.plugins.statusline.statusline_command.emit_success"),
            patch("code_puppy.plugins.statusline.statusline_command.emit_info"),
            patch(
                "code_puppy.plugins.statusline.statusline_command._has_jq",
                return_value=False,
            ),
            patch(
                "code_puppy.plugins.statusline.statusline_command.emit_warning"
            ) as mock_warn,
        ):
            result = self._call("/statusline init")

        assert result is True
        mock_warn.assert_called_once()
        assert "jq" in mock_warn.call_args[0][0]

    # --- unknown subcommand ---

    def test_unknown_subcommand_warns(self):
        with (
            patch(
                "code_puppy.plugins.statusline.statusline_command.emit_warning"
            ) as mock_warn,
            patch("code_puppy.plugins.statusline.statusline_command.emit_info"),
        ):
            result = self._call("/statusline flibbertigibbet")
        assert result is True
        mock_warn.assert_called_once()

    # --- help ---

    def test_help_returns_entry(self):
        from code_puppy.plugins.statusline.statusline_command import (
            statusline_command_help,
        )

        entries = dict(statusline_command_help())
        assert "statusline" in entries
