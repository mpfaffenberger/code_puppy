"""Route/feature-flag capability resolution for the Anthropic native editor.

Covers the two independent gates ``supports_anthropic_native_editor`` must
apply: the opt-in feature flag and the declared-route check. Each test would
fail if the gate were dropped or if the route check ever fell back to a
model-name guess.
"""

import pytest

from code_puppy.model_capabilities import (
    get_model_config,
    is_direct_anthropic_route,
    supports_anthropic_native_editor,
)

_MODELS_CONFIG = {
    "claude-direct": {"type": "anthropic", "name": "claude-direct"},
    "claude-via-code": {"type": "claude_code", "name": "claude-via-code"},
    "claude-custom-endpoint": {
        "type": "custom_anthropic",
        "name": "claude-custom-endpoint",
    },
    "claude-via-openrouter": {
        "type": "openai",
        "name": "claude-via-openrouter",
        "provider": "openrouter",
    },
}


@pytest.mark.parametrize(
    "model_name,expected",
    [
        ("claude-direct", True),
        ("claude-via-code", False),
        ("claude-custom-endpoint", False),
        ("claude-via-openrouter", False),
        ("does-not-exist", False),
        (None, False),
    ],
)
def test_native_editor_requires_declared_direct_anthropic_route(
    monkeypatch, model_name, expected
):
    """Route decision must come from the declared config ``type``, never a
    model-name substring -- 'claude-via-openrouter' must not pass despite
    the name."""
    monkeypatch.setattr(
        "code_puppy.model_capabilities.get_anthropic_native_editor_enabled",
        lambda: True,
    )
    assert supports_anthropic_native_editor(model_name, _MODELS_CONFIG) is expected


def test_native_editor_disabled_when_feature_flag_off_even_on_direct_route(
    monkeypatch,
):
    """A supported route must still be refused if the feature flag is off --
    the native path must not be reachable by route alone."""
    monkeypatch.setattr(
        "code_puppy.model_capabilities.get_anthropic_native_editor_enabled",
        lambda: False,
    )
    assert supports_anthropic_native_editor("claude-direct", _MODELS_CONFIG) is False


def test_get_anthropic_native_editor_enabled_defaults_off(monkeypatch):
    """The rollout switch must default to off -- native must not be the
    default at merge (Phase 4 decides the default later)."""
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: None)
    from code_puppy.model_capabilities import get_anthropic_native_editor_enabled

    assert get_anthropic_native_editor_enabled() is False


def test_get_anthropic_native_editor_enabled_reads_config_flag(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.config.get_value",
        lambda key: "true" if key == "enable_anthropic_native_editor" else None,
    )
    from code_puppy.model_capabilities import get_anthropic_native_editor_enabled

    assert get_anthropic_native_editor_enabled() is True


def test_get_model_config_uses_provided_config_without_reloading(monkeypatch):
    """When a config dict is supplied, it must be used as-is -- no full
    reload (which would defeat the point of passing an already-loaded
    config to avoid a second load per agent-build pass)."""

    def _explode():
        raise AssertionError("must not reload config when one was provided")

    monkeypatch.setattr("code_puppy.model_capabilities._load_models_config", _explode)
    assert get_model_config("claude-direct", _MODELS_CONFIG) == {
        "type": "anthropic",
        "name": "claude-direct",
    }


def test_get_model_config_falls_back_to_cached_loader_when_no_config_given(
    monkeypatch,
):
    """The real production call path -- register_tools_for_agent calling
    supports_anthropic_native_editor(model_name) with NO explicit config --
    goes through _model_config_cache/_load_models_config, not the
    provided-config short-circuit the test above covers. Every other test in
    this module passes ``_MODELS_CONFIG`` explicitly and so never exercises
    this branch at all."""
    from code_puppy import model_capabilities

    model_capabilities._model_config_cache.clear()
    monkeypatch.setattr(
        model_capabilities, "_load_models_config", lambda: dict(_MODELS_CONFIG)
    )
    try:
        resolved = get_model_config("claude-direct")
        assert resolved == {"type": "anthropic", "name": "claude-direct"}
        assert is_direct_anthropic_route(resolved) is True
    finally:
        model_capabilities._model_config_cache.clear()


def test_get_model_config_returns_none_for_unknown_or_missing_name():
    assert get_model_config("does-not-exist", _MODELS_CONFIG) is None
    assert get_model_config(None, _MODELS_CONFIG) is None


@pytest.mark.parametrize(
    "model_config,expected",
    [
        ({"type": "anthropic"}, True),
        ({"type": "custom_anthropic"}, False),
        ({"type": "claude_code"}, False),
        ({"type": "openai"}, False),
        (None, False),
        ({}, False),
    ],
)
def test_is_direct_anthropic_route(model_config, expected):
    assert is_direct_anthropic_route(model_config) is expected
