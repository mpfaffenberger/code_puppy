"""Tests for user-defined custom model params (/model_settings -> Custom Params).

Covers the config-layer JSON blob storage, scalar parsing, the reserved-key
exclusion in get_all_model_settings, and the dotted-key extra_body merge in
make_model_settings.
"""

import json
from unittest.mock import patch

import pytest

import code_puppy.config as cp_config
from code_puppy.model_factory import _merge_dotted_key


class TestParseConfigScalar:
    """Tests for the shared scalar parser."""

    def test_parses_booleans_case_insensitive(self):
        assert cp_config.parse_config_scalar("true") is True
        assert cp_config.parse_config_scalar("False") is False

    def test_parses_int_before_float(self):
        assert cp_config.parse_config_scalar("42") == 42
        assert isinstance(cp_config.parse_config_scalar("42"), int)

    def test_parses_float(self):
        assert cp_config.parse_config_scalar("0.7") == 0.7

    def test_falls_back_to_string(self):
        assert cp_config.parse_config_scalar("medium") == "medium"

    def test_strips_whitespace(self):
        assert cp_config.parse_config_scalar("  high  ") == "high"


class TestGetCustomModelSettings:
    """Tests for reading the custom params JSON blob."""

    @pytest.mark.parametrize(
        "stored,expected",
        [
            (None, {}),
            ("   ", {}),
            (
                '{"chat_template_kwargs.thinking": "medium", "top_k": 5}',
                {"chat_template_kwargs.thinking": "medium", "top_k": 5},
            ),
            ("{not valid json", {}),
            ('["a", "list"]', {}),
        ],
    )
    @patch.object(cp_config, "get_value")
    def test_get_custom_model_settings(self, _mock, stored, expected):
        _mock.return_value = stored
        assert cp_config.get_custom_model_settings("test-model") == expected

    @patch.object(cp_config, "get_value")
    def test_uses_reserved_config_key(self, mock_get_value):
        mock_get_value.return_value = None
        cp_config.get_custom_model_settings("gpt-5.1")
        mock_get_value.assert_called_once_with("model_settings_gpt_5_1_custom")


class TestSetCustomModelSetting:
    """Tests for writing custom params."""

    @patch.object(cp_config, "set_config_value")
    @patch.object(cp_config, "get_value", return_value=None)
    def test_adds_new_key(self, _mock_get, mock_set):
        cp_config.set_custom_model_setting(
            "gpt-5", "chat_template_kwargs.thinking", "medium"
        )
        key, raw = mock_set.call_args[0]
        assert key == "model_settings_gpt_5_custom"
        assert json.loads(raw) == {"chat_template_kwargs.thinking": "medium"}

    @patch.object(cp_config, "set_config_value")
    @patch.object(cp_config, "get_value", return_value='{"a": 1, "b": 2}')
    def test_deletes_key_with_none(self, _mock_get, mock_set):
        cp_config.set_custom_model_setting("gpt-5", "a", None)
        _, raw = mock_set.call_args[0]
        assert json.loads(raw) == {"b": 2}

    @patch.object(cp_config, "set_config_value")
    @patch.object(cp_config, "get_value", return_value='{"a": 1}')
    def test_clears_config_entry_when_last_key_removed(self, _mock_get, mock_set):
        cp_config.set_custom_model_setting("gpt-5", "a", None)
        mock_set.assert_called_once_with("model_settings_gpt_5_custom", "")

    @patch.object(cp_config, "set_config_value")
    @patch.object(cp_config, "get_value", return_value=None)
    def test_ignores_empty_key(self, _mock_get, mock_set):
        cp_config.set_custom_model_setting("gpt-5", "   ", "value")
        mock_set.assert_not_called()


class TestCustomKeyExcludedFromScalarSettings:
    """The reserved 'custom' key must stay out of the generic namespace."""

    def test_get_all_model_settings_skips_custom_blob(self, tmp_path):
        cfg_file = tmp_path / "puppy.cfg"
        cfg_file.write_text(
            f"[{cp_config.DEFAULT_SECTION}]\n"
            "model_settings_test_model_temperature = 0.5\n"
            'model_settings_test_model_custom = {"top_k": 5}\n'
        )
        with patch.object(cp_config, "CONFIG_FILE", str(cfg_file)):
            settings = cp_config.get_all_model_settings("test-model")
        assert settings == {"temperature": 0.5}


