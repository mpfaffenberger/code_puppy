"""Full coverage tests for code_puppy/config.py.

Targets all uncovered lines from existing test suites.
"""

import configparser
import json
import os
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from code_puppy import config as cp_config


# ---------------------------------------------------------------------------
# _get_xdg_dir
# ---------------------------------------------------------------------------
class TestGetXdgDir:
    def test_returns_xdg_path_when_env_set(self, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
        result = cp_config._get_xdg_dir("XDG_CONFIG_HOME", ".config")
        assert result == "/custom/config/code_puppy"

    def test_returns_legacy_path_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = cp_config._get_xdg_dir("XDG_CONFIG_HOME", ".config")
        assert result == os.path.join(os.path.expanduser("~"), ".code_puppy")


# ---------------------------------------------------------------------------
# Boolean config getters
# ---------------------------------------------------------------------------
class TestBooleanGetters:
    def test_get_use_dbos_default_true(self):
        """enable_dbos defaults to True when not set."""
        assert cp_config.get_use_dbos() is True

    def test_get_use_dbos_false(self):
        cp_config.set_config_value("enable_dbos", "false")
        assert cp_config.get_use_dbos() is False

    def test_get_subagent_verbose_default_false(self):
        assert cp_config.get_subagent_verbose() is False

    def test_get_subagent_verbose_true(self):
        cp_config.set_config_value("subagent_verbose", "true")
        assert cp_config.get_subagent_verbose() is True

    def test_get_pack_agents_enabled_false(self):
        cp_config.set_config_value("enable_pack_agents", "false")
        assert cp_config.get_pack_agents_enabled() is False

    def test_get_pack_agents_enabled_true(self):
        cp_config.set_config_value("enable_pack_agents", "on")
        assert cp_config.get_pack_agents_enabled() is True

    def test_get_universal_constructor_enabled_default_true(self):
        assert cp_config.get_universal_constructor_enabled() is True

    def test_get_universal_constructor_enabled_false(self):
        cp_config.set_config_value("enable_universal_constructor", "false")
        assert cp_config.get_universal_constructor_enabled() is False

    def test_set_universal_constructor_enabled(self):
        cp_config.set_universal_constructor_enabled(False)
        assert cp_config.get_universal_constructor_enabled() is False
        cp_config.set_universal_constructor_enabled(True)
        assert cp_config.get_universal_constructor_enabled() is True

    def test_get_enable_streaming_default_true(self):
        assert cp_config.get_enable_streaming() is True

    def test_get_enable_streaming_false(self):
        cp_config.set_config_value("enable_streaming", "false")
        assert cp_config.get_enable_streaming() is False

    def test_get_yolo_mode_default_true(self):
        # yolo_mode defaults to True
        cp_config.reset_value("yolo_mode")
        assert cp_config.get_yolo_mode() is True

    def test_get_yolo_mode_off(self):
        cp_config.set_config_value("yolo_mode", "off")
        assert cp_config.get_yolo_mode() is False

    def test_get_mcp_disabled_default_false(self):
        assert cp_config.get_mcp_disabled() is False

    def test_get_mcp_disabled_true(self):
        cp_config.set_config_value("disable_mcp", "yes")
        assert cp_config.get_mcp_disabled() is True

    def test_get_grep_output_verbose_default_false(self):
        assert cp_config.get_grep_output_verbose() is False

    def test_get_grep_output_verbose_true(self):
        cp_config.set_config_value("grep_output_verbose", "1")
        assert cp_config.get_grep_output_verbose() is True

    def test_get_http2_values(self):
        cp_config.set_http2(True)
        assert cp_config.get_http2() is True
        cp_config.set_http2(False)
        assert cp_config.get_http2() is False

    def test_get_suppress_thinking_default_false(self):
        assert cp_config.get_suppress_thinking_messages() is False

    def test_set_suppress_thinking(self):
        cp_config.set_suppress_thinking_messages(True)
        assert cp_config.get_suppress_thinking_messages() is True

    def test_get_suppress_informational_default_false(self):
        assert cp_config.get_suppress_informational_messages() is False

    def test_set_suppress_informational(self):
        cp_config.set_suppress_informational_messages(True)
        assert cp_config.get_suppress_informational_messages() is True

    def test_get_auto_save_session_default_true(self):
        cp_config.reset_value("auto_save_session")
        assert cp_config.get_auto_save_session() is True

    def test_set_auto_save_session(self):
        cp_config.set_auto_save_session(False)
        assert cp_config.get_auto_save_session() is False

    def test_get_frontend_emitter_enabled_default(self):
        assert cp_config.get_frontend_emitter_enabled() is True

    def test_get_frontend_emitter_enabled_false(self):
        cp_config.set_config_value("frontend_emitter_enabled", "false")
        assert cp_config.get_frontend_emitter_enabled() is False


# ---------------------------------------------------------------------------
# Safety permission level
# ---------------------------------------------------------------------------
class TestSafetyPermissionLevel:
    def test_default_medium(self):
        assert cp_config.get_safety_permission_level() == "medium"

    def test_valid_levels(self):
        for level in ["none", "low", "medium", "high", "critical"]:
            cp_config.set_config_value("safety_permission_level", level)
            assert cp_config.get_safety_permission_level() == level

    def test_invalid_falls_back_to_medium(self):
        cp_config.set_config_value("safety_permission_level", "invalid")
        assert cp_config.get_safety_permission_level() == "medium"


# ---------------------------------------------------------------------------
# Numeric config getters
# ---------------------------------------------------------------------------
class TestNumericGetters:
    def test_get_protected_token_count_default(self):
        result = cp_config.get_protected_token_count()
        assert isinstance(result, int)
        assert result >= 1000

    def test_get_protected_token_count_custom(self):
        cp_config.set_config_value("protected_token_count", "10000")
        result = cp_config.get_protected_token_count()
        assert result == 10000

    def test_get_protected_token_count_invalid(self):
        cp_config.set_config_value("protected_token_count", "not_a_number")
        result = cp_config.get_protected_token_count()
        assert isinstance(result, int)

    def test_get_resume_message_count_default(self):
        assert cp_config.get_resume_message_count() == 50

    def test_get_resume_message_count_custom(self):
        cp_config.set_config_value("resume_message_count", "30")
        assert cp_config.get_resume_message_count() == 30

    def test_get_resume_message_count_clamped(self):
        cp_config.set_config_value("resume_message_count", "999")
        assert cp_config.get_resume_message_count() == 100

    def test_get_resume_message_count_invalid(self):
        cp_config.set_config_value("resume_message_count", "bad")
        assert cp_config.get_resume_message_count() == 50

    def test_get_compaction_threshold_default(self):
        assert cp_config.get_compaction_threshold() == 0.85

    def test_get_compaction_threshold_custom(self):
        cp_config.set_config_value("compaction_threshold", "0.7")
        assert cp_config.get_compaction_threshold() == 0.7

    def test_get_compaction_threshold_clamped_low(self):
        cp_config.set_config_value("compaction_threshold", "0.1")
        assert cp_config.get_compaction_threshold() == 0.5

    def test_get_compaction_threshold_invalid(self):
        cp_config.set_config_value("compaction_threshold", "xyz")
        assert cp_config.get_compaction_threshold() == 0.85

    def test_get_compaction_strategy_default(self):
        assert cp_config.get_compaction_strategy() in ["summarization", "truncation"]

    def test_get_compaction_strategy_values(self):
        cp_config.set_config_value("compaction_strategy", "summarization")
        assert cp_config.get_compaction_strategy() == "summarization"
        cp_config.set_config_value("compaction_strategy", "truncation")
        assert cp_config.get_compaction_strategy() == "truncation"

    def test_get_compaction_strategy_invalid(self):
        cp_config.set_config_value("compaction_strategy", "invalid")
        assert cp_config.get_compaction_strategy() == "truncation"

    def test_get_message_limit_default(self):
        cp_config.reset_value("message_limit")
        assert cp_config.get_message_limit() == 1000

    def test_get_message_limit_custom(self):
        cp_config.set_config_value("message_limit", "500")
        assert cp_config.get_message_limit() == 500

    def test_get_message_limit_invalid(self):
        cp_config.set_config_value("message_limit", "bad")
        assert cp_config.get_message_limit() == 1000

    def test_get_message_limit_custom_default(self):
        cp_config.reset_value("message_limit")
        assert cp_config.get_message_limit(default=50) == 50

    def test_get_diff_context_lines_default(self):
        cp_config.reset_value("diff_context_lines")
        assert cp_config.get_diff_context_lines() == 6

    def test_get_diff_context_lines_custom(self):
        cp_config.set_config_value("diff_context_lines", "10")
        assert cp_config.get_diff_context_lines() == 10

    def test_get_diff_context_lines_clamped(self):
        cp_config.set_config_value("diff_context_lines", "100")
        assert cp_config.get_diff_context_lines() == 50

    def test_get_diff_context_lines_invalid(self):
        cp_config.set_config_value("diff_context_lines", "bad")
        assert cp_config.get_diff_context_lines() == 6

    def test_get_max_saved_sessions_default(self):
        assert cp_config.get_max_saved_sessions() == 20

    def test_get_max_saved_sessions_custom(self):
        cp_config.set_config_value("max_saved_sessions", "50")
        assert cp_config.get_max_saved_sessions() == 50

    def test_set_max_saved_sessions(self):
        cp_config.set_max_saved_sessions(10)
        assert cp_config.get_max_saved_sessions() == 10

    def test_get_max_saved_sessions_invalid(self):
        cp_config.set_config_value("max_saved_sessions", "bad")
        assert cp_config.get_max_saved_sessions() == 20

    def test_get_frontend_emitter_max_recent_events_default(self):
        assert cp_config.get_frontend_emitter_max_recent_events() == 100

    def test_get_frontend_emitter_max_recent_events_invalid(self):
        cp_config.set_config_value("frontend_emitter_max_recent_events", "bad")
        assert cp_config.get_frontend_emitter_max_recent_events() == 100

    def test_get_frontend_emitter_queue_size_default(self):
        assert cp_config.get_frontend_emitter_queue_size() == 100

    def test_get_frontend_emitter_queue_size_invalid(self):
        cp_config.set_config_value("frontend_emitter_queue_size", "bad")
        assert cp_config.get_frontend_emitter_queue_size() == 100


# ---------------------------------------------------------------------------
# Temperature
# ---------------------------------------------------------------------------
class TestTemperature:
    def test_get_temperature_none(self):
        cp_config.reset_value("temperature")
        assert cp_config.get_temperature() is None

    def test_get_temperature_empty(self):
        cp_config.set_config_value("temperature", "")
        assert cp_config.get_temperature() is None

    def test_get_temperature_valid(self):
        cp_config.set_config_value("temperature", "0.7")
        assert cp_config.get_temperature() == 0.7

    def test_get_temperature_clamped_high(self):
        cp_config.set_config_value("temperature", "5.0")
        assert cp_config.get_temperature() == 2.0

    def test_get_temperature_clamped_low(self):
        cp_config.set_config_value("temperature", "-1.0")
        assert cp_config.get_temperature() == 0.0

    def test_get_temperature_invalid(self):
        cp_config.set_config_value("temperature", "bad")
        assert cp_config.get_temperature() is None

    def test_set_temperature_none(self):
        cp_config.set_temperature(None)
        assert cp_config.get_temperature() is None

    def test_set_temperature_value(self):
        cp_config.set_temperature(1.5)
        assert cp_config.get_temperature() == 1.5


# ---------------------------------------------------------------------------
# OpenAI reasoning / verbosity
# ---------------------------------------------------------------------------
class TestOpenAISettings:
    def test_get_openai_reasoning_effort_default(self):
        cp_config.reset_value("openai_reasoning_effort")
        assert cp_config.get_openai_reasoning_effort() == "medium"

    def test_get_openai_reasoning_effort_invalid(self):
        cp_config.set_config_value("openai_reasoning_effort", "bogus")
        assert cp_config.get_openai_reasoning_effort() == "medium"

    def test_set_openai_reasoning_effort_valid(self):
        cp_config.set_openai_reasoning_effort("high")
        assert cp_config.get_openai_reasoning_effort() == "high"

    def test_set_openai_reasoning_effort_invalid(self):
        with pytest.raises(ValueError):
            cp_config.set_openai_reasoning_effort("bogus")

    def test_get_openai_verbosity_default(self):
        cp_config.reset_value("openai_verbosity")
        assert cp_config.get_openai_verbosity() == "medium"

    def test_get_openai_verbosity_invalid(self):
        cp_config.set_config_value("openai_verbosity", "bogus")
        assert cp_config.get_openai_verbosity() == "medium"

    def test_set_openai_verbosity_valid(self):
        cp_config.set_openai_verbosity("low")
        assert cp_config.get_openai_verbosity() == "low"

    def test_set_openai_verbosity_invalid(self):
        with pytest.raises(ValueError):
            cp_config.set_openai_verbosity("bogus")


# ---------------------------------------------------------------------------
# Per-model settings
# ---------------------------------------------------------------------------
class TestPerModelSettings:
    def test_sanitize_model_name(self):
        assert cp_config._sanitize_model_name_for_key("gpt-4.1") == "gpt_4_1"
        assert cp_config._sanitize_model_name_for_key("a/b") == "a_b"

    def test_get_set_model_setting(self):
        cp_config.set_model_setting("test-model", "temperature", 0.5)
        val = cp_config.get_model_setting("test-model", "temperature")
        assert val == 0.5

    def test_get_model_setting_default(self):
        val = cp_config.get_model_setting("nonexistent", "seed", default=42.0)
        assert val == 42.0

    def test_set_model_setting_none_clears(self):
        cp_config.set_model_setting("test-model", "seed", 123)
        cp_config.set_model_setting("test-model", "seed", None)
        assert cp_config.get_model_setting("test-model", "seed") is None

    def test_set_model_setting_int(self):
        cp_config.set_model_setting("test-model", "seed", 42)  # int, not float
        val = cp_config.get_model_setting("test-model", "seed")
        assert val == 42.0

    def test_get_model_setting_invalid_value(self):
        cp_config.set_config_value("model_settings_test_model_seed", "bad")
        val = cp_config.get_model_setting("test-model", "seed", default=99.0)
        assert val == 99.0

    def test_get_all_model_settings(self):
        cp_config.set_model_setting("all-test", "temperature", 0.8)
        cp_config.set_model_setting("all-test", "seed", 42)
        settings = cp_config.get_all_model_settings("all-test")
        assert "temperature" in settings

    def test_get_all_model_settings_boolean(self):
        cp_config.set_config_value("model_settings_bool_test_extended_thinking", "true")
        settings = cp_config.get_all_model_settings("bool-test")
        assert settings.get("extended_thinking") is True

    def test_get_all_model_settings_string(self):
        cp_config.set_config_value("model_settings_str_test_foo", "bar")
        settings = cp_config.get_all_model_settings("str-test")
        assert settings.get("foo") == "bar"

    def test_clear_model_settings(self):
        cp_config.set_model_setting("clear-test", "temperature", 0.5)
        cp_config.clear_model_settings("clear-test")
        settings = cp_config.get_all_model_settings("clear-test")
        assert len(settings) == 0

    def test_get_effective_model_settings_with_global_fallback(self):
        cp_config.set_temperature(0.9)
        cp_config.clear_model_settings("fallback-test")
        with patch.object(
            cp_config, "get_global_model_name", return_value="fallback-test"
        ):
            with patch.object(cp_config, "model_supports_setting", return_value=True):
                settings = cp_config.get_effective_model_settings("fallback-test")
                assert settings.get("temperature") == 0.9

    def test_get_effective_model_settings_seed_converted_to_int(self):
        cp_config.set_model_setting("seed-test", "seed", 42)
        with patch.object(cp_config, "model_supports_setting", return_value=True):
            settings = cp_config.get_effective_model_settings("seed-test")
            assert isinstance(settings.get("seed"), int)

    def test_get_effective_model_settings_none_uses_global(self):
        with patch.object(cp_config, "get_global_model_name", return_value="test"):
            with patch.object(cp_config, "model_supports_setting", return_value=True):
                settings = cp_config.get_effective_model_settings(None)
                assert isinstance(settings, dict)

    def test_get_effective_temperature(self):
        cp_config.set_model_setting("eff-temp", "temperature", 0.3)
        with patch.object(cp_config, "model_supports_setting", return_value=True):
            val = cp_config.get_effective_temperature("eff-temp")
            assert val == 0.3

    def test_get_effective_top_p(self):
        with patch.object(cp_config, "model_supports_setting", return_value=True):
            val = cp_config.get_effective_top_p("no-top-p")
            assert val is None

    def test_get_effective_seed(self):
        with patch.object(cp_config, "model_supports_setting", return_value=True):
            val = cp_config.get_effective_seed("no-seed")
            assert val is None


# ---------------------------------------------------------------------------
# model_supports_setting
# ---------------------------------------------------------------------------
class TestModelSupportsSetting:
    def test_glm_clear_thinking(self):
        assert (
            cp_config.model_supports_setting("glm-4.7-chat", "clear_thinking") is True
        )
        assert cp_config.model_supports_setting("GLM-5-large", "clear_thinking") is True

    def test_with_supported_settings_list(self):
        mock_config = {"test-model": {"supported_settings": ["temperature", "seed"]}}
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value=mock_config,
        ):
            assert cp_config.model_supports_setting("test-model", "temperature") is True
            assert cp_config.model_supports_setting("test-model", "top_p") is False

    def test_claude_default_settings(self):
        mock_config = {"claude-test": {}}
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value=mock_config,
        ):
            assert (
                cp_config.model_supports_setting("claude-test", "temperature") is True
            )
            assert (
                cp_config.model_supports_setting("claude-test", "extended_thinking")
                is True
            )

    def test_claude_opus_4_6_effort(self):
        mock_config = {"claude-opus-4-6": {}}
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value=mock_config,
        ):
            assert cp_config.model_supports_setting("claude-opus-4-6", "effort") is True

    def test_generic_model_defaults(self):
        mock_config = {"generic": {}}
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value=mock_config,
        ):
            assert cp_config.model_supports_setting("generic", "temperature") is True
            assert cp_config.model_supports_setting("generic", "seed") is True
            assert cp_config.model_supports_setting("generic", "top_p") is False

    def test_exception_returns_true(self):
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config", side_effect=Exception
        ):
            assert cp_config.model_supports_setting("any", "any") is True


