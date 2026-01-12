"""Test suite for Claude Code OAuth model discovery and management.

Covers model fetching, filtering, storage, and configuration updates.
"""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from code_puppy.plugins.claude_code_oauth.utils import (
    add_models_to_extra_config,
    fetch_claude_code_models,
    filter_latest_claude_models,
    load_claude_models,
    load_claude_models_filtered,
    remove_claude_code_models,
    save_claude_models,
    update_claude_code_model_tokens,
)


@pytest.fixture
def sample_access_token():
    """Sample valid access token."""
    return "claude_access_token_test_12345"


@pytest.fixture
def sample_models_response():
    """Sample models list response from API."""
    return {
        "data": [
            {"id": "claude-opus-4-1-20250805", "name": "Claude Opus 4.1"},
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
            {"id": "claude-haiku-3-5-20241022", "name": "Claude Haiku 3.5"},
        ]
    }


# ============================================================================
# MODEL DISCOVERY AND FILTERING
# ============================================================================


class TestModelDiscovery:
    """Test fetching and discovering Claude models."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.requests.get")
    def test_fetch_claude_code_models_success(
        self, mock_get, sample_access_token, sample_models_response
    ):
        """Test successful model discovery."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_models_response
        mock_get.return_value = mock_response

        models = fetch_claude_code_models(sample_access_token)

        assert models is not None
        assert len(models) == 3
        assert "claude-opus-4-1-20250805" in models
        assert "claude-sonnet-4-20250514" in models
        assert "claude-haiku-3-5-20241022" in models

        # Verify API call was correct
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "/v1/models" in call_args[0][0]
        assert (
            f"Bearer {sample_access_token}" in call_args[1]["headers"]["Authorization"]
        )

    @patch("code_puppy.plugins.claude_code_oauth.utils.requests.get")
    def test_fetch_claude_code_models_api_error(self, mock_get, sample_access_token):
        """Test API error during model fetch."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_get.return_value = mock_response

        models = fetch_claude_code_models(sample_access_token)

        assert models is None

    @patch("code_puppy.plugins.claude_code_oauth.utils.requests.get")
    def test_fetch_claude_code_models_network_error(
        self, mock_get, sample_access_token
    ):
        """Test network error during fetch."""
        mock_get.side_effect = requests.RequestException("Network error")

        models = fetch_claude_code_models(sample_access_token)

        assert models is None

    @patch("code_puppy.plugins.claude_code_oauth.utils.requests.get")
    def test_fetch_claude_code_models_invalid_response(
        self, mock_get, sample_access_token
    ):
        """Test handling of invalid response format."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"invalid": "format"}
        mock_get.return_value = mock_response

        models = fetch_claude_code_models(sample_access_token)

        assert models is None


class TestModelFiltering:
    """Test model filtering to keep only latest versions."""

    def test_filter_latest_claude_models_keeps_latest(self):
        """Test filtering keeps latest version of each family."""
        models = [
            "claude-opus-4-0-20250101",
            "claude-opus-4-1-20250805",  # Latest opus
            "claude-sonnet-4-0-20250101",
            "claude-sonnet-4-5-20250514",  # Latest sonnet
            "claude-haiku-3-0-20241022",
            "claude-haiku-3-5-20241022",  # Latest haiku
        ]

        filtered = filter_latest_claude_models(models)

        assert len(filtered) == 3
        assert "claude-opus-4-1-20250805" in filtered
        assert "claude-sonnet-4-5-20250514" in filtered
        assert "claude-haiku-3-5-20241022" in filtered

    def test_filter_latest_claude_models_single_version(self):
        """Test filtering with single version of each family."""
        models = [
            "claude-opus-4-1-20250805",
            "claude-sonnet-4-5-20250514",
            "claude-haiku-3-5-20241022",
        ]

        filtered = filter_latest_claude_models(models)

        assert len(filtered) == 3
        assert set(filtered) == set(models)

    def test_filter_latest_claude_models_ignores_invalid(self):
        """Test that invalid model names are ignored."""
        models = [
            "invalid-model-name",
            "claude-opus-4-1-20250805",
            "gpt-4",
            "claude-sonnet-4-5-20250514",
        ]

        filtered = filter_latest_claude_models(models)

        assert "invalid-model-name" not in filtered
        assert "gpt-4" not in filtered
        assert len(filtered) == 2

    def test_filter_latest_claude_models_date_comparison(self):
        """Test that date-based filtering works correctly."""
        models = [
            "claude-opus-4-1-20250101",
            "claude-opus-4-1-20250805",  # More recent
            "claude-opus-4-1-20250615",  # In between
        ]

        filtered = filter_latest_claude_models(models)

        assert len(filtered) == 1
        assert "claude-opus-4-1-20250805" in filtered


# ============================================================================
# MODEL STORAGE AND MANAGEMENT
# ============================================================================


