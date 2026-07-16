"""Tests for provider_credentials helper module."""

import os
import unittest
from unittest.mock import patch

from code_puppy.provider_credentials import (
    credential_display,
    credential_hint,
    extract_env_var_from_model_config,
    get_credential_value,
    is_credential_set,
    mask_secret,
    required_env_var_for_model,
    required_env_vars_by_provider,
    save_credential,
)


class TestExtractEnvVarFromModelConfig(unittest.TestCase):
    def test_extracts_from_custom_endpoint_api_key(self):
        config = {
            "provider": "firepass",
            "custom_endpoint": {"api_key": "$FIREWORKS_API_KEY"},
        }
        self.assertEqual(extract_env_var_from_model_config(config), "FIREWORKS_API_KEY")

    def test_extracts_from_top_level_api_key(self):
        config = {"provider": "openai", "api_key": "$OPENAI_API_KEY"}
        self.assertEqual(extract_env_var_from_model_config(config), "OPENAI_API_KEY")

    def test_prefers_custom_endpoint_over_top_level(self):
        config = {
            "provider": "x",
            "api_key": "$TOP_KEY",
            "custom_endpoint": {"api_key": "$ENDPOINT_KEY"},
        }
        self.assertEqual(extract_env_var_from_model_config(config), "ENDPOINT_KEY")

    def test_returns_none_when_no_dollar_prefix(self):
        config = {"provider": "openai", "api_key": "sk-abc123"}
        self.assertIsNone(extract_env_var_from_model_config(config))

    def test_returns_none_for_empty_config(self):
        self.assertIsNone(extract_env_var_from_model_config({}))

    def test_returns_none_for_non_dict(self):
        self.assertIsNone(extract_env_var_from_model_config(None))


class TestMaskSecret(unittest.TestCase):
    def test_masks_long_value(self):
        self.assertEqual(mask_secret("sk-abcdefghijklmnopqrstuvwxyz"), "…wxyz")

    def test_masks_short_value(self):
        self.assertEqual(mask_secret("abcd"), "…d")

    def test_returns_empty_for_none(self):
        self.assertEqual(mask_secret(None), "")

    def test_returns_empty_for_empty_string(self):
        self.assertEqual(mask_secret(""), "")


class TestCredentialDisplay(unittest.TestCase):
    def test_shows_set_with_masked_value(self):
        with patch(
            "code_puppy.provider_credentials.get_credential_value",
            return_value="sk-abc123",
        ):
            self.assertEqual(credential_display("OPENAI_API_KEY"), "set (…c123)")

    def test_shows_not_set_when_missing(self):
        with patch(
            "code_puppy.provider_credentials.get_credential_value",
            return_value=None,
        ):
            self.assertEqual(credential_display("MISSING_KEY"), "not set")


class TestCredentialHint(unittest.TestCase):
    def test_returns_known_hint(self):
        self.assertIn("fireworks", credential_hint("FIREWORKS_API_KEY").lower())

    def test_returns_empty_for_unknown(self):
        self.assertEqual(credential_hint("UNKNOWN_KEY"), "")


class TestSaveCredential(unittest.TestCase):
    def test_saves_to_config_and_environ(self):
        with patch("code_puppy.config.set_config_value") as mock_set:
            save_credential("TEST_KEY", "test_value")
            mock_set.assert_called_once_with("test_key", "test_value")
            self.assertEqual(os.environ.get("TEST_KEY"), "test_value")
            os.environ.pop("TEST_KEY", None)

    def test_saves_empty_value(self):
        with patch("code_puppy.config.set_config_value") as mock_set:
            save_credential("TEST_KEY", "")
            mock_set.assert_called_once_with("test_key", "")
            self.assertNotIn("TEST_KEY", os.environ)


class TestRequiredEnvVarForModel(unittest.TestCase):
    def test_finds_fireworks_model(self):
        with patch(
            "code_puppy.provider_credentials._load_merged_model_config",
            return_value={
                "firepass-kimi-k2p6": {
                    "provider": "firepass",
                    "custom_endpoint": {"api_key": "$FIREWORKS_API_KEY"},
                }
            },
        ):
            result = required_env_var_for_model("firepass-kimi-k2p6")
            self.assertEqual(result, "FIREWORKS_API_KEY")

    def test_returns_none_for_unknown_model(self):
        with patch(
            "code_puppy.provider_credentials._load_merged_model_config",
            return_value={},
        ):
            self.assertIsNone(required_env_var_for_model("nonexistent-model-xyz"))


class TestRequiredEnvVarsByProvider(unittest.TestCase):
    def test_includes_firepass_provider(self):
        with patch(
            "code_puppy.provider_credentials._load_merged_model_config",
            return_value={
                "firepass-kimi-k2p6": {
                    "provider": "firepass",
                    "custom_endpoint": {"api_key": "$FIREWORKS_API_KEY"},
                }
            },
        ):
            result = required_env_vars_by_provider()
            self.assertIn("firepass", result)
            self.assertIn("FIREWORKS_API_KEY", result["firepass"])

    def test_returns_sorted_lists(self):
        with patch(
            "code_puppy.provider_credentials._load_merged_model_config",
            return_value={
                "model-a": {"provider": "p1", "api_key": "$Z_KEY"},
                "model-b": {"provider": "p1", "api_key": "$A_KEY"},
            },
        ):
            result = required_env_vars_by_provider()
            self.assertEqual(result["p1"], ["A_KEY", "Z_KEY"])


class TestGetCredentialValue(unittest.TestCase):
    def test_prefers_config_over_environ(self):
        with patch(
            "code_puppy.config.get_value",
            return_value="config_value",
        ):
            with patch.dict(os.environ, {"TEST_KEY": "env_value"}):
                self.assertEqual(get_credential_value("TEST_KEY"), "config_value")

    def test_falls_back_to_environ(self):
        with patch(
            "code_puppy.config.get_value",
            return_value=None,
        ):
            with patch.dict(os.environ, {"TEST_KEY": "env_value"}):
                self.assertEqual(get_credential_value("TEST_KEY"), "env_value")

    def test_returns_none_when_missing(self):
        with patch(
            "code_puppy.config.get_value",
            return_value=None,
        ):
            os.environ.pop("TEST_KEY_NEVER_SET", None)
            self.assertIsNone(get_credential_value("TEST_KEY_NEVER_SET"))


class TestIsCredentialSet(unittest.TestCase):
    def test_true_when_value_exists(self):
        with patch(
            "code_puppy.provider_credentials.get_credential_value",
            return_value="sk-abc",
        ):
            self.assertTrue(is_credential_set("OPENAI_API_KEY"))

    def test_false_when_missing(self):
        with patch(
            "code_puppy.provider_credentials.get_credential_value",
            return_value=None,
        ):
            self.assertFalse(is_credential_set("MISSING_KEY"))

    def test_false_for_empty_string(self):
        with patch(
            "code_puppy.provider_credentials.get_credential_value",
            return_value="",
        ):
            self.assertFalse(is_credential_set("EMPTY_KEY"))


if __name__ == "__main__":
    unittest.main()
