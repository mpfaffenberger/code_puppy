"""``model_factory._resolve_anthropic_model_class`` selection tests."""

from code_puppy.anthropic_native_editor_model import AnthropicNativeEditorModel
from code_puppy.model_factory import AnthropicModel, _resolve_anthropic_model_class


def test_resolves_to_plain_model_when_capability_disabled(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.model_factory.supports_anthropic_native_editor",
        lambda model_name, config: False,
    )
    result = _resolve_anthropic_model_class("claude-x", {"type": "anthropic"})
    assert result is AnthropicModel


def test_resolves_to_native_editor_model_when_capability_enabled(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.model_factory.supports_anthropic_native_editor",
        lambda model_name, config: True,
    )
    result = _resolve_anthropic_model_class("claude-x", {"type": "anthropic"})
    assert result is AnthropicNativeEditorModel


def test_passes_a_single_entry_config_keyed_by_the_resolved_model_name(monkeypatch):
    """The helper must hand the capability check a config shaped like the
    full models.json (``{name: config}``), not the bare model_config dict --
    ``get_model_config`` looks it up by key."""
    seen = {}

    def _fake_supports(model_name, models_config):
        seen["model_name"] = model_name
        seen["models_config"] = models_config
        return False

    monkeypatch.setattr(
        "code_puppy.model_factory.supports_anthropic_native_editor", _fake_supports
    )
    model_config = {"type": "anthropic", "name": "claude-x"}
    _resolve_anthropic_model_class("claude-x", model_config)

    assert seen == {
        "model_name": "claude-x",
        "models_config": {"claude-x": model_config},
    }
