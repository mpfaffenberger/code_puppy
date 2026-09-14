"""Tests for the configurable output-token cap (``max_output_tokens``).

Covers the resolution chain in ``config.get_model_max_output_tokens``
(per-model override > catalog entry > heuristic) and its integration into
``make_model_settings`` -- including that the raw key never leaks into the
provider-bound ModelSettings.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import code_puppy.config as cp_config
from code_puppy import models_dev_parser
from code_puppy.model_factory import ModelFactory, make_model_settings
from code_puppy.models_dev_parser import ModelInfo

MODEL = "acme-large"


@pytest.fixture
def catalog():
    """One model with a models.dev-sourced output cap, one without."""
    return {
        MODEL: {"type": "custom_openai", "context_length": 200000},
        "acme-capped": {
            "type": "custom_openai",
            "context_length": 200000,
            "max_output_tokens": 64000,
        },
    }


class TestGetModelMaxOutputTokens:
    def test_heuristic_when_nothing_configured(self, catalog):
        # 15% of 200k = 30000, inside the [2048, 65536] clamp.
        assert cp_config.get_model_max_output_tokens(MODEL, catalog) == 30000

    @pytest.mark.parametrize(
        "context_length,expected",
        [(8000, 2048), (1_000_000, 65536), (128000, 19200)],
    )
    def test_heuristic_clamps(self, context_length, expected):
        cfg = {MODEL: {"context_length": context_length}}
        assert cp_config.get_model_max_output_tokens(MODEL, cfg) == expected

    def test_catalog_value_beats_heuristic(self, catalog):
        assert cp_config.get_model_max_output_tokens("acme-capped", catalog) == 64000

    def test_per_model_override_beats_catalog(self, catalog):
        cp_config.set_model_setting("acme-capped", "max_output_tokens", 8192)
        assert cp_config.get_model_max_output_tokens("acme-capped", catalog) == 8192

    def test_float_stored_override_is_coerced_to_int(self, catalog):
        cp_config.set_model_setting(MODEL, "max_output_tokens", 4096.0)
        result = cp_config.get_model_max_output_tokens(MODEL, catalog)
        assert result == 4096 and isinstance(result, int)

    @pytest.mark.parametrize("bad", ["", "nope", "0", "-5"])
    def test_garbage_override_falls_through(self, catalog, bad):
        with patch.object(cp_config, "get_value", return_value=bad):
            assert (
                cp_config.get_model_max_output_tokens("acme-capped", catalog) == 64000
            )

    def test_garbage_catalog_value_falls_through_to_heuristic(self):
        cfg = {MODEL: {"context_length": 200000, "max_output_tokens": "lots"}}
        assert cp_config.get_model_max_output_tokens(MODEL, cfg) == 30000

    def test_loads_catalog_when_not_provided(self, catalog):
        with patch.object(ModelFactory, "load_config", return_value=catalog):
            assert cp_config.get_model_max_output_tokens("acme-capped") == 64000

    def test_catalog_load_failure_uses_default_context(self):
        with patch.object(ModelFactory, "load_config", side_effect=RuntimeError):
            # 15% of the 128k fallback context.
            assert cp_config.get_model_max_output_tokens(MODEL) == 19200

    def test_universally_supported_setting(self, catalog):
        assert cp_config.model_supports_setting(MODEL, "max_output_tokens", catalog)


class TestMakeModelSettingsMaxTokens:
    def test_explicit_arg_wins_over_everything(self, catalog):
        cp_config.set_model_setting("acme-capped", "max_output_tokens", 8192)
        with patch.object(ModelFactory, "load_config", return_value=catalog):
            settings = make_model_settings("acme-capped", max_tokens=1234)
        assert settings["max_tokens"] == 1234

    def test_catalog_value_used_by_default(self, catalog):
        with patch.object(ModelFactory, "load_config", return_value=catalog):
            settings = make_model_settings("acme-capped")
        assert settings["max_tokens"] == 64000

    def test_per_model_override_used(self, catalog):
        cp_config.set_model_setting("acme-capped", "max_output_tokens", 8192)
        with patch.object(ModelFactory, "load_config", return_value=catalog):
            settings = make_model_settings("acme-capped")
        assert settings["max_tokens"] == 8192

    def test_agent_override_beats_per_model(self, catalog):
        cp_config.set_model_setting("acme-capped", "max_output_tokens", 8192)
        with patch.object(ModelFactory, "load_config", return_value=catalog):
            settings = make_model_settings(
                "acme-capped", overrides={"max_output_tokens": 2048}
            )
        assert settings["max_tokens"] == 2048

    def test_raw_key_never_reaches_model_settings(self, catalog):
        cp_config.set_model_setting("acme-capped", "max_output_tokens", 8192)
        with patch.object(ModelFactory, "load_config", return_value=catalog):
            settings = make_model_settings(
                "acme-capped", overrides={"max_output_tokens": 2048}
            )
        assert "max_output_tokens" not in settings


OPUS5 = ModelInfo(
    provider_id="anthropic",
    model_id="claude-opus-5",
    name="Claude Opus 5",
    max_output=128000,
    context_length=1000000,
)


def _copilot_opus5() -> ModelInfo:
    """Same model id, half the output cap -- models.dev really disagrees."""
    return ModelInfo(
        provider_id="github-copilot",
        model_id="claude-opus-5",
        name="Claude Opus 5 (Copilot)",
        max_output=64000,
        context_length=1000000,
    )


def _install_registry(monkeypatch, *models) -> None:
    """Point the resolver at a fake registry holding ``models``."""
    registry = SimpleNamespace(get_models=lambda: list(models))
    monkeypatch.setattr(models_dev_parser, "get_registry", lambda: registry)


class TestModelsDevFallback:
    """Step 3 of the chain: models.dev, ahead of the 15% heuristic.

    Regression cover for the Terminal-Bench 2.1 finding. ``claude-opus-5`` uses
    adaptive thinking, so its reasoning shares the output budget; a guessed
    19200-token cap (15% of a fabricated 128k context) starved it mid-thought
    until pydantic-ai hard-failed with no tool call ever emitted.
    """

    ENTRY = {"type": "custom_anthropic", "name": "claude-opus-5"}

    def test_real_cap_replaces_the_starvation_heuristic(self, monkeypatch):
        _install_registry(monkeypatch, OPUS5)
        cfg = {"anthropic/claude-opus-5": self.ENTRY}
        assert (
            cp_config.get_model_max_output_tokens("anthropic/claude-opus-5", cfg)
            == 128000
        )

    def test_without_models_dev_the_heuristic_still_starves(self):
        """Documents the pre-fix behaviour this fallback exists to prevent."""
        cfg = {"anthropic/claude-opus-5": self.ENTRY}
        assert (
            cp_config.get_model_max_output_tokens("anthropic/claude-opus-5", cfg)
            == 19200
        )

    def test_provider_scoped_match_wins_over_disagreeing_providers(self, monkeypatch):
        _install_registry(monkeypatch, OPUS5, _copilot_opus5())
        cfg = {"anthropic/claude-opus-5": self.ENTRY}
        assert (
            cp_config.get_model_max_output_tokens("anthropic/claude-opus-5", cfg)
            == 128000
        )

    def test_name_only_match_refuses_to_pick_a_side(self, monkeypatch):
        _install_registry(monkeypatch, OPUS5, _copilot_opus5())
        # No provider prefix -> no provider-scoped key, and the providers split.
        cfg = {"my-opus": self.ENTRY}
        assert cp_config.get_model_max_output_tokens("my-opus", cfg) == 19200

    def test_unanimous_name_only_match_is_accepted(self, monkeypatch):
        twins = [
            ModelInfo(
                provider_id=provider,
                model_id="acme-7b",
                name="Acme 7B",
                max_output=8192,
                context_length=32000,
            )
            for provider in ("one", "two")
        ]
        _install_registry(monkeypatch, *twins)
        cfg = {"acme": {"name": "acme-7b", "context_length": 32000}}
        assert cp_config.get_model_max_output_tokens("acme", cfg) == 8192

    def test_unknown_model_falls_through(self, monkeypatch):
        _install_registry(monkeypatch, OPUS5)
        cfg = {"nobody-home": {"name": "unknown-9000", "context_length": 200000}}
        assert cp_config.get_model_max_output_tokens("nobody-home", cfg) == 30000

    def test_registry_failure_falls_through(self, monkeypatch):
        def boom():
            raise RuntimeError("offline")

        monkeypatch.setattr(models_dev_parser, "get_registry", boom)
        cfg = {"nobody-home": {"name": "unknown-9000", "context_length": 200000}}
        assert cp_config.get_model_max_output_tokens("nobody-home", cfg) == 30000

    def test_entry_without_a_name_is_skipped(self, monkeypatch):
        _install_registry(monkeypatch, OPUS5)
        cfg = {"anonymous": {"type": "custom_openai", "context_length": 200000}}
        assert cp_config.get_model_max_output_tokens("anonymous", cfg) == 30000

    def test_catalog_value_still_beats_models_dev(self, monkeypatch):
        _install_registry(monkeypatch, OPUS5)
        cfg = {"explicit": {"name": "claude-opus-5", "max_output_tokens": 4096}}
        assert cp_config.get_model_max_output_tokens("explicit", cfg) == 4096

    def test_user_override_still_beats_models_dev(self, monkeypatch):
        _install_registry(monkeypatch, OPUS5)
        cp_config.set_model_setting(
            "anthropic/claude-opus-5", "max_output_tokens", 2048
        )
        cfg = {"anthropic/claude-opus-5": self.ENTRY}
        assert (
            cp_config.get_model_max_output_tokens("anthropic/claude-opus-5", cfg)
            == 2048
        )


class TestExtraModelKeyRelocation:
    """The key builder now lives beside the models.dev index it describes."""

    def test_add_model_menu_still_exports_it(self):
        from code_puppy.command_line.add_model_menu import extra_model_key
        from code_puppy.models_dev_parser import extra_model_key as canonical

        assert extra_model_key is canonical

    def test_key_shape_is_unchanged(self):
        assert (
            models_dev_parser.extra_model_key("anthropic", "claude-opus-5")
            == "anthropic-claude-opus-5"
        )
