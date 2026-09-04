"""Tests for the configurable output-token cap (``max_output_tokens``).

Covers the resolution chain in ``config.get_model_max_output_tokens``
(per-model override > catalog entry > heuristic) and its integration into
``make_model_settings`` -- including that the raw key never leaks into the
provider-bound ModelSettings.
"""

from unittest.mock import patch

import pytest

import code_puppy.config as cp_config
from code_puppy.model_factory import ModelFactory, make_model_settings

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
