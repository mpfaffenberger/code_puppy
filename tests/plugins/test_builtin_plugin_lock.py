"""Tests for the builtin-plugin lock (hidden ``lock_builtin_plugins`` key).

When the lock is active:
  * disabling a builtin plugin is refused at the config layer
  * re-enabling a builtin is always allowed (never strand one disabled)
  * user/project plugins remain freely toggleable
  * the /plugins menu hides builtins and shows a managed-count note
"""

from __future__ import annotations

import json
from unittest.mock import patch

from code_puppy.plugins import config as pc
from code_puppy.plugins.plugin_list.plugins_menu import PluginsMenu

_FAKE_LOADED = {
    "builtin": ["plugin_list", "agent_skills", "emoji_filter"],
    "user": ["convo_namer"],
    "project": [],
}


# ── config layer ────────────────────────────────────────────────


def test_is_builtin_plugin_filesystem_truth():
    assert pc.is_builtin_plugin("plugin_list")  # ships in code_puppy/plugins/
    assert not pc.is_builtin_plugin("convo_namer")  # user-tier name
    assert not pc.is_builtin_plugin("does_not_exist")


def test_lock_defaults_off():
    assert pc.get_lock_builtin_plugins() is False


def test_lock_roundtrip():
    pc.set_lock_builtin_plugins(True)
    assert pc.get_lock_builtin_plugins() is True
    pc.set_lock_builtin_plugins(False)
    assert pc.get_lock_builtin_plugins() is False


def test_builtin_disablable_when_unlocked():
    pc.set_lock_builtin_plugins(False)
    assert pc.set_plugin_disabled("plugin_list", True) is True
    assert "plugin_list" in pc.get_disabled_plugins()


def test_builtin_disable_refused_when_locked():
    pc.set_lock_builtin_plugins(True)
    assert pc.set_plugin_disabled("plugin_list", True) is False
    assert "plugin_list" not in pc.get_disabled_plugins()


def test_user_plugin_disablable_when_locked():
    pc.set_lock_builtin_plugins(True)
    assert pc.set_plugin_disabled("convo_namer", True) is True
    assert "convo_namer" in pc.get_disabled_plugins()


def test_builtin_reenable_always_allowed_when_locked():
    # A builtin somehow already in the disabled set must be recoverable.
    from code_puppy.config import set_value

    set_value("disabled_plugins", json.dumps(["plugin_list"]))
    pc.set_lock_builtin_plugins(True)
    assert pc.set_plugin_disabled("plugin_list", False) is True
    assert "plugin_list" not in pc.get_disabled_plugins()


# ── menu layer ──────────────────────────────────────────────────


def test_menu_shows_all_when_unlocked():
    pc.set_lock_builtin_plugins(False)
    with patch("code_puppy.plugins.get_loaded_plugins", return_value=_FAKE_LOADED):
        menu = PluginsMenu()
    tiers = {e.tier for e in menu.plugins}
    assert "builtin" in tiers and "user" in tiers
    assert menu.hidden_builtin_count == 0


def test_menu_hides_builtins_when_locked():
    pc.set_lock_builtin_plugins(True)
    with patch("code_puppy.plugins.get_loaded_plugins", return_value=_FAKE_LOADED):
        menu = PluginsMenu()
    names = {e.name for e in menu.plugins}
    assert names == {"convo_namer"}
    assert all(e.tier != "builtin" for e in menu.plugins)
    assert menu.hidden_builtin_count == 3


def test_menu_renders_managed_note_when_locked():
    pc.set_lock_builtin_plugins(True)
    with patch("code_puppy.plugins.get_loaded_plugins", return_value=_FAKE_LOADED):
        menu = PluginsMenu()
        text = "".join(seg for _, seg in menu._render_list())
    assert "3 builtin plugins are managed and hidden" in text


def test_menu_toggle_does_not_flag_changed_on_refusal():
    """Selecting a builtin (only possible if lock flips mid-session) and
    toggling must not falsely set the restart-needed flag."""
    pc.set_lock_builtin_plugins(False)
    with patch("code_puppy.plugins.get_loaded_plugins", return_value=_FAKE_LOADED):
        menu = PluginsMenu()
        # Force selection onto a builtin, then lock and toggle.
        builtin_idx = next(i for i, e in enumerate(menu.plugins) if e.tier == "builtin")
        menu.selected_idx = builtin_idx
        pc.set_lock_builtin_plugins(True)
        menu._toggle_current()
    assert menu._changed is False


# ── idempotent set ──────────────────────────────────────────────


def test_set_lock_builtin_plugins_is_idempotent():
    pc.set_lock_builtin_plugins(False)
    pc.set_lock_builtin_plugins(True)
    assert pc.get_lock_builtin_plugins() is True
    # Second call is a harmless no-op.
    pc.set_lock_builtin_plugins(True)
    assert pc.get_lock_builtin_plugins() is True