# ---------------------------------------------------------------------------
# Model name management
# ---------------------------------------------------------------------------
class TestModelName:
    def test_get_global_model_name_from_session(self):
        cp_config._SESSION_MODEL = "cached-model"
        assert cp_config.get_global_model_name() == "cached-model"
        cp_config._SESSION_MODEL = None

    def test_get_global_model_name_from_config(self):
        cp_config._SESSION_MODEL = None
        cp_config.set_config_value("model", "my-model")
        with patch.object(cp_config, "_validate_model_exists", return_value=True):
            result = cp_config.get_global_model_name()
            assert result == "my-model"
        cp_config._SESSION_MODEL = None

    def test_get_global_model_name_invalid_stored(self):
        cp_config._SESSION_MODEL = None
        cp_config.set_config_value("model", "bad-model")
        with patch.object(cp_config, "_validate_model_exists", return_value=False):
            with patch.object(
                cp_config, "_default_model_from_models_json", return_value="default-m"
            ):
                result = cp_config.get_global_model_name()
                assert result == "default-m"
        cp_config._SESSION_MODEL = None

    def test_set_model_name(self):
        cp_config.set_model_name("new-model")
        assert cp_config._SESSION_MODEL == "new-model"
        cp_config._SESSION_MODEL = None

    def test_reset_session_model(self):
        cp_config._SESSION_MODEL = "foo"
        cp_config.reset_session_model()
        assert cp_config._SESSION_MODEL is None


