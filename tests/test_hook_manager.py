"""
Tests for the hook_manager plugin.

Covers:
  - config.py  : load/save, flatten, toggle, delete helpers
  - hooks_menu : _wrap utility, HooksMenu data methods
  - register_callbacks : slash-command handler routing (non-TUI paths)

These tests are immutable per project policy.  Do NOT modify or delete them.
"""

import copy
import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONFIG: Dict[str, Any] = {
    "PreToolUse": [
        {
            "matcher": "Bash || agent_run_shell_command",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 /tmp/block-sed.py",
                    "timeout": 5000,
                }
            ],
        }
    ],
    "PostToolUse": [
        {
            "matcher": "Edit",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 /tmp/post-edit.py",
                    "timeout": 3000,
                    "enabled": False,
                }
            ],
        },
        {
            "matcher": "Read",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 /tmp/post-read.py",
                    "timeout": 2000,
                }
            ],
        },
    ],
}


@pytest.fixture
def tmp_settings(tmp_path: Path):
    """Write SAMPLE_CONFIG to a temp .claude/settings.json and return its path."""
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    settings_file.write_text(
        json.dumps({"hooks": SAMPLE_CONFIG}, indent=2), encoding="utf-8"
    )
    return settings_file


# ---------------------------------------------------------------------------
# config.py – load / save
# ---------------------------------------------------------------------------