class TestModelStorage:
    """Test loading and saving Claude models."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path")
    def test_load_claude_models_existing(self, mock_path, tmp_path):
        """Test loading existing models."""
        models_file = tmp_path / "models.json"
        test_models = {
            "claude-code-opus": {"type": "claude_code", "name": "claude-opus"},
        }
        models_file.write_text(json.dumps(test_models))
        mock_path.return_value = models_file

        loaded = load_claude_models()

        assert loaded == test_models

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path")
    def test_load_claude_models_nonexistent(self, mock_path, tmp_path):
        """Test loading when models file doesn't exist."""
        models_file = tmp_path / "nonexistent.json"
        mock_path.return_value = models_file

        loaded = load_claude_models()

        assert loaded == {}

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path")
    def test_load_claude_models_corrupted(self, mock_path, tmp_path):
        """Test loading corrupted models file."""
        models_file = tmp_path / "corrupted.json"
        models_file.write_text("{ invalid json")
        mock_path.return_value = models_file

        loaded = load_claude_models()

        assert loaded == {}

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path")
    def test_save_claude_models(self, mock_path, tmp_path):
        """Test saving models to file."""
        models_file = tmp_path / "models.json"
        mock_path.return_value = models_file
        test_models = {
            "claude-code-opus": {"type": "claude_code", "name": "claude-opus"},
        }

        result = save_claude_models(test_models)

        assert result is True
        assert models_file.exists()
        with open(models_file) as f:
            saved = json.load(f)
        assert saved == test_models

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path")
    def test_save_claude_models_failure(self, mock_path):
        """Test save failure handling."""
        mock_path.side_effect = Exception("Permission denied")

        result = save_claude_models({"test": "data"})

        assert result is False


class TestLoadModelFiltered:
    """Test filtered model loading."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_claude_models")
    def test_load_claude_models_filtered_with_oauth_source(self, mock_load):
        """Test filtering applies to OAuth models."""
        all_models = {
            "claude-code-opus-4-1-20250805": {
                "name": "claude-opus-4-1-20250805",
                "oauth_source": "claude-code-plugin",
            },
            "claude-code-sonnet-4-5-20250514": {
                "name": "claude-sonnet-4-5-20250514",
                "oauth_source": "claude-code-plugin",
            },
        }
        mock_load.return_value = all_models

        filtered = load_claude_models_filtered()

        assert len(filtered) == 2
        assert "claude-code-opus-4-1-20250805" in filtered


# ============================================================================
# ADD/REMOVE MODELS
# ============================================================================


class TestAddRemoveModels:
    """Test adding and removing models from configuration."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_valid_access_token")
    @patch("code_puppy.plugins.claude_code_oauth.utils.save_claude_models")
    def test_add_models_to_extra_config(self, mock_save, mock_get_token):
        """Test adding models to configuration."""
        mock_get_token.return_value = "test_token_123"
        mock_save.return_value = True
        models = [
            "claude-opus-4-1-20250805",
            "claude-sonnet-4-5-20250514",
            "claude-haiku-3-5-20241022",
        ]

        result = add_models_to_extra_config(models)

        assert result is True
        mock_save.assert_called_once()
        saved_models = mock_save.call_args[0][0]
        assert len(saved_models) == 3
        # Verify models have proper structure
        for key, model_config in saved_models.items():
            assert "claude-code-" in key
            assert model_config["oauth_source"] == "claude-code-plugin"
            assert model_config["type"] == "claude_code"
            assert "custom_endpoint" in model_config

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_claude_models")
    @patch("code_puppy.plugins.claude_code_oauth.utils.save_claude_models")
    def test_remove_claude_code_models(self, mock_save, mock_load):
        """Test removing Claude Code models."""
        all_models = {
            "claude-code-opus": {"oauth_source": "claude-code-plugin"},
            "claude-code-sonnet": {"oauth_source": "claude-code-plugin"},
            "other-model": {"oauth_source": "other"},
        }
        mock_load.return_value = all_models
        mock_save.return_value = True

        removed = remove_claude_code_models()

        assert removed == 2
        # Verify remaining models
        saved_models = mock_save.call_args[0][0]
        assert "claude-code-opus" not in saved_models
        assert "claude-code-sonnet" not in saved_models
        assert "other-model" in saved_models

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_claude_models")
    def test_remove_claude_code_models_none_to_remove(self, mock_load):
        """Test remove when no models to remove."""
        mock_load.return_value = {"other-model": {"oauth_source": "other"}}

        removed = remove_claude_code_models()

        assert removed == 0


# ============================================================================
# UPDATE TOKENS IN MODELS
# ============================================================================


class TestUpdateModelTokens:
    """Test updating access tokens in model configurations."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_claude_models")
    @patch("code_puppy.plugins.claude_code_oauth.utils.save_claude_models")
    def test_update_claude_code_model_tokens(self, mock_save, mock_load):
        """Test updating tokens in model configs."""
        old_token = "old_token_123"
        new_token = "new_token_456"
        models = {
            "claude-code-opus": {
                "oauth_source": "claude-code-plugin",
                "custom_endpoint": {"api_key": old_token},
            },
        }
        mock_load.return_value = models
        mock_save.return_value = True

        result = update_claude_code_model_tokens(new_token)

        assert result is True
        saved_models = mock_save.call_args[0][0]
        assert (
            saved_models["claude-code-opus"]["custom_endpoint"]["api_key"] == new_token
        )

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_claude_models")
    def test_update_claude_code_model_tokens_no_models(self, mock_load):
        """Test updating tokens when no models exist."""
        mock_load.return_value = {}

        result = update_claude_code_model_tokens("test_token")

        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