# ---------------------------------------------------------------------------
# Default model from models.json
# ---------------------------------------------------------------------------
class TestDefaultModel:
    def test_default_model_cached(self):
        cp_config._default_model_cache = "cached"
        assert cp_config._default_model_from_models_json() == "cached"
        cp_config._default_model_cache = None

    def test_default_model_from_config(self):
        cp_config._default_model_cache = None
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"first": {}, "second": {}},
        ):
            result = cp_config._default_model_from_models_json()
            assert result == "first"
        cp_config._default_model_cache = None

    def test_default_model_empty_config(self):
        cp_config._default_model_cache = None
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config", return_value={}
        ):
            result = cp_config._default_model_from_models_json()
            assert result == "gpt-5"
        cp_config._default_model_cache = None

    def test_default_model_exception(self):
        cp_config._default_model_cache = None
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config", side_effect=Exception
        ):
            result = cp_config._default_model_from_models_json()
            assert result == "gpt-5"
        cp_config._default_model_cache = None


# ---------------------------------------------------------------------------
# Default vision model
# ---------------------------------------------------------------------------
class TestDefaultVisionModel:
    def test_cached(self):
        cp_config._default_vision_model_cache = "cached-vision"
        assert cp_config._default_vision_model_from_models_json() == "cached-vision"
        cp_config._default_vision_model_cache = None

    def test_supports_vision_tag(self):
        cp_config._default_vision_model_cache = None
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"model-a": {"supports_vision": True}},
        ):
            assert cp_config._default_vision_model_from_models_json() == "model-a"
        cp_config._default_vision_model_cache = None

    def test_preferred_candidates(self):
        cp_config._default_vision_model_cache = None
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"gpt-4.1": {}, "other": {}},
        ):
            assert cp_config._default_vision_model_from_models_json() == "gpt-4.1"
        cp_config._default_vision_model_cache = None

    def test_fallback_to_general_default(self):
        cp_config._default_vision_model_cache = None
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"some-model": {}},
        ):
            with patch.object(
                cp_config, "_default_model_from_models_json", return_value="some-model"
            ):
                assert (
                    cp_config._default_vision_model_from_models_json() == "some-model"
                )
        cp_config._default_vision_model_cache = None

    def test_empty_config(self):
        cp_config._default_vision_model_cache = None
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config", return_value={}
        ):
            assert cp_config._default_vision_model_from_models_json() == "gpt-4.1"
        cp_config._default_vision_model_cache = None

    def test_exception(self):
        cp_config._default_vision_model_cache = None
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config", side_effect=Exception
        ):
            assert cp_config._default_vision_model_from_models_json() == "gpt-4.1"
        cp_config._default_vision_model_cache = None


