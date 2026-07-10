"""Tests for the plugin_list plugin (/plugins slash command)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from code_puppy.plugins.plugin_list.register_callbacks import (
    _build_output,
    _custom_help,
    _format_plugin_list,
    _handle_custom_command,
)

# Patch targets live on the source module because _build_output() uses
# lazy imports: ``from code_puppy.plugins import …``.
_PLUGINS_MOD = "code_puppy.plugins"
_PLUGINS_CONFIG_MOD = "code_puppy.plugins.config"


# ── Unit tests for helpers ────────────────────────────────────────────────


class TestFormatPluginList:
    def test_empty_list(self):
        assert _format_plugin_list([], set()) == "  (none)"

    def test_single_plugin(self):
        result = _format_plugin_list(["shell_safety"], set())
        assert "shell_safety" in result

    def test_multiple_sorted(self):
        result = _format_plugin_list(["zebra", "alpha", "mid"], set())
        lines = result.split("\n")
        assert len(lines) == 3
        assert "alpha" in lines[0]
        assert "mid" in lines[1]
        assert "zebra" in lines[2]

    def test_disabled_shown(self):
        result = _format_plugin_list(["alpha", "beta"], {"beta"})
        lines = result.split("\n")
        assert "(disabled)" not in lines[0]  # alpha
        assert "(disabled)" in lines[1]  # beta


class TestBuildOutput:
    def test_all_tiers_populated(self):
        loaded = {
            "builtin": ["shell_safety", "agent_skills"],
            "user": ["my_tool"],
            "project": ["repo_guard"],
        }
        with (
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value=loaded,
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=Path("/tmp/proj/.code_puppy/plugins"),
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
        ):
            output = _build_output()
            assert "Loaded Plugins" in output
            assert "Builtin (" in output
            assert "agent_skills" in output
            assert "shell_safety" in output
            assert "User (~/.code_puppy/plugins/):" in output
            assert "my_tool" in output
            assert "Project (/tmp/proj/.code_puppy/plugins/):" in output
            assert "repo_guard" in output

    def test_empty_tiers_show_none(self):
        loaded = {"builtin": ["one"], "user": [], "project": []}
        with (
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value=loaded,
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=None,
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
        ):
            output = _build_output()
            lines = output.split("\n")
            user_idx = next(
                i for i, line in enumerate(lines) if line.startswith("User")
            )
            project_idx = next(
                i for i, line in enumerate(lines) if line.startswith("Project")
            )
            assert lines[user_idx + 1].strip() == "(none)"
            assert lines[project_idx + 1].strip() == "(none)"

    def test_project_path_placeholder_when_no_dir(self):
        loaded = {"builtin": [], "user": [], "project": []}
        with (
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value=loaded,
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=None,
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
        ):
            output = _build_output()
            assert "<CWD>/.code_puppy/plugins/" in output


# ── Slash command tests ───────────────────────────────────────────────────


class TestHandleCustomCommand:
    def test_unrelated_command_returns_none(self):
        assert _handle_custom_command("/foo", "foo") is None
        assert _handle_custom_command("/help", "help") is None

    def test_bare_plugins_launches_tui(self):
        with patch(
            "code_puppy.plugins.plugin_list.plugins_menu.run_plugins_menu",
        ) as mock_menu:
            result = _handle_custom_command("/plugins", "plugins")
            assert result is True
            mock_menu.assert_called_once()

    def test_plugins_list_returns_text(self):
        loaded = {"builtin": ["a"], "user": [], "project": []}
        with (
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value=loaded,
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=None,
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
            patch(
                "code_puppy.messaging.emit_info",
            ) as mock_emit,
        ):
            result = _handle_custom_command("/plugins list", "plugins")
            assert result is True
            mock_emit.assert_called_once()
            assert "Loaded Plugins" in mock_emit.call_args[0][0]


class TestMenuShowsGatedProjectPlugins:
    """The TUI must show project plugins the trust gate held back."""

    def _make_menu(self, loaded, statuses, project_dir=None):
        from code_puppy.plugins.plugin_list.plugins_menu import PluginsMenu

        with (
            patch(f"{_PLUGINS_MOD}.get_loaded_plugins", return_value=loaded),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugin_status",
                return_value=statuses,
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=project_dir,
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
        ):
            return PluginsMenu()

    def test_gated_plugins_appear_with_status(self):
        loaded = {"builtin": ["plugin_list"], "user": [], "project": ["trusted_one"]}
        statuses = {
            "trusted_one": "loaded",
            "sketchy": "untrusted",
            "drifted": "changed",
        }
        menu = self._make_menu(loaded, statuses, Path("/proj/.code_puppy/plugins"))

        by_name = {e.name: e for e in menu.plugins if e.tier == "project"}
        assert set(by_name) == {"trusted_one", "sketchy", "drifted"}
        assert by_name["trusted_one"].status == "loaded"
        assert by_name["sketchy"].status == "untrusted"
        assert by_name["drifted"].status == "changed"
        assert menu.project_dir == "/proj/.code_puppy/plugins"

    def test_toggle_is_noop_for_gated_plugin(self):
        loaded = {"builtin": [], "user": [], "project": []}
        menu = self._make_menu(loaded, {"sketchy": "untrusted"})
        menu.selected_idx = 0

        with patch(f"{_PLUGINS_CONFIG_MOD}.set_plugin_disabled") as mock_toggle:
            menu._toggle_current()

        mock_toggle.assert_not_called()
        assert menu._changed is False

    def test_detail_pane_shows_enable_hint(self):
        from code_puppy.plugins.plugin_list.plugins_menu_render import render_detail

        loaded = {"builtin": [], "user": [], "project": []}
        menu = self._make_menu(
            loaded, {"sketchy": "untrusted"}, Path("/proj/.code_puppy/plugins")
        )
        menu.selected_idx = 0

        text = "".join(frag for _style, frag in render_detail(menu))
        assert "Press Enter" in text
        assert "disabled by default" in text
        assert "/proj/.code_puppy/plugins" in text  # project path visible


class TestSlashEnableOpensTUI:
    """Slash enable never prompts inline — it opens the TUI ceremony."""

    _MENU = "code_puppy.plugins.plugin_list.plugins_menu.run_plugins_menu"

    def _run_enable(self, tmp_path: Path, status: str, menu_effect=None):
        from code_puppy.plugins.plugin_list.project_trust_flow import (
            try_enable_project_plugin,
        )

        plugin_dir = tmp_path / ".code_puppy" / "plugins" / "sketchy"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "register_callbacks.py").write_text("# sketchy\n")

        with (
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=plugin_dir.parent,
            ),
            patch(
                "code_puppy.plugins.trust.get_trust_status",
                return_value=status,
            ),
            patch("code_puppy.plugins.trust.trust_plugin") as mock_trust,
            patch(
                f"{_PLUGINS_MOD}.load_project_plugin_now", return_value=True
            ) as mock_load,
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value={"builtin": [], "user": [], "project": []},
            ),
            patch(f"{_PLUGINS_CONFIG_MOD}.set_plugin_disabled"),
            patch("code_puppy.messaging.emit_info") as mock_info,
            patch(self._MENU, side_effect=menu_effect) as mock_menu,
        ):
            handled = try_enable_project_plugin("sketchy")
        return handled, mock_trust, mock_load, mock_info, mock_menu

    def test_untrusted_opens_tui_preselected(self, tmp_path: Path):
        handled, mock_trust, mock_load, _info, mock_menu = self._run_enable(
            tmp_path, "untrusted"
        )
        assert handled is True  # fully handled — no dispatcher leak
        mock_menu.assert_called_once_with(focus_plugin="sketchy")
        mock_trust.assert_not_called()  # only the popup grants trust
        mock_load.assert_not_called()

    def test_changed_opens_tui_preselected(self, tmp_path: Path):
        handled, _trust, _load, _info, mock_menu = self._run_enable(tmp_path, "changed")
        assert handled is True
        mock_menu.assert_called_once_with(focus_plugin="sketchy")

    def test_tui_failure_falls_back_to_text(self, tmp_path: Path):
        handled, mock_trust, _load, mock_info, _menu = self._run_enable(
            tmp_path, "untrusted", menu_effect=RuntimeError("no tty")
        )
        assert handled is True
        mock_trust.assert_not_called()
        assert "/plugins" in mock_info.call_args[0][0]

    def test_trusted_activates_directly(self, tmp_path: Path):
        handled, mock_trust, mock_load, _info, mock_menu = self._run_enable(
            tmp_path, "trusted"
        )
        assert handled is True
        mock_trust.assert_not_called()  # no re-hash on activate
        mock_load.assert_called_once_with("sketchy")
        mock_menu.assert_not_called()


class TestTrustModal:
    """The in-TUI ceremony: popup state, accept word, cancel."""

    def _gated_menu(self):
        from code_puppy.plugins.plugin_list.plugins_menu import PluginsMenu

        with (
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value={"builtin": [], "user": [], "project": []},
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugin_status",
                return_value={"sketchy": "untrusted"},
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=Path("/proj/.code_puppy/plugins"),
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
        ):
            menu = PluginsMenu()
            menu.selected_idx = 0
            yield menu

    def test_enter_on_gated_entry_opens_modal(self):
        gen = self._gated_menu()
        menu = next(gen)
        menu._toggle_current()
        assert menu.trust_target is not None
        assert menu.trust_target.name == "sketchy"

    def test_focus_plugin_preselects_and_opens_modal(self):
        from code_puppy.plugins.plugin_list.plugins_menu import PluginsMenu

        with (
            patch(
                f"{_PLUGINS_MOD}.get_loaded_plugins",
                return_value={"builtin": ["plugin_list"], "user": [], "project": []},
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugin_status",
                return_value={"sketchy": "untrusted"},
            ),
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=Path("/proj/.code_puppy/plugins"),
            ),
            patch(
                f"{_PLUGINS_CONFIG_MOD}.get_disabled_plugins",
                return_value=set(),
            ),
        ):
            menu = PluginsMenu(focus_plugin="sketchy")

        entry = menu.plugins[menu.selected_idx]
        assert entry.name == "sketchy"  # preselected, not index 0
        assert menu.trust_target is entry  # ceremony popup already open

    def test_wrong_word_sets_error_and_grants_nothing(self):
        from types import SimpleNamespace

        gen = self._gated_menu()
        menu = next(gen)
        menu._toggle_current()
        with patch(
            "code_puppy.plugins.plugin_list.project_trust_flow.grant_trust_and_load"
        ) as mock_grant:
            keep = menu._accept_trust(SimpleNamespace(text="nope"))
        mock_grant.assert_not_called()
        assert keep is False  # box clears for retry
        assert menu.trust_error
        assert menu.trust_target is not None  # modal stays open

    def test_accept_word_grants_and_closes(self):
        from types import SimpleNamespace

        gen = self._gated_menu()
        menu = next(gen)
        menu._toggle_current()
        with (
            patch(
                "code_puppy.plugins.plugin_list.project_trust_flow.grant_trust_and_load",
                return_value=(True, "loaded!"),
            ) as mock_grant,
            patch.object(menu, "_refresh_data"),
        ):
            menu._accept_trust(SimpleNamespace(text="  TRUST  "))
        mock_grant.assert_called_once_with("sketchy")
        assert menu.trust_target is None  # modal closed
        assert menu.trust_feedback == "loaded!"

    def test_escape_cancels_without_granting(self):
        gen = self._gated_menu()
        menu = next(gen)
        menu._toggle_current()
        with patch(
            "code_puppy.plugins.plugin_list.project_trust_flow.grant_trust_and_load"
        ) as mock_grant:
            menu._close_trust_modal()
        mock_grant.assert_not_called()
        assert menu.trust_target is None


class TestBannerShowsProjectPath:
    def test_banner_names_the_project(self):
        from code_puppy.plugins.trust_notice import emit_skipped_plugin_notice

        with (
            patch(
                f"{_PLUGINS_MOD}.get_project_plugins_directory",
                return_value=Path("/proj/.code_puppy/plugins"),
            ),
            patch("code_puppy.messaging.emit_warning") as mock_warn,
        ):
            emit_skipped_plugin_notice({"sketchy": "untrusted"})

        banner = mock_warn.call_args[0][0]
        assert "/proj/.code_puppy/plugins" in banner.plain


class TestCustomHelp:
    def test_returns_plugins_entry(self):
        entries = _custom_help()
        assert len(entries) == 1
        cmd, desc = entries[0]
        assert cmd == "plugins"
        assert "plugin" in desc.lower()
