"""Tests for user-defined custom model params (/model_settings -> Custom Params).

Covers the config-layer JSON blob storage, scalar parsing, the reserved-key
exclusion in get_all_model_settings, and the dotted-key extra_body merge in
make_model_settings.
"""

import json
from unittest.mock import patch

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

    @patch.object(cp_config, "get_value", return_value=None)
    def test_returns_empty_dict_when_unset(self, _mock):
        assert cp_config.get_custom_model_settings("test-model") == {}

    @patch.object(cp_config, "get_value", return_value="   ")
    def test_returns_empty_dict_when_blank(self, _mock):
        assert cp_config.get_custom_model_settings("test-model") == {}

    @patch.object(
        cp_config,
        "get_value",
        return_value='{"chat_template_kwargs.thinking": "medium", "top_k": 5}',
    )
    def test_returns_parsed_dict(self, _mock):
        result = cp_config.get_custom_model_settings("test-model")
        assert result == {"chat_template_kwargs.thinking": "medium", "top_k": 5}

    @patch.object(cp_config, "get_value", return_value="{not valid json")
    def test_fails_closed_on_corrupt_json(self, _mock):
        assert cp_config.get_custom_model_settings("test-model") == {}

    @patch.object(cp_config, "get_value", return_value='["a", "list"]')
    def test_fails_closed_on_non_dict_json(self, _mock):
        assert cp_config.get_custom_model_settings("test-model") == {}

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