# ---------------------------------------------------------------------------
# Validate model exists
# ---------------------------------------------------------------------------
class TestValidateModel:
    def test_cached_true(self):
        cp_config._model_validation_cache["cached-m"] = True
        assert cp_config._validate_model_exists("cached-m") is True
        del cp_config._model_validation_cache["cached-m"]

    def test_found(self):
        cp_config._model_validation_cache.clear()
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config", return_value={"m": {}}
        ):
            assert cp_config._validate_model_exists("m") is True

    def test_not_found(self):
        cp_config._model_validation_cache.clear()
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config", return_value={}
        ):
            assert cp_config._validate_model_exists("missing") is False

    def test_exception(self):
        cp_config._model_validation_cache.clear()
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config", side_effect=Exception
        ):
            assert cp_config._validate_model_exists("any") is True


# ---------------------------------------------------------------------------
# Model context length
# ---------------------------------------------------------------------------
class TestModelContextLength:
    def test_from_config(self):
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"m": {"context_length": 32000}},
        ):
            with patch.object(cp_config, "get_global_model_name", return_value="m"):
                assert cp_config.get_model_context_length() == 32000

    def test_default(self):
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config", return_value={}
        ):
            with patch.object(cp_config, "get_global_model_name", return_value="m"):
                assert cp_config.get_model_context_length() == 128000

    def test_exception(self):
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config", side_effect=Exception
        ):
            assert cp_config.get_model_context_length() == 128000


