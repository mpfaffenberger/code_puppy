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
