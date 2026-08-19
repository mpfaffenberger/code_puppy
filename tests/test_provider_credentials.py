"""Tests for provider_credentials helper module."""

import os
import unittest
from unittest.mock import patch

import pytest

from code_puppy.provider_credentials import (
    _SECRET_HEADER_NAMES,
    credential_display,
    credential_hint,
    extract_env_var_from_model_config,
    extract_env_vars_from_model_config,
    extract_secret_header_env_vars_from_model_config,
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

    def test_extract_env_vars_includes_header_credentials(self):
        names = extract_env_vars_from_model_config(
            {
                "provider": "custom",
                "custom_endpoint": {
                    "api_key": "$ENDPOINT_KEY",
                    "headers": {
                        "Authorization": "Bearer $MY_SERVICE_TOKEN",
                        "X-Unused": "literal",
                    },
                },
                "api_key": "$TOP_KEY",
            }
        )
        assert names == ["ENDPOINT_KEY", "TOP_KEY", "MY_SERVICE_TOKEN"]


class TestExtractSecretHeaderEnvVars:
    """Only header vars whose NAME marks them a credential are secret."""

    def test_extracts_only_secret_named_header_vars(self):
        names = extract_secret_header_env_vars_from_model_config(
            {"custom_endpoint": {"headers": {"Authorization": "Bearer $A", "X-Title": "$B"}}}
        )
        assert names == ["A"]

    def test_secret_header_name_match_is_case_insensitive(self):
        # The frozenset stores lowercase names, and the header name is lowered
        # before the membership test, so an upper-cased header still matches.
        assert "authorization" in _SECRET_HEADER_NAMES
        names = extract_secret_header_env_vars_from_model_config(
            {"custom_endpoint": {"headers": {"AUTHORIZATION": "Bearer $UPPER"}}}
        )
        assert names == ["UPPER"]


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


class TestEnvironmentWithoutCredentials:
    """The child-shell scrub set derives from api_key fields only."""

    def test_keeps_custom_endpoint_header_non_secret(self, monkeypatch):
        from code_puppy.provider_credentials import environment_without_credentials

        monkeypatch.setattr(
            "code_puppy.provider_credentials._load_merged_model_config",
            lambda: {
                "openrouter-model": {
                    "provider": "openrouter",
                    "api_key": "$OPENROUTER_API_KEY",
                    "custom_endpoint": {"headers": {"HTTP-Referer": "$SITE_URL"}},
                }
            },
        )
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
        monkeypatch.setenv("SITE_URL", "https://example.com")

        env = environment_without_credentials()

        assert "OPENROUTER_API_KEY" not in env
        assert env["SITE_URL"] == "https://example.com"

    def test_scrubs_custom_endpoint_secret_header(self, monkeypatch):
        """A secret-named header var is scrubbed; a sibling non-secret one stays.

        An ``Authorization: Bearer $TOKEN`` authenticates provider calls just as
        an api_key does, so its var must not ride into a model-triggered child
        shell — while a non-secret ``X-Title: $SITE_URL`` still passes through.
        """
        from code_puppy.provider_credentials import environment_without_credentials

        monkeypatch.setattr(
            "code_puppy.provider_credentials._load_merged_model_config",
            lambda: {
                "custom-model": {
                    "provider": "custom",
                    "custom_endpoint": {
                        "headers": {
                            "Authorization": "Bearer $MY_LLM_TOKEN",
                            "X-Title": "$SITE_URL",
                        }
                    },
                }
            },
        )
        monkeypatch.setenv("MY_LLM_TOKEN", "llm-secret")
        monkeypatch.setenv("SITE_URL", "https://example.com")

        env = environment_without_credentials()

        assert "MY_LLM_TOKEN" not in env
        assert env["SITE_URL"] == "https://example.com"

    def test_catalog_change_applies_to_next_call(self, monkeypatch):
        """A mid-session catalog edit reaches the scrub set with no invalidation step."""
        from code_puppy.provider_credentials import (
            credential_env_var_names,
            environment_without_credentials,
            save_credential,
        )

        catalog_keys: list = []
        monkeypatch.setattr(
            "code_puppy.provider_credentials.all_api_key_env_vars",
            lambda: list(catalog_keys),
        )
        monkeypatch.setattr("code_puppy.config.set_config_value", lambda *a, **k: None)
        monkeypatch.setenv("NEW_CUSTOM_API_KEY", "placeholder")
        assert "NEW_CUSTOM_API_KEY" not in credential_env_var_names()

        catalog_keys.append("NEW_CUSTOM_API_KEY")
        assert "NEW_CUSTOM_API_KEY" in credential_env_var_names()

        save_credential("NEW_CUSTOM_API_KEY", "brand-new-secret")
        assert "NEW_CUSTOM_API_KEY" not in environment_without_credentials()


if __name__ == "__main__":
    unittest.main()
