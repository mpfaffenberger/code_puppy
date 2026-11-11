"""Settings must be discoverable before users have saved them once."""

import configparser

import pytest
from termflow.tui.completion import Document

from code_puppy import callbacks, config
from code_puppy.command_line import completers
from code_puppy.command_line.config_apply import MODEL_SETTINGS_ONLY_KEYS
from code_puppy.command_line.set_menu_catalog import SETTINGS_CATEGORIES
from code_puppy.command_line.set_menu_schema import Setting, SettingsCategory

ADDITIONAL_KEYS = {
    "classic_prompt",
    "command_timeout_seconds",
    "disabled_plugins",
    "enable_speculative_code_mode",
    "osc_palette_json",
    "port_base",
}
PLUGIN_KEYS = {
    "auto_continue_model",
    "frontend_emitter_enabled",
    "frontend_emitter_max_recent_events",
    "frontend_emitter_queue_size",
}
CATALOG_KEYS = {
    setting.key for category in SETTINGS_CATEGORIES for setting in category.settings
}
HIDDEN_KEYS = {"model", "puppy_token"} | MODEL_SETTINGS_ONLY_KEYS


@pytest.fixture
def empty_config(monkeypatch):
    monkeypatch.setattr(config, "_load_config", configparser.ConfigParser)
    monkeypatch.setitem(callbacks._callbacks, "register_settings", [])
    completers._config_keys_cache.clear()
    yield
    completers._config_keys_cache.clear()


def test_catalog_and_additional_keys_discoverable_without_saved_values(empty_config):
    keys = config.get_config_keys()
    assert CATALOG_KEYS | ADDITIONAL_KEYS <= set(keys)
    assert keys == sorted(set(keys))


@pytest.mark.parametrize("key", sorted((CATALOG_KEYS | ADDITIONAL_KEYS) - HIDDEN_KEYS))
def test_unsaved_setting_has_prompt_completion(empty_config, key):
    text = f"/set {key}"
    document = Document(text=text, cursor_position=len(text))
    suggestions = list(completers.SetCompleter().get_completions(document, None))
    assert f"{key} = " in [item.text for item in suggestions]


def test_plugin_keys_not_hardcoded_in_core(empty_config):
    assert not PLUGIN_KEYS & set(config.get_config_keys())


def test_plugin_settings_discovered_through_real_hook(empty_config, monkeypatch):
    category = SettingsCategory(
        "Test plugin",
        tuple(
            Setting(key=key, display_name=key, description="Test", type_hint="string")
            for key in sorted(PLUGIN_KEYS)
        ),
    )
    callbacks.register_callback("register_settings", lambda: category)
    assert PLUGIN_KEYS <= set(config.get_config_keys())
    for key in sorted(PLUGIN_KEYS):
        text = f"/set {key}"
        document = Document(text=text, cursor_position=len(text))
        suggestions = list(completers.SetCompleter().get_completions(document, None))
        assert f"{key} = " in [item.text for item in suggestions]


def test_existing_and_plugin_keys_preserved(empty_config, monkeypatch):
    parser = configparser.ConfigParser()
    parser[config.DEFAULT_SECTION] = {"custom_saved_key": "yes"}
    monkeypatch.setattr(config, "_load_config", lambda: parser)
    monkeypatch.setattr(config, "_plugin_setting_keys", lambda: {"plugin_key"})
    assert {"custom_saved_key", "plugin_key"} <= set(config.get_config_keys())


def test_deliberate_completion_exclusions_preserved(empty_config, monkeypatch):
    monkeypatch.setattr(
        completers, "get_config_keys", lambda: sorted(CATALOG_KEYS | HIDDEN_KEYS)
    )
    text = "/set "
    document = Document(text=text, cursor_position=len(text))
    suggestions = list(completers.SetCompleter().get_completions(document, None))
    completed_keys = {item.text.split(" = ", 1)[0] for item in suggestions}
    assert not completed_keys & HIDDEN_KEYS
    assert "show_tool_output" in completed_keys