# ---------------------------------------------------------------------------
# MCP server configs
# ---------------------------------------------------------------------------
class TestMCPServerConfigs:
    def test_no_file(self):
        with patch.object(pathlib.Path, "exists", return_value=False):
            assert cp_config.load_mcp_server_configs() == {}

    def test_valid_file(self, tmp_path):
        f = tmp_path / "mcp_servers.json"
        f.write_text(json.dumps({"mcp_servers": {"s1": "http://localhost"}}))
        with patch.object(cp_config, "MCP_SERVERS_FILE", str(f)):
            result = cp_config.load_mcp_server_configs()
            assert result == {"s1": "http://localhost"}

    def test_bad_json(self, tmp_path):
        f = tmp_path / "mcp_servers.json"
        f.write_text("not json")
        with patch.object(cp_config, "MCP_SERVERS_FILE", str(f)):
            with patch("code_puppy.messaging.message_queue.emit_error"):
                result = cp_config.load_mcp_server_configs()
                assert result == {}


# ---------------------------------------------------------------------------
# Config keys
# ---------------------------------------------------------------------------
class TestConfigKeys:
    def test_get_config_keys_returns_sorted_list(self):
        keys = cp_config.get_config_keys()
        assert isinstance(keys, list)
        assert keys == sorted(keys)
        assert "yolo_mode" in keys
        assert "compaction_strategy" in keys
        assert "enable_dbos" in keys
        assert "enable_streaming" in keys
        assert "cancel_agent_key" in keys
        assert "resume_message_count" in keys


