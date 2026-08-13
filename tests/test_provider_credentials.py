"""Tests for provider_credentials helper module."""

import os
import unittest
from unittest.mock import patch

import pytest

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


class TestExtractEnvVarFromModelConfig:
    """Extraction of ``$ENV`` references from a model config."""

    @pytest.mark.parametrize(
        "config,expected",
        [
            (
                {
                    "provider": "firepass",
                    "custom_endpoint": {"api_key": "$FIREWORKS_API_KEY"},
                },
                "FIREWORKS_API_KEY",
            ),
            ({"provider": "openai", "api_key": "$OPENAI_API_KEY"}, "OPENAI_API_KEY"),
            (
                {
                    "provider": "x",
                    "api_key": "$TOP_KEY",
                    "custom_endpoint": {"api_key": "$ENDPOINT_KEY"},
                },
                "ENDPOINT_KEY",
            ),
            ({"provider": "openai", "api_key": "sk-abc123"}, None),
            ({}, None),
            (None, None),
        ],
    )
    def test_extract_env_var_from_model_config(self, config, expected):
        assert extract_env_var_from_model_config(config) == expected


class TestMaskSecret:
    """mask_secret keeps only the last few characters visible."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("sk-abcdefghijklmnopqrstuvwxyz", "…wxyz"),
            ("abcd", "…d"),
            (None, ""),
            ("", ""),
        ],
    )
    def test_mask_secret(self, value, expected):
        assert mask_secret(value) == expected


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


class TestIsCredentialSet:
    """is_credential_set is true only for non-empty resolved values."""

    @pytest.mark.parametrize(
        "cred_value,expected", [("sk-abc", True), (None, False), ("", False)]
    )
    def test_is_credential_set(self, cred_value, expected):
        with patch(
            "code_puppy.provider_credentials.get_credential_value",
            return_value=cred_value,
        ):
            assert is_credential_set("ANY_KEY") is expected


if __name__ == "__main__":
    unittest.main()
