"""Tests for the ``summarization_model`` config setting.

Covers:
- ``get_summarization_model_name()`` — falls back to global when unset/empty
- ``set_summarization_model_name()`` — persists via set_config_value
- ``get_config_keys()`` — new key is discoverable for ``/set`` tab-completion
- ``summarization_agent.reload_summarization_agent`` — reads the new setting
"""

from __future__ import annotations

from unittest.mock import patch

from code_puppy import config as cp_config
from code_puppy.config import (
    get_config_keys,
    get_summarization_model_name,
    set_summarization_model_name,
)


class TestGetSummarizationModelName:
    """Fallback semantics are the core of this feature."""

    def test_returns_configured_value_when_set(self):
        with (
            patch.object(
                cp_config, "get_value", return_value="firepass-kimi-k2p5-turbo"
            ),
            patch.object(
                cp_config, "get_global_model_name", return_value="should-not-be-used"
            ),
        ):
            assert get_summarization_model_name() == "firepass-kimi-k2p5-turbo"

    def test_falls_back_to_global_when_unset(self):
        with (
            patch.object(cp_config, "get_value", return_value=None),
            patch.object(
                cp_config, "get_global_model_name", return_value="claude-opus-4-7"
            ),
        ):
            assert get_summarization_model_name() == "claude-opus-4-7"

    def test_falls_back_to_global_when_empty_string(self):
        """Empty string in config should be treated as unset, not as a valid model."""
        with (
            patch.object(cp_config, "get_value", return_value=""),
            patch.object(
                cp_config, "get_global_model_name", return_value="claude-opus-4-7"
            ),
        ):
            assert get_summarization_model_name() == "claude-opus-4-7"

    def test_reads_from_summarization_model_key(self):
        """Verify it looks up the correct config key, not some other name."""
        with (
            patch.object(cp_config, "get_value") as mock_get,
            patch.object(cp_config, "get_global_model_name", return_value="default"),
        ):
            mock_get.return_value = None
            get_summarization_model_name()
            mock_get.assert_called_with("summarization_model")


class TestSetSummarizationModelName:
    def test_persists_via_set_config_value(self):
        with patch.object(cp_config, "set_config_value") as mock_set:
            set_summarization_model_name("firepass-kimi-k2p5-turbo")
            mock_set.assert_called_once_with(
                "summarization_model", "firepass-kimi-k2p5-turbo"
            )

    def test_empty_string_clears_setting(self):
        """Passing empty string should clear the key (falls back to global)."""
        with patch.object(cp_config, "set_config_value") as mock_set:
            set_summarization_model_name("")
            mock_set.assert_called_once_with("summarization_model", "")

    def test_none_is_treated_as_clear(self):
        """None should not crash — coerce to empty string."""
        with patch.object(cp_config, "set_config_value") as mock_set:
            set_summarization_model_name(None)  # type: ignore[arg-type]
            mock_set.assert_called_once_with("summarization_model", "")


class TestConfigKeyDiscovery:
    def test_summarization_model_is_discoverable(self):
        """The new key must appear in get_config_keys() so /set tab-completion works."""
        keys = get_config_keys()
        assert "summarization_model" in keys, (
            "summarization_model missing from get_config_keys() — "
            "won't show up in /set tab-completion"
        )


class TestSummarizationAgentUsesNewGetter:
    """Integration-style: does the summarization sub-agent actually read
    from our new getter when it builds its Agent?"""

    def test_reload_summarization_agent_reads_new_key(self, monkeypatch):
        """reload_summarization_agent() should resolve the model via the new getter."""
        from code_puppy import summarization_agent

        # Intercept the get_summarization_model_name call
        monkeypatch.setattr(
            summarization_agent,
            "get_summarization_model_name",
            lambda: "synthetic-GLM-5.1",
        )

        # Stub ModelFactory to avoid actually building a model (which would need keys)
        captured = {}

        def fake_get_model(name, _config):
            captured["model_name"] = name

            class _FakeModel:
                pass

            return _FakeModel()

        monkeypatch.setattr(
            summarization_agent.ModelFactory, "get_model", fake_get_model
        )
        monkeypatch.setattr(
            summarization_agent.ModelFactory,
            "load_config",
            lambda: {"synthetic-GLM-5.1": {}},
        )
        monkeypatch.setattr(summarization_agent, "make_model_settings", lambda _n: {})

        # Avoid real Agent construction
        class _FakeAgent:
            def __init__(self, **kw):
                pass

        monkeypatch.setattr(summarization_agent, "Agent", _FakeAgent)

        summarization_agent.reload_summarization_agent()

        assert captured["model_name"] == "synthetic-GLM-5.1", (
            f"Summarization agent built with wrong model: {captured['model_name']}"
        )