# ---------------------------------------------------------------------------
# set_config_value / reset_value
# ---------------------------------------------------------------------------
class TestSetResetValue:
    def test_set_and_get(self):
        cp_config.set_config_value("test_key", "test_value")
        assert cp_config.get_value("test_key") == "test_value"

    def test_set_value_alias(self):
        cp_config.set_value("alias_key", "alias_val")
        assert cp_config.get_value("alias_key") == "alias_val"

    def test_reset_value(self):
        cp_config.set_config_value("reset_me", "val")
        cp_config.reset_value("reset_me")
        assert cp_config.get_value("reset_me") is None

    def test_reset_nonexistent(self):
        # Should not raise
        cp_config.reset_value("does_not_exist_xyz")


# ---------------------------------------------------------------------------
# Agent pinned models
# ---------------------------------------------------------------------------
class TestAgentPinnedModels:
    def test_set_get_clear(self):
        cp_config.set_agent_pinned_model("test-agent", "my-model")
        assert cp_config.get_agent_pinned_model("test-agent") == "my-model"
        cp_config.clear_agent_pinned_model("test-agent")
        # empty string is treated as falsy but returned by get_value
        assert not cp_config.get_agent_pinned_model("test-agent")

    def test_get_all_agent_pinned_models(self):
        cp_config.set_agent_pinned_model("a1", "m1")
        cp_config.set_agent_pinned_model("a2", "m2")
        pinnings = cp_config.get_all_agent_pinned_models()
        assert pinnings.get("a1") == "m1"
        assert pinnings.get("a2") == "m2"

    def test_get_agents_pinned_to_model(self):
        cp_config.set_agent_pinned_model("pa1", "target")
        cp_config.set_agent_pinned_model("pa2", "other")
        result = cp_config.get_agents_pinned_to_model("target")
        assert "pa1" in result
        assert "pa2" not in result


# ---------------------------------------------------------------------------
# Puppy token
# ---------------------------------------------------------------------------
class TestPuppyToken:
    def test_get_set(self):
        cp_config.set_puppy_token("tok123")
        assert cp_config.get_puppy_token() == "tok123"


# ---------------------------------------------------------------------------
# Diff colors
# ---------------------------------------------------------------------------
class TestDiffColors:
    def test_default_addition_color(self):
        cp_config.reset_value("highlight_addition_color")
        assert cp_config.get_diff_addition_color() == "#0b1f0b"

    def test_set_addition_color(self):
        cp_config.set_diff_addition_color("green")
        assert cp_config.get_diff_addition_color() == "green"

    def test_default_deletion_color(self):
        cp_config.reset_value("highlight_deletion_color")
        assert cp_config.get_diff_deletion_color() == "#390e1a"

    def test_set_deletion_color(self):
        cp_config.set_diff_deletion_color("red")
        assert cp_config.get_diff_deletion_color() == "red"

    def test_set_diff_highlight_style_noop(self):
        # Should not raise
        cp_config.set_diff_highlight_style("anything")