class TestLoadHooksConfig:
    def test_loads_hooks_key(self, tmp_settings, monkeypatch):
        from code_puppy.plugins.hook_manager.config import load_hooks_config

        monkeypatch.chdir(tmp_settings.parent.parent)
        cfg = load_hooks_config()
        assert "PreToolUse" in cfg
        assert "PostToolUse" in cfg

    def test_returns_empty_when_missing(self, tmp_path, monkeypatch):
        from code_puppy.plugins.hook_manager.config import load_hooks_config

        monkeypatch.chdir(tmp_path)
        cfg = load_hooks_config()
        assert cfg == {}

    def test_returns_empty_on_malformed_json(self, tmp_path, monkeypatch):
        from code_puppy.plugins.hook_manager.config import load_hooks_config

        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text("NOT JSON", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        cfg = load_hooks_config()
        assert cfg == {}


class TestSaveHooksConfig:
    def test_round_trip(self, tmp_settings, monkeypatch):
        from code_puppy.plugins.hook_manager.config import (
            load_hooks_config,
            save_hooks_config,
        )

        monkeypatch.chdir(tmp_settings.parent.parent)
        cfg = load_hooks_config()
        save_hooks_config(cfg)
        reloaded = load_hooks_config()
        assert reloaded == cfg

    def test_preserves_other_top_level_keys(self, tmp_path, monkeypatch):
        from code_puppy.plugins.hook_manager.config import save_hooks_config

        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(
            json.dumps({"permissions": {"allow": ["Bash"]}, "hooks": {}}),
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        save_hooks_config({"PreToolUse": []})
        data = json.loads(settings.read_text())
        assert "permissions" in data, "other keys must be preserved"
        assert data["hooks"] == {"PreToolUse": []}

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        from code_puppy.plugins.hook_manager.config import save_hooks_config

        monkeypatch.chdir(tmp_path)
        save_hooks_config({})
        assert (tmp_path / ".claude" / "settings.json").exists()


# ---------------------------------------------------------------------------
# config.py – HookEntry
# ---------------------------------------------------------------------------


class TestHookEntry:
    def _make(self, **kwargs):
        from code_puppy.plugins.hook_manager.config import HookEntry

        defaults = dict(
            event_type="PreToolUse",
            matcher="Bash",
            hook_type="command",
            command="python3 /tmp/test.py",
        )
        defaults.update(kwargs)
        return HookEntry(**defaults)

    def test_display_command_short(self):
        e = self._make(command="python3 /tmp/test.py")
        assert e.display_command == "python3 /tmp/test.py"

    def test_display_command_truncated(self):
        e = self._make(command="x" * 70)
        assert e.display_command.endswith("...")
        assert len(e.display_command) == 60

    def test_display_matcher_truncated(self):
        e = self._make(matcher="A" * 50)
        assert e.display_matcher.endswith("...")
        assert len(e.display_matcher) == 40

    def test_display_matcher_short(self):
        e = self._make(matcher="Bash")
        assert e.display_matcher == "Bash"


# ---------------------------------------------------------------------------
# config.py – flatten_hooks
# ---------------------------------------------------------------------------


class TestFlattenHooks:
    def test_correct_count(self):
        from code_puppy.plugins.hook_manager.config import flatten_hooks

        entries = flatten_hooks(SAMPLE_CONFIG)
        assert len(entries) == 3  # 1 PreToolUse + 2 PostToolUse

    def test_event_types(self):
        from code_puppy.plugins.hook_manager.config import flatten_hooks

        entries = flatten_hooks(SAMPLE_CONFIG)
        event_types = {e.event_type for e in entries}
        assert event_types == {"PreToolUse", "PostToolUse"}

    def test_disabled_flag_preserved(self):
        from code_puppy.plugins.hook_manager.config import flatten_hooks

        entries = flatten_hooks(SAMPLE_CONFIG)
        disabled = [e for e in entries if not e.enabled]
        assert len(disabled) == 1
        assert disabled[0].command == "python3 /tmp/post-edit.py"

    def test_group_and_hook_indices(self):
        from code_puppy.plugins.hook_manager.config import flatten_hooks

        entries = flatten_hooks(SAMPLE_CONFIG)
        # PostToolUse group 0 hook 0  =>  disabled post-edit
        post = [e for e in entries if e.event_type == "PostToolUse"]
        assert post[0]._group_index == 0 and post[0]._hook_index == 0
        assert post[1]._group_index == 1 and post[1]._hook_index == 0

    def test_empty_config_returns_empty_list(self):
        from code_puppy.plugins.hook_manager.config import flatten_hooks

        assert flatten_hooks({}) == []

    def test_skips_non_list_event(self):
        from code_puppy.plugins.hook_manager.config import flatten_hooks

        bad = {"PreToolUse": "not-a-list"}
        assert flatten_hooks(bad) == []


# ---------------------------------------------------------------------------
# config.py – toggle_hook_enabled
# ---------------------------------------------------------------------------


class TestToggleHookEnabled:
    def test_enables_disabled_hook(self):
        from code_puppy.plugins.hook_manager.config import toggle_hook_enabled

        cfg = copy.deepcopy(SAMPLE_CONFIG)
        result = toggle_hook_enabled(cfg, "PostToolUse", 0, 0, True)
        assert result["PostToolUse"][0]["hooks"][0]["enabled"] is True

    def test_disables_enabled_hook(self):
        from code_puppy.plugins.hook_manager.config import toggle_hook_enabled

        cfg = copy.deepcopy(SAMPLE_CONFIG)
        result = toggle_hook_enabled(cfg, "PreToolUse", 0, 0, False)
        assert result["PreToolUse"][0]["hooks"][0]["enabled"] is False

    def test_does_not_mutate_original(self):
        from code_puppy.plugins.hook_manager.config import toggle_hook_enabled

        cfg = copy.deepcopy(SAMPLE_CONFIG)
        _ = toggle_hook_enabled(cfg, "PreToolUse", 0, 0, False)
        # Original must be unchanged (no "enabled" key = defaults to True)
        orig_hook = cfg["PreToolUse"][0]["hooks"][0]
        assert orig_hook.get("enabled", True) is True

    def test_bad_indices_logs_warning_no_crash(self):
        from code_puppy.plugins.hook_manager.config import toggle_hook_enabled

        cfg = copy.deepcopy(SAMPLE_CONFIG)
        result = toggle_hook_enabled(cfg, "PreToolUse", 99, 99, True)
        # Should return a copy of config unchanged
        assert result["PreToolUse"] == cfg["PreToolUse"]


# ---------------------------------------------------------------------------
# config.py – delete_hook
# ---------------------------------------------------------------------------


class TestDeleteHook:
    def test_removes_hook(self):
        from code_puppy.plugins.hook_manager.config import delete_hook

        cfg = copy.deepcopy(SAMPLE_CONFIG)
        # PostToolUse group 1 (Read) hook 0
        result = delete_hook(cfg, "PostToolUse", 1, 0)
        # Group 1 should be gone (was the only hook)
        assert len(result["PostToolUse"]) == 1

    def test_prunes_empty_group(self):
        from code_puppy.plugins.hook_manager.config import delete_hook

        cfg = copy.deepcopy(SAMPLE_CONFIG)
        result = delete_hook(cfg, "PostToolUse", 0, 0)
        # Group 0 (Edit) had one hook – should be removed
        remaining_matchers = [g["matcher"] for g in result["PostToolUse"]]
        assert "Edit" not in remaining_matchers

    def test_prunes_empty_event_key(self):
        from code_puppy.plugins.hook_manager.config import delete_hook

        cfg = copy.deepcopy(SAMPLE_CONFIG)
        result = delete_hook(cfg, "PreToolUse", 0, 0)
        assert "PreToolUse" not in result

    def test_does_not_mutate_original(self):
        from code_puppy.plugins.hook_manager.config import delete_hook

        cfg = copy.deepcopy(SAMPLE_CONFIG)
        _ = delete_hook(cfg, "PreToolUse", 0, 0)
        assert "PreToolUse" in cfg

    def test_bad_indices_no_crash(self):
        from code_puppy.plugins.hook_manager.config import delete_hook

        cfg = copy.deepcopy(SAMPLE_CONFIG)
        result = delete_hook(cfg, "PreToolUse", 99, 99)
        assert result["PreToolUse"] == cfg["PreToolUse"]


# ---------------------------------------------------------------------------
# hooks_menu.py – _wrap utility
# ---------------------------------------------------------------------------


class TestWrap:
    def test_short_string_single_line(self):
        from code_puppy.plugins.hook_manager.hooks_menu import _wrap

        assert _wrap("hello world", 80) == ["hello world"]

    def test_wraps_at_word_boundary(self):
        from code_puppy.plugins.hook_manager.hooks_menu import _wrap

        result = _wrap("one two three four five", 10)
        for line in result:
            assert len(line) <= 12  # some tolerance for word lengths

    def test_empty_string_returns_empty_placeholder(self):
        from code_puppy.plugins.hook_manager.hooks_menu import _wrap

        assert _wrap("", 40) == [""]

    def test_single_very_long_word(self):
        from code_puppy.plugins.hook_manager.hooks_menu import _wrap

        word = "superlongword"
        result = _wrap(word, 5)
        assert result == [word]


# ---------------------------------------------------------------------------
# hooks_menu.py – HooksMenu data methods (no TUI)
# ---------------------------------------------------------------------------


class TestHooksMenuDataMethods:
    def _make_menu(self, tmp_settings, monkeypatch):
        """Create HooksMenu with mocked global hooks to isolate to project-only testing."""
        from code_puppy.plugins.hook_manager.hooks_menu import HooksMenu

        monkeypatch.chdir(tmp_settings.parent.parent)
        # Mock _load_global_hooks_config to return empty dict for test isolation
        with patch(
            "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
            return_value={},
        ):
            return HooksMenu()

    def test_refresh_data_loads_entries(self, tmp_settings, monkeypatch):
        menu = self._make_menu(tmp_settings, monkeypatch)
        assert len(menu.entries) == 3

    def test_current_entry_is_first(self, tmp_settings, monkeypatch):
        menu = self._make_menu(tmp_settings, monkeypatch)
        entry = menu._current_entry()
        assert entry is not None
        assert entry.event_type == "PreToolUse"

    def test_current_entry_none_when_empty(self, tmp_path, monkeypatch):
        from code_puppy.plugins.hook_manager.hooks_menu import HooksMenu

        monkeypatch.chdir(tmp_path)
        with patch(
            "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
            return_value={},
        ):
            menu = HooksMenu()
        assert menu._current_entry() is None

    def test_toggle_current_persists(self, tmp_settings, monkeypatch):
        menu = self._make_menu(tmp_settings, monkeypatch)
        orig_enabled = menu.entries[0].enabled
        menu.list_control = MagicMock()
        menu.detail_control = MagicMock()
        menu._toggle_current()
        # Reload to verify disk was updated
        from code_puppy.plugins.hook_manager.config import (
            flatten_hooks,
            load_hooks_config,
        )

        cfg = load_hooks_config()
        entries = flatten_hooks(cfg)
        assert entries[0].enabled is not orig_enabled

    def test_delete_current_removes_entry(self, tmp_settings, monkeypatch):
        menu = self._make_menu(tmp_settings, monkeypatch)
        initial_count = len(menu.entries)
        menu.list_control = MagicMock()
        menu.detail_control = MagicMock()
        with patch(
            "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
            return_value={},
        ):
            menu._delete_current()
        assert len(menu.entries) == initial_count - 1

    def test_enable_all(self, tmp_settings, monkeypatch):
        menu = self._make_menu(tmp_settings, monkeypatch)
        menu.list_control = MagicMock()
        menu.detail_control = MagicMock()
        with patch(
            "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
            return_value={},
        ):
            menu._enable_all()
        assert all(e.enabled for e in menu.entries)

    def test_disable_all(self, tmp_settings, monkeypatch):
        menu = self._make_menu(tmp_settings, monkeypatch)
        menu.list_control = MagicMock()
        menu.detail_control = MagicMock()
        with patch(
            "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
            return_value={},
        ):
            menu._disable_all()
        assert all(not e.enabled for e in menu.entries)

    def test_render_list_returns_list(self, tmp_settings, monkeypatch):
        menu = self._make_menu(tmp_settings, monkeypatch)
        rendered = menu._render_list()
        assert isinstance(rendered, list)
        assert len(rendered) > 0

    def test_render_detail_returns_list(self, tmp_settings, monkeypatch):
        menu = self._make_menu(tmp_settings, monkeypatch)
        rendered = menu._render_detail()
        assert isinstance(rendered, list)
        assert len(rendered) > 0

    def test_render_list_empty_config(self, tmp_path, monkeypatch):
        from code_puppy.plugins.hook_manager.hooks_menu import HooksMenu

        monkeypatch.chdir(tmp_path)
        with patch(
            "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
            return_value={},
        ):
            menu = HooksMenu()
        rendered = menu._render_list()
        # Should render the "no hooks" message
        text_parts = "".join(t for _, t in rendered)
        assert "No hooks configured" in text_parts

    def test_render_detail_empty(self, tmp_path, monkeypatch):
        from code_puppy.plugins.hook_manager.hooks_menu import HooksMenu

        monkeypatch.chdir(tmp_path)
        with patch(
            "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
            return_value={},
        ):
            menu = HooksMenu()
        rendered = menu._render_detail()
        text_parts = "".join(t for _, t in rendered)
        assert "No hook selected" in text_parts


# ---------------------------------------------------------------------------
# register_callbacks.py – slash command routing (non-TUI paths)
# ---------------------------------------------------------------------------


class TestHandleHooksCommand:
    def _call(self, command: str, name: str = "hooks"):
        from code_puppy.plugins.hook_manager.register_callbacks import (
            _handle_hooks_command,
        )

        return _handle_hooks_command(command, name)

    def test_returns_none_for_unknown_command(self):
        result = self._call("/skills", "skills")
        assert result is None

    def test_alias_hook_is_handled(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("code_puppy.messaging.emit_info"):
            with patch(
                "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
                return_value={},
            ):
                result = self._call("/hook list", "hook")
        assert result is True

    def test_list_subcommand_returns_true(self, tmp_settings, monkeypatch):
        monkeypatch.chdir(tmp_settings.parent.parent)
        with patch("code_puppy.messaging.emit_info"):
            with patch(
                "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
                return_value={},
            ):
                result = self._call("/hooks list", "hooks")
        assert result is True

    def test_list_empty_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("code_puppy.messaging.emit_info") as mock_info:
            with patch(
                "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
                return_value={},
            ):
                result = self._call("/hooks list", "hooks")
        assert result is True
        calls = " ".join(str(c) for c in mock_info.call_args_list)
        assert "No hooks" in calls

    def test_enable_subcommand(self, tmp_settings, monkeypatch):
        monkeypatch.chdir(tmp_settings.parent.parent)
        with patch("code_puppy.messaging.emit_success") as mock_ok:
            with patch(
                "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
                return_value={},
            ):
                result = self._call("/hooks enable", "hooks")
        assert result is True
        assert mock_ok.called

    def test_disable_subcommand(self, tmp_settings, monkeypatch):
        monkeypatch.chdir(tmp_settings.parent.parent)
        with patch("code_puppy.messaging.emit_warning") as mock_warn:
            with patch(
                "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
                return_value={},
            ):
                result = self._call("/hooks disable", "hooks")
        assert result is True
        assert mock_warn.called

    def test_status_subcommand(self, tmp_settings, monkeypatch):
        monkeypatch.chdir(tmp_settings.parent.parent)
        with patch("code_puppy.messaging.emit_info") as mock_info:
            with patch(
                "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
                return_value={},
            ):
                result = self._call("/hooks status", "hooks")
        assert result is True
        calls = " ".join(str(c) for c in mock_info.call_args_list)
        assert "PreToolUse" in calls or "PostToolUse" in calls

    def test_unknown_subcommand_returns_true_with_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("code_puppy.messaging.emit_error") as mock_err:
            with patch(
                "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
                return_value={},
            ):
                result = self._call("/hooks foobar", "hooks")
        assert result is True
        assert mock_err.called

    def test_enable_then_all_hooks_enabled_on_disk(self, tmp_settings, monkeypatch):
        monkeypatch.chdir(tmp_settings.parent.parent)
        with patch("code_puppy.messaging.emit_success"):
            with patch(
                "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
                return_value={},
            ):
                self._call("/hooks enable", "hooks")
        from code_puppy.plugins.hook_manager.config import (
            flatten_hooks,
            load_hooks_config,
        )

        entries = flatten_hooks(load_hooks_config())
        assert all(e.enabled for e in entries)

    def test_disable_then_all_hooks_disabled_on_disk(self, tmp_settings, monkeypatch):
        monkeypatch.chdir(tmp_settings.parent.parent)
        with patch("code_puppy.messaging.emit_warning"):
            with patch(
                "code_puppy.plugins.hook_manager.config._load_global_hooks_config",
                return_value={},
            ):
                self._call("/hooks disable", "hooks")
        from code_puppy.plugins.hook_manager.config import (
            flatten_hooks,
            load_hooks_config,
        )

        entries = flatten_hooks(load_hooks_config())
        assert all(not e.enabled for e in entries)


# ---------------------------------------------------------------------------
# register_callbacks.py – help entries
# ---------------------------------------------------------------------------


class TestHooksCommandHelp:
    def test_help_returns_list_of_tuples(self):
        from code_puppy.plugins.hook_manager.register_callbacks import (
            _hooks_command_help,
        )

        entries = _hooks_command_help()
        assert isinstance(entries, list)
        assert len(entries) >= 1

    def test_hooks_command_advertised(self):
        from code_puppy.plugins.hook_manager.register_callbacks import (
            _hooks_command_help,
        )

        names = [name for name, _ in _hooks_command_help()]
        assert "hooks" in names

    def test_hook_alias_advertised(self):
        from code_puppy.plugins.hook_manager.register_callbacks import (
            _hooks_command_help,
        )

        names = [name for name, _ in _hooks_command_help()]
        assert "hook" in names


# ---------------------------------------------------------------------------
# Integration: plugin auto-discovery registers the callbacks
# ---------------------------------------------------------------------------


class TestPluginRegistration:
    def test_custom_command_callback_registered(self):
        # Force (re-)import so callbacks are guaranteed to be registered
        import importlib

        import code_puppy.plugins.hook_manager.register_callbacks as rcb

        importlib.reload(rcb)

        from code_puppy.callbacks import get_callbacks

        cbs = get_callbacks("custom_command")
        modules = [f.__module__ for f in cbs]
        assert any("hook_manager" in m for m in modules)

    def test_custom_command_help_callback_registered(self):
        import importlib

        import code_puppy.plugins.hook_manager.register_callbacks as rcb

        importlib.reload(rcb)

        from code_puppy.callbacks import get_callbacks

        cbs = get_callbacks("custom_command_help")
        modules = [f.__module__ for f in cbs]
        assert any("hook_manager" in m for m in modules)
