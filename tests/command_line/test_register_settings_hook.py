"""The ``register_settings`` hook: one plugin declaration feeds /set everywhere."""

from __future__ import annotations

import pytest
from termflow.tui.completion import Document

from code_puppy import callbacks
from code_puppy.command_line import completers
from code_puppy.command_line.set_menu_schema import Setting, SettingsCategory
from code_puppy.command_line.set_menu_settings import iter_curated_settings
from code_puppy.command_line.set_menu_values import is_sensitive_key
from code_puppy.config import get_config_keys, set_config_value


def _setting(key: str, **kwargs) -> Setting:
    return Setting(
        key=key, display_name=key, description="d", type_hint="string", **kwargs
    )


@pytest.fixture
def register(monkeypatch):
    """Register settings callbacks on a clean, per-test hook list."""
    monkeypatch.setitem(callbacks._callbacks, "register_settings", [])
    completers._config_keys_cache.clear()
    yield lambda result: callbacks.register_callback(
        "register_settings", lambda: result
    )
    completers._config_keys_cache.clear()


def _pairs() -> dict[str, str]:
    return {setting.key: category.name for category, setting in iter_curated_settings()}


def test_accepts_one_category_a_list_or_none_and_drops_junk(register, caplog):
    register(SettingsCategory("Solo", (_setting("solo_key"),)))
    register([SettingsCategory("Pair", (_setting("pair_key"),)), "junk"])
    register(None)
    names = [category.name for category in callbacks.on_register_settings()]
    assert names == ["Solo", "Pair"]
    assert "junk" in caplog.text


def test_plugin_keys_are_config_keys_even_before_they_are_saved(register):
    register(SettingsCategory("Plugin", (_setting("plugin_knob"),)))
    assert "plugin_knob" in get_config_keys()


def test_same_named_category_merges_new_one_appends(register):
    register(SettingsCategory("Features", (_setting("plugin_feature"),)))
    register(SettingsCategory("Brand New", (_setting("plugin_other"),)))
    pairs = _pairs()
    assert pairs["plugin_feature"] == "Features"
    assert pairs["plugin_other"] == "Brand New"
    assert list(pairs)[-1] == "plugin_other"  # plugin categories come last
    assert [n for n in dict.fromkeys(pairs.values())].count("Features") == 1


def test_core_wins_then_first_plugin_wins(register):
    register(SettingsCategory("Hijack", (_setting("yolo_mode"), _setting("dup"))))
    register(SettingsCategory("Late", (_setting("dup"),)))
    keys = [setting.key for _, setting in iter_curated_settings()]
    assert keys.count("yolo_mode") == keys.count("dup") == 1
    assert _pairs()["yolo_mode"] != "Hijack"
    assert _pairs()["dup"] == "Hijack"


def test_completion_lists_plugin_key_and_never_echoes_secrets(register):
    register(
        SettingsCategory(
            "Plugin",
            (_setting("plugin_plain"), _setting("plugin_secret", sensitive=True)),
        )
    )
    set_config_value("plugin_plain", "shown")
    set_config_value("plugin_secret", "hunter2")
    assert is_sensitive_key("plugin_secret")
    document = Document(text="/set plugin_", cursor_position=len("/set plugin_"))
    texts = [c.text for c in completers.SetCompleter().get_completions(document, None)]
    assert texts == ["plugin_plain = shown", "plugin_secret = "]