# ---------------------------------------------------------------------------
# Banner colors
# ---------------------------------------------------------------------------
class TestBannerColors:
    def test_get_default(self):
        cp_config.reset_value("banner_color_thinking")
        color = cp_config.get_banner_color("thinking")
        assert color == "deep_sky_blue4"

    def test_get_unknown_banner(self):
        assert cp_config.get_banner_color("nonexistent_banner") == "blue"

    def test_set_and_get(self):
        cp_config.set_banner_color("thinking", "red")
        assert cp_config.get_banner_color("thinking") == "red"

    def test_get_all(self):
        colors = cp_config.get_all_banner_colors()
        assert "thinking" in colors

    def test_reset_single(self):
        cp_config.set_banner_color("thinking", "custom")
        cp_config.reset_banner_color("thinking")
        # reset_banner_color sets to DEFAULT_BANNER_COLORS value
        assert (
            cp_config.get_banner_color("thinking")
            == cp_config.DEFAULT_BANNER_COLORS["thinking"]
        )

    def test_reset_all(self):
        cp_config.set_banner_color("thinking", "custom")
        cp_config.reset_all_banner_colors()
        assert (
            cp_config.get_banner_color("thinking")
            == cp_config.DEFAULT_BANNER_COLORS["thinking"]
        )


