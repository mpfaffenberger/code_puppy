"""Routing tests for the TUI model-settings save/reset helpers.

The TUI reuses the classic ``SETTING_DEFINITIONS`` but has its own persistence
helpers. Two storage backends must be routed correctly, exactly like
``ModelSettingsMenu._save_edit`` / ``_reset_to_default``:

* per-model retry overrides -> the dedicated ``retry_model_`` namespace
* everything else (incl. OpenAI reasoning_effort/summary/verbosity, which
  main made per-model in 6faab505) -> generic per-model ``set_model_setting``

Regression guard for the bug where retry edits fell through to
``set_model_setting`` and silently no-opped, and for the stale global
``set_openai_*`` setters that were removed upstream.
"""

import code_puppy.tui.screens.model_settings as ms
from code_puppy.config import CUSTOM_MODEL_SETTING


def test_save_retry_setting_routes_to_retry_namespace(monkeypatch):
    calls = {"retry": [], "generic": []}
    monkeypatch.setattr(
        ms, "_write_per_model_retry", lambda m, k, v: calls["retry"].append((m, k, v))
    )
    monkeypatch.setattr(
        ms, "set_model_setting", lambda m, k, v: calls["generic"].append((m, k, v))
    )

    ms._save_setting("gpt-x", "retry_main_max_attempts", 5)

    assert calls["retry"] == [("gpt-x", "retry_main_max_attempts", 5)]
    assert calls["generic"] == []  # must NOT leak into the generic store


def test_reset_retry_setting_clears_retry_namespace(monkeypatch):
    calls = {"retry": [], "generic": []}
    monkeypatch.setattr(
        ms, "_write_per_model_retry", lambda m, k, v: calls["retry"].append((m, k, v))
    )
    monkeypatch.setattr(
        ms, "set_model_setting", lambda m, k, v: calls["generic"].append((m, k, v))
    )

    ms._reset_setting("gpt-x", "retry_subagent_strategy")

    assert calls["retry"] == [("gpt-x", "retry_subagent_strategy", None)]
    assert calls["generic"] == []


def test_save_generic_setting_routes_to_set_model_setting(monkeypatch):
    """Non-retry, non-global settings (e.g. GPT-5.6 reasoning_context) stay
    on the generic per-model store."""
    calls = {"retry": [], "generic": []}
    monkeypatch.setattr(
        ms, "_write_per_model_retry", lambda m, k, v: calls["retry"].append((m, k, v))
    )
    monkeypatch.setattr(
        ms, "set_model_setting", lambda m, k, v: calls["generic"].append((m, k, v))
    )

    ms._save_setting("gpt-5.6", "reasoning_context", "current_turn")

    assert calls["generic"] == [("gpt-5.6", "reasoning_context", "current_turn")]
    assert calls["retry"] == []


def test_save_reasoning_setting_routes_per_model(monkeypatch):
    """OpenAI reasoning controls are now per-model (main removed the global
    ``set_openai_*`` setters in 6faab505), so they route through
    ``set_model_setting`` like any other non-retry setting."""
    calls = {"retry": [], "generic": []}
    monkeypatch.setattr(
        ms, "_write_per_model_retry", lambda m, k, v: calls["retry"].append((m, k, v))
    )
    monkeypatch.setattr(
        ms, "set_model_setting", lambda m, k, v: calls["generic"].append((m, k, v))
    )

    ms._save_setting("gpt-x", "reasoning_effort", "high")

    assert calls["generic"] == [("gpt-x", "reasoning_effort", "high")]
    assert calls["retry"] == []


def test_reset_reasoning_setting_routes_per_model(monkeypatch):
    """Resetting a reasoning control clears the per-model value (None)."""
    calls = {"retry": [], "generic": []}
    monkeypatch.setattr(
        ms, "_write_per_model_retry", lambda m, k, v: calls["retry"].append((m, k, v))
    )
    monkeypatch.setattr(
        ms, "set_model_setting", lambda m, k, v: calls["generic"].append((m, k, v))
    )

    ms._reset_setting("gpt-x", "reasoning_effort")

    assert calls["generic"] == [("gpt-x", "reasoning_effort", None)]
    assert calls["retry"] == []


def test_supported_settings_includes_retry_and_custom_keys(monkeypatch):
    """Regression guard (PUP parity audit, 2026-08-01): retry overrides and
    the reserved 'custom' key apply to every model regardless of the
    per-model ``supported_settings`` allowlist -- model_supports_setting()
    alone says False for both, so _supported_settings() must bypass it
    (mirrors ModelSettingsMenu._get_supported_settings). Before this fix
    retry settings/custom params silently vanished from the TUI editor.
    """
    monkeypatch.setattr(ms, "model_supports_setting", lambda model, key: False)

    supported = ms._supported_settings("any-model")

    assert "retry_main_strategy" in supported
    assert "retry_main_max_attempts" in supported
    assert "retry_subagent_strategy" in supported
    assert "retry_subagent_max_attempts" in supported
    assert CUSTOM_MODEL_SETTING in supported


def test_reset_custom_setting_clears_all_pairs(monkeypatch):
    """Resetting the custom-params entry means "no custom params at all"
    (there's no static default to fall back to), not a no-op write through
    set_model_setting -- mirrors ModelSettingsMenu._reset_to_default."""
    monkeypatch.setattr(ms, "get_custom_model_settings", lambda m: {"a": 1, "b": 2})
    cleared = []
    monkeypatch.setattr(
        ms, "set_custom_model_setting", lambda m, k, v: cleared.append((m, k, v))
    )
    generic_calls = []
    monkeypatch.setattr(
        ms, "set_model_setting", lambda m, k, v: generic_calls.append((m, k, v))
    )

    ms._reset_setting("gpt-x", CUSTOM_MODEL_SETTING)

    assert set(cleared) == {("gpt-x", "a", None), ("gpt-x", "b", None)}
    assert generic_calls == []  # must not fall through to the scalar store


def test_format_value_renders_custom_pairs():
    """The custom dict must render as 'k=v; k=v', not a raw dict repr or a
    crash from the scalar format-string branch."""
    rendered = ms._format_value(
        CUSTOM_MODEL_SETTING, {"chat_template_kwargs.thinking": "medium"}, "gpt-x"
    )
    assert rendered == "chat_template_kwargs.thinking=medium"


def test_format_value_custom_empty_or_none_shows_none():
    assert ms._format_value(CUSTOM_MODEL_SETTING, {}, "gpt-x") == "(none)"
    assert ms._format_value(CUSTOM_MODEL_SETTING, None, "gpt-x") == "(none)"