class TestMergeDottedKey:
    """Tests for the dotted-key -> nested-dict expansion."""

    def test_flat_key(self):
        target = {}
        _merge_dotted_key(target, "top_k", 5)
        assert target == {"top_k": 5}

    def test_nested_key(self):
        target = {}
        _merge_dotted_key(target, "chat_template_kwargs.thinking", "medium")
        assert target == {"chat_template_kwargs": {"thinking": "medium"}}

    def test_merges_into_existing_nested_dict(self):
        target = {"chat_template_kwargs": {"enable_thinking": True}}
        _merge_dotted_key(target, "chat_template_kwargs.thinking", "medium")
        assert target == {
            "chat_template_kwargs": {"enable_thinking": True, "thinking": "medium"}
        }

    def test_replaces_non_dict_intermediate(self):
        target = {"thinking": "enabled"}
        _merge_dotted_key(target, "thinking.type", "disabled")
        assert target == {"thinking": {"type": "disabled"}}

    def test_ignores_empty_key(self):
        target = {"a": 1}
        _merge_dotted_key(target, "", "value")
        _merge_dotted_key(target, "...", "value")
        assert target == {"a": 1}


class TestMakeModelSettingsCustomParams:
    """Custom params must land in extra_body, applied last so they win."""

    def test_custom_params_merged_into_extra_body(self):
        from code_puppy.model_factory import make_model_settings

        with patch(
            "code_puppy.config.get_custom_model_settings",
            return_value={"chat_template_kwargs.thinking": "medium", "top_k": 5},
        ):
            settings = make_model_settings("some-model", max_tokens=4096)

        assert settings["extra_body"]["chat_template_kwargs"] == {"thinking": "medium"}
        assert settings["extra_body"]["top_k"] == 5

    def test_custom_params_override_built_in_extra_body(self):
        """GLM models set extra_body.thinking themselves; custom wins."""
        from code_puppy.model_factory import make_model_settings

        with patch(
            "code_puppy.config.get_custom_model_settings",
            return_value={"thinking.type": "disabled"},
        ):
            settings = make_model_settings("zai-glm-5.1-api", max_tokens=4096)

        assert settings["extra_body"]["thinking"]["type"] == "disabled"
        # Sibling keys from the built-in payload survive the merge.
        assert settings["extra_body"]["thinking"]["clear_thinking"] is False

    def test_no_custom_params_leaves_extra_body_untouched(self):
        from code_puppy.model_factory import make_model_settings

        with patch(
            "code_puppy.config.get_custom_model_settings",
            return_value={},
        ):
            settings = make_model_settings("some-model", max_tokens=4096)

        assert settings.get("extra_body") is None