# ---------------------------------------------------------------------------
# Autosave session management
# ---------------------------------------------------------------------------
class TestAutosaveSession:
    def test_get_current_autosave_id(self):
        cp_config._CURRENT_AUTOSAVE_ID = None
        aid = cp_config.get_current_autosave_id()
        assert aid is not None
        assert len(aid) > 0

    def test_rotate_autosave_id(self):
        import time

        cp_config.get_current_autosave_id()
        time.sleep(0.01)
        new = cp_config.rotate_autosave_id()
        # They could be the same within a second, but it should return a string
        assert isinstance(new, str)

    def test_get_current_autosave_session_name(self):
        name = cp_config.get_current_autosave_session_name()
        assert name.startswith("auto_session_")

    def test_set_from_session_name_with_prefix(self):
        result = cp_config.set_current_autosave_from_session_name(
            "auto_session_20250101_120000"
        )
        assert result == "20250101_120000"

    def test_set_from_session_name_without_prefix(self):
        result = cp_config.set_current_autosave_from_session_name("custom_id")
        assert result == "custom_id"

    def test_auto_save_session_if_enabled_disabled(self):
        cp_config.set_auto_save_session(False)
        assert cp_config.auto_save_session_if_enabled() is False

    def test_auto_save_session_if_enabled_no_history(self):
        cp_config.set_auto_save_session(True)
        mock_agent = MagicMock()
        mock_agent.get_message_history.return_value = []
        with patch(
            "code_puppy.agents.agent_manager.get_current_agent", return_value=mock_agent
        ):
            assert cp_config.auto_save_session_if_enabled() is False

    def test_auto_save_session_if_enabled_success(self):
        cp_config.set_auto_save_session(True)
        mock_agent = MagicMock()
        mock_agent.get_message_history.return_value = [
            {"role": "user", "content": "hi"}
        ]
        mock_metadata = MagicMock()
        mock_metadata.message_count = 1
        mock_metadata.total_tokens = 100
        with patch(
            "code_puppy.agents.agent_manager.get_current_agent", return_value=mock_agent
        ):
            with patch("code_puppy.config.save_session", return_value=mock_metadata):
                with patch("code_puppy.messaging.emit_info"):
                    assert cp_config.auto_save_session_if_enabled() is True

    def test_finalize_autosave_session(self):
        with patch.object(cp_config, "auto_save_session_if_enabled"):
            result = cp_config.finalize_autosave_session()
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Ensure config exists
# ---------------------------------------------------------------------------
class TestEnsureConfigExists:
    def test_creates_dirs_and_prompts(self, monkeypatch, tmp_path):
        cfg_dir = str(tmp_path / "config")
        cfg_file = os.path.join(cfg_dir, "puppy.cfg")
        monkeypatch.setattr(cp_config, "CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(cp_config, "CONFIG_FILE", cfg_file)
        monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setattr(cp_config, "CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setattr(cp_config, "STATE_DIR", str(tmp_path / "state"))

        inputs = iter(["TestPup", "TestOwner"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        config = cp_config.ensure_config_exists()
        assert config["puppy"]["puppy_name"] == "TestPup"
        assert config["puppy"]["owner_name"] == "TestOwner"
        assert os.path.exists(cfg_file)

    def test_existing_config_no_prompt(self, tmp_path, monkeypatch):
        cfg_dir = str(tmp_path)
        cfg_file = os.path.join(cfg_dir, "puppy.cfg")
        cp = configparser.ConfigParser()
        cp["puppy"] = {"puppy_name": "Buddy", "owner_name": "Alice"}
        with open(cfg_file, "w") as f:
            cp.write(f)

        monkeypatch.setattr(cp_config, "CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(cp_config, "CONFIG_FILE", cfg_file)
        monkeypatch.setattr(cp_config, "DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setattr(cp_config, "CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setattr(cp_config, "STATE_DIR", str(tmp_path / "state"))

        config = cp_config.ensure_config_exists()
        assert config["puppy"]["puppy_name"] == "Buddy"


# ---------------------------------------------------------------------------
# Command history
# ---------------------------------------------------------------------------
class TestCommandHistory:
    def test_save_command_to_history(self, tmp_path):
        hist_file = str(tmp_path / "history.txt")
        with patch.object(cp_config, "COMMAND_HISTORY_FILE", hist_file):
            cp_config.save_command_to_history("test command")
            content = open(hist_file).read()
            assert "test command" in content

    def test_save_command_error(self, tmp_path):
        with patch.object(
            cp_config, "COMMAND_HISTORY_FILE", "/nonexistent/dir/hist.txt"
        ):
            with patch("code_puppy.messaging.emit_error"):
                cp_config.save_command_to_history("test")  # Should not raise

    def test_initialize_command_history_file_new(self, tmp_path, monkeypatch):
        state_dir = str(tmp_path / "state")
        hist_file = os.path.join(state_dir, "history.txt")
        monkeypatch.setattr(cp_config, "STATE_DIR", state_dir)
        monkeypatch.setattr(cp_config, "COMMAND_HISTORY_FILE", hist_file)
        cp_config.initialize_command_history_file()
        assert os.path.exists(hist_file)

    def test_initialize_command_history_migration(self, tmp_path, monkeypatch):
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)
        hist_file = os.path.join(state_dir, "history.txt")
        old_file = os.path.join(str(tmp_path), ".code_puppy_history.txt")
        with open(old_file, "w") as f:
            f.write("old history")

        monkeypatch.setattr(cp_config, "STATE_DIR", state_dir)
        monkeypatch.setattr(cp_config, "COMMAND_HISTORY_FILE", hist_file)
        monkeypatch.setattr(os.path, "expanduser", lambda _: str(tmp_path))

        cp_config.initialize_command_history_file()
        assert os.path.exists(hist_file)
        assert open(hist_file).read() == "old history"


# ---------------------------------------------------------------------------
# User / project agents directories
# ---------------------------------------------------------------------------
class TestAgentsDirectories:
    def test_get_user_agents_directory(self):
        d = cp_config.get_user_agents_directory()
        assert os.path.isdir(d)

    def test_get_project_agents_directory_exists(self, tmp_path, monkeypatch):
        agents_dir = tmp_path / ".code_puppy" / "agents"
        agents_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        assert cp_config.get_project_agents_directory() is not None

    def test_get_project_agents_directory_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cp_config.get_project_agents_directory() is None


# ---------------------------------------------------------------------------
# Default agent
# ---------------------------------------------------------------------------
class TestDefaultAgent:
    def test_default(self):
        assert cp_config.get_default_agent() == "code-puppy"

    def test_set_and_get(self):
        cp_config.set_default_agent("custom-agent")
        assert cp_config.get_default_agent() == "custom-agent"


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
class TestAPIKeys:
    def test_get_set_api_key(self):
        cp_config.set_api_key("TEST_KEY", "secret")
        assert cp_config.get_api_key("TEST_KEY") == "secret"

    def test_get_api_key_not_set(self):
        assert cp_config.get_api_key("NONEXISTENT_KEY_XYZ") == ""

    def test_load_api_keys_to_environment(self, monkeypatch):
        cp_config.set_api_key("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cp_config.load_api_keys_to_environment()
        assert os.environ.get("OPENAI_API_KEY") == "test-key"

    def test_load_api_keys_env_has_priority(self, monkeypatch):
        cp_config.set_api_key("OPENAI_API_KEY", "from-config")
        monkeypatch.setenv("OPENAI_API_KEY", "from-env")
        cp_config.load_api_keys_to_environment()
        assert os.environ["OPENAI_API_KEY"] == "from-env"

    def test_load_api_keys_dotenv(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("OPENAI_API_KEY=from-dotenv\n")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        try:
            cp_config.load_api_keys_to_environment()
        except Exception:
            pass  # dotenv may not be installed


# ---------------------------------------------------------------------------
# Allow recursion
# ---------------------------------------------------------------------------
class TestAllowRecursion:
    def test_default_true(self):
        assert cp_config.get_allow_recursion() is True

    def test_false(self):
        cp_config.set_config_value("allow_recursion", "false")
        assert cp_config.get_allow_recursion() is False


# ---------------------------------------------------------------------------
# set_enable_dbos
# ---------------------------------------------------------------------------
class TestSetEnableDbos:
    def test_set(self):
        cp_config.set_enable_dbos(True)
        assert cp_config.get_use_dbos() is True
        cp_config.set_enable_dbos(False)
        assert cp_config.get_use_dbos() is False


# ---------------------------------------------------------------------------
# clear_model_cache
# ---------------------------------------------------------------------------
class TestClearModelCache:
    def test_clears_all(self):
        cp_config._model_validation_cache["x"] = True
        cp_config._default_model_cache = "y"
        cp_config._default_vision_model_cache = "z"
        cp_config.clear_model_cache()
        assert len(cp_config._model_validation_cache) == 0
        assert cp_config._default_model_cache is None
        assert cp_config._default_vision_model_cache is None