class TestMakeModelSettingsOpenAIReasoningEffort:
    """OpenAI reasoning models forward effort to the provider field."""

    def test_o_series_forwards_reasoning_effort_to_openai_field(self):
        from code_puppy.model_factory import make_model_settings

        models_config = {"o3-mini": {"type": "openai", "name": "o3-mini"}}
        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value=models_config,
            ),
            patch(
                "code_puppy.config.get_effective_model_settings",
                return_value={"reasoning_effort": "high"},
            ),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
        ):
            settings = make_model_settings("o3-mini", max_tokens=4096)

        assert settings["openai_reasoning_effort"] == "high"

    def test_o_series_defaults_to_medium(self):
        from code_puppy.model_factory import make_model_settings

        models_config = {"o4-mini": {"type": "openai", "name": "o4-mini"}}
        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value=models_config,
            ),
            patch("code_puppy.config.get_effective_model_settings", return_value={}),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
        ):
            settings = make_model_settings("o4-mini", max_tokens=4096)

        assert settings["openai_reasoning_effort"] == "medium"

    @pytest.mark.parametrize(
        "unsupported_effort",
        ["none", "xhigh", "max", "minimal", "ultra", "banana"],
    )
    def test_o_series_drops_unsupported_effort(self, unsupported_effort):
        from code_puppy.model_factory import make_model_settings

        models_config = {
            "codex-mini-latest": {"type": "openai", "name": "codex-mini-latest"}
        }
        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value=models_config,
            ),
            patch(
                "code_puppy.config.get_effective_model_settings",
                return_value={"reasoning_effort": unsupported_effort},
            ),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
        ):
            settings = make_model_settings("codex-mini-latest", max_tokens=4096)

        assert "openai_reasoning_effort" not in settings

    def test_fixed_effort_model_is_left_untouched(self):
        """o1-mini/o1-preview/gpt-5-pro have no configurable effort at all;
        branch must not fire for them."""
        from code_puppy.model_factory import make_model_settings

        models_config = {"o1-mini": {"type": "openai", "name": "o1-mini"}}
        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value=models_config,
            ),
            patch(
                "code_puppy.config.get_effective_model_settings",
                return_value={"reasoning_effort": "high"},
            ),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
        ):
            settings = make_model_settings("o1-mini", max_tokens=4096)

        assert "openai_reasoning_effort" not in settings

    def test_forwards_via_catalog_name_alias(self):
        """extra_models.json-style entries commonly use a friendly alias
        for the catalog key with the real OpenAI model id in "name"."""
        from code_puppy.model_factory import make_model_settings

        models_config = {"acme-reasoner": {"type": "custom_openai", "name": "o3"}}
        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value=models_config,
            ),
            patch(
                "code_puppy.config.get_effective_model_settings",
                return_value={"reasoning_effort": "high"},
            ),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
        ):
            settings = make_model_settings("acme-reasoner", max_tokens=4096)

        assert settings["openai_reasoning_effort"] == "high"

    def test_short_token_alias_does_not_hijack_a_non_openai_model(self):
        """OpenAI-like aliases must not hijack Anthropic models."""
        from code_puppy.model_factory import make_model_settings

        models_config = {
            "zoo1-claude": {
                "type": "custom_anthropic",
                "name": "claude-3-5-sonnet-20241022",
            }
        }
        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value=models_config,
            ),
            patch(
                "code_puppy.config.get_effective_model_settings",
                return_value={"reasoning_effort": "high"},
            ),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
        ):
            settings = make_model_settings("zoo1-claude", max_tokens=4096)

        assert "openai_reasoning_effort" not in settings
        # Took the Anthropic branch instead (temperature defaulted to 1.0
        # for extended thinking, per that branch's logic).
        assert settings["temperature"] == 1.0

    def test_short_token_alias_does_not_hijack_a_non_anthropic_model_either(self):
        """OpenAI-like aliases must not hijack other provider types."""
        from code_puppy.model_factory import make_model_settings

        models_config = {"team-o1-eval": {"type": "gemini", "name": "gemini-2.5-pro"}}
        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value=models_config,
            ),
            patch(
                "code_puppy.config.get_effective_model_settings",
                return_value={"reasoning_effort": "high"},
            ),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
        ):
            settings = make_model_settings("team-o1-eval", max_tokens=4096)

        assert "openai_reasoning_effort" not in settings
        assert "reasoning_effort" not in settings

    def test_null_catalog_name_does_not_crash(self):
        from code_puppy.model_factory import make_model_settings

        models_config = {"custom-reasoner": {"type": "openai", "name": None}}
        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value=models_config,
            ),
            patch(
                "code_puppy.config.get_effective_model_settings",
                return_value={"reasoning_effort": "high"},
            ),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
        ):
            settings = make_model_settings("custom-reasoner", max_tokens=4096)

        assert settings["max_tokens"] == 4096
        assert "reasoning_effort" not in settings
        assert "openai_reasoning_effort" not in settings

    def test_gpt5_branch_also_falls_back_to_catalog_name_alias(self):
        """GPT-5 aliases retain GPT-5-specific settings handling."""
        from code_puppy.model_factory import make_model_settings

        models_config = {
            "acme-reasoner-5": {"type": "custom_openai", "name": "gpt-5.2"}
        }
        with (
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value=models_config,
            ),
            patch(
                "code_puppy.config.get_effective_model_settings",
                return_value={"reasoning_effort": "high", "verbosity": "low"},
            ),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
        ):
            settings = make_model_settings("acme-reasoner-5", max_tokens=4096)

        assert settings["openai_reasoning_effort"] == "high"
        # Only the GPT-5 branch injects verbosity via extra_body -- proves
        # this went through that branch, not the generic o-series one.
        assert settings["extra_body"]["verbosity"] == "low"
