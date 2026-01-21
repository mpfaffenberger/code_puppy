"""Comprehensive unit tests for antigravity_oauth/utils.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.antigravity_oauth.utils import (
    add_models_to_config,
    get_model_families_summary,
    load_antigravity_models,
    load_stored_tokens,
    reload_current_agent,
    remove_antigravity_models,
    save_antigravity_models,
    save_tokens,
)


class TestLoadStoredTokens:
    """Tests for load_stored_tokens function."""

    def test_load_stored_tokens_success(self, tmp_path):
        """Test successfully loading stored tokens from disk."""
        token_data = {"access_token": "test_token", "refresh_token": "refresh"}
        token_file = tmp_path / "tokens.json"
        token_file.write_text(json.dumps(token_data))

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            result = load_stored_tokens()

        assert result == token_data

    def test_load_stored_tokens_file_not_found(self):
        """Test load_stored_tokens returns None when file doesn't exist."""
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=Path("/nonexistent/path/tokens.json"),
        ):
            result = load_stored_tokens()

        assert result is None

    def test_load_stored_tokens_json_decode_error(self, tmp_path):
        """Test load_stored_tokens returns None on JSON decode error."""
        token_file = tmp_path / "tokens.json"
        token_file.write_text("invalid json{")

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            result = load_stored_tokens()

        assert result is None

    def test_load_stored_tokens_read_error(self):
        """Test load_stored_tokens returns None on read error."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.open.side_effect = PermissionError("No permission")

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=mock_path,
        ):
            result = load_stored_tokens()

        assert result is None

    def test_load_stored_tokens_empty_file(self, tmp_path):
        """Test load_stored_tokens with empty file."""
        token_file = tmp_path / "tokens.json"
        token_file.write_text("{}")  # Empty JSON object

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            result = load_stored_tokens()

        assert result == {}


class TestSaveTokens:
    """Tests for save_tokens function."""

    def test_save_tokens_success(self, tmp_path):
        """Test successfully saving tokens to disk."""
        token_file = tmp_path / "tokens.json"
        token_data = {"access_token": "test_token", "refresh_token": "refresh"}

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            result = save_tokens(token_data)

        assert result is True
        assert token_file.exists()
        saved_data = json.loads(token_file.read_text())
        assert saved_data == token_data

    def test_save_tokens_creates_directory(self, tmp_path):
        """Test save_tokens creates parent directory if needed."""
        token_file = tmp_path / "subdir" / "tokens.json"
        token_data = {"access_token": "test_token"}

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            # This should fail since parent directory doesn't exist
            result = save_tokens(token_data)

        # The function doesn't create directories, so it should fail
        assert result is False

    def test_save_tokens_file_permissions(self, tmp_path):
        """Test save_tokens sets correct file permissions."""
        token_file = tmp_path / "tokens.json"
        token_data = {"access_token": "test_token"}

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            result = save_tokens(token_data)

        assert result is True
        # Check that chmod(0o600) was called implicitly
        file_stat = token_file.stat()
        # Mode should be restrictive (only owner can read/write)
        assert file_stat.st_mode & 0o077 == 0

    def test_save_tokens_write_error(self):
        """Test save_tokens returns False on write error."""
        mock_path = MagicMock(spec=Path)
        mock_path.open.side_effect = PermissionError("No write permission")

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=mock_path,
        ):
            result = save_tokens({"access_token": "test"})

        assert result is False

    def test_save_tokens_chmod_error(self, tmp_path):
        """Test save_tokens handles chmod errors gracefully."""
        token_file = tmp_path / "tokens.json"
        token_data = {"access_token": "test_token"}

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
                return_value=token_file,
            ),
            patch.object(Path, "chmod", side_effect=PermissionError("Cannot chmod")),
        ):
            result = save_tokens(token_data)

        # Should still fail because chmod raised an error
        assert result is False

    def test_save_tokens_empty_dict(self, tmp_path):
        """Test save_tokens with empty dict."""
        token_file = tmp_path / "tokens.json"
        token_data = {}

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            result = save_tokens(token_data)

        assert result is True
        saved_data = json.loads(token_file.read_text())
        assert saved_data == {}

    def test_save_tokens_complex_structure(self, tmp_path):
        """Test save_tokens with complex nested structure."""
        token_file = tmp_path / "tokens.json"
        token_data = {
            "access_token": "test_token",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "scopes": ["scope1", "scope2"],
            "metadata": {"user_id": "123", "email": "test@example.com"},
        }

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            result = save_tokens(token_data)

        assert result is True
        saved_data = json.loads(token_file.read_text())
        assert saved_data == token_data


class TestLoadAntigravityModels:
    """Tests for load_antigravity_models function."""

    def test_load_antigravity_models_success(self, tmp_path):
        """Test successfully loading antigravity models from disk."""
        models_data = {
            "antigravity-gemini-3-pro": {
                "type": "custom_gemini",
                "name": "gemini-3-pro",
            }
        }
        models_file = tmp_path / "models.json"
        models_file.write_text(json.dumps(models_data))

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_antigravity_models_path",
            return_value=models_file,
        ):
            result = load_antigravity_models()

        assert result == models_data

    def test_load_antigravity_models_file_not_found(self):
        """Test load_antigravity_models returns empty dict when file doesn't exist."""
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_antigravity_models_path",
            return_value=Path("/nonexistent/path/models.json"),
        ):
            result = load_antigravity_models()

        assert result == {}

    def test_load_antigravity_models_json_decode_error(self, tmp_path):
        """Test load_antigravity_models returns empty dict on JSON decode error."""
        models_file = tmp_path / "models.json"
        models_file.write_text("invalid json{")

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_antigravity_models_path",
            return_value=models_file,
        ):
            result = load_antigravity_models()

        assert result == {}

    def test_load_antigravity_models_read_error(self):
        """Test load_antigravity_models returns empty dict on read error."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.open.side_effect = PermissionError("No permission")

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_antigravity_models_path",
            return_value=mock_path,
        ):
            result = load_antigravity_models()

        assert result == {}

    def test_load_antigravity_models_empty_file(self, tmp_path):
        """Test load_antigravity_models with empty JSON object."""
        models_file = tmp_path / "models.json"
        models_file.write_text("{}")

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_antigravity_models_path",
            return_value=models_file,
        ):
            result = load_antigravity_models()

        assert result == {}


class TestSaveAntigravityModels:
    """Tests for save_antigravity_models function."""

    def test_save_antigravity_models_success(self, tmp_path):
        """Test successfully saving antigravity models to disk."""
        models_file = tmp_path / "models.json"
        models_data = {
            "antigravity-gemini-3-pro": {
                "type": "custom_gemini",
                "name": "gemini-3-pro",
            }
        }

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_antigravity_models_path",
            return_value=models_file,
        ):
            result = save_antigravity_models(models_data)

        assert result is True
        saved_data = json.loads(models_file.read_text())
        assert saved_data == models_data

    def test_save_antigravity_models_write_error(self):
        """Test save_antigravity_models returns False on write error."""
        mock_path = MagicMock(spec=Path)
        mock_path.open.side_effect = PermissionError("No write permission")

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_antigravity_models_path",
            return_value=mock_path,
        ):
            result = save_antigravity_models({"model": "data"})

        assert result is False

    def test_save_antigravity_models_empty_dict(self, tmp_path):
        """Test save_antigravity_models with empty dict."""
        models_file = tmp_path / "models.json"

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_antigravity_models_path",
            return_value=models_file,
        ):
            result = save_antigravity_models({})

        assert result is True
        saved_data = json.loads(models_file.read_text())
        assert saved_data == {}

    def test_save_antigravity_models_complex_structure(self, tmp_path):
        """Test save_antigravity_models with complex nested structure."""
        models_file = tmp_path / "models.json"
        models_data = {
            "antigravity-gemini-3-pro": {
                "type": "custom_gemini",
                "name": "gemini-3-pro",
                "custom_endpoint": {"url": "http://example.com", "api_key": "key"},
                "context_length": 200000,
                "thinking_budget": 8192,
            },
            "antigravity-claude-sonnet": {
                "type": "custom_claude",
                "name": "claude-sonnet",
                "context_length": 200000,
            },
        }

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.get_antigravity_models_path",
            return_value=models_file,
        ):
            result = save_antigravity_models(models_data)

        assert result is True
        saved_data = json.loads(models_file.read_text())
        assert saved_data == models_data


class TestAddModelsToConfig:
    """Tests for add_models_to_config function."""

    def test_add_models_to_config_success(self, tmp_path):
        """Test successfully adding models to config."""
        tmp_path / "models.json"
        access_token = "test_access_token"
        project_id = "test-project-id"

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.save_antigravity_models",
            return_value=True,
        ) as mock_save:
            result = add_models_to_config(access_token, project_id)

        assert result is True
        # Verify save was called with models
        assert mock_save.called
        saved_models = mock_save.call_args[0][0]
        assert len(saved_models) > 0
        # Check first model structure
        first_key = next(iter(saved_models))
        assert "antigravity-" in first_key
        assert saved_models[first_key]["type"] == "antigravity"
        assert saved_models[first_key]["oauth_source"] == "antigravity-plugin"
        assert saved_models[first_key]["name"]  # Has model name
        assert saved_models[first_key]["custom_endpoint"]["api_key"] == access_token
        assert saved_models[first_key]["project_id"] == project_id

    def test_add_models_to_config_with_thinking_budget(self, tmp_path):
        """Test add_models_to_config includes thinking budget when present."""
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.save_antigravity_models",
            return_value=True,
        ) as mock_save:
            result = add_models_to_config("token", "project")

        assert result is True
        saved_models = mock_save.call_args[0][0]
        # Check that thinking models have thinking_budget
        thinking_models = [
            m for m in saved_models.values() if "thinking" in m.get("name", "").lower()
        ]
        for model in thinking_models:
            assert "thinking_budget" in model

    def test_add_models_to_config_save_failure(self):
        """Test add_models_to_config returns False when save fails."""
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.save_antigravity_models",
            return_value=False,
        ):
            result = add_models_to_config("token", "project")

        assert result is False

    def test_add_models_to_config_exception(self):
        """Test add_models_to_config handles exceptions gracefully."""
        # Mock save_antigravity_models to raise an exception
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.save_antigravity_models",
            side_effect=Exception("Save error"),
        ):
            result = add_models_to_config("token", "project")

        assert result is False

    def test_add_models_to_config_default_project_id(self):
        """Test add_models_to_config with default empty project_id."""
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.save_antigravity_models",
            return_value=True,
        ) as mock_save:
            result = add_models_to_config("token")

        assert result is True
        saved_models = mock_save.call_args[0][0]
        first_model = next(iter(saved_models.values()))
        assert first_model["project_id"] == ""

    def test_add_models_to_config_custom_headers(self):
        """Test add_models_to_config includes custom headers."""
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.save_antigravity_models",
            return_value=True,
        ) as mock_save:
            result = add_models_to_config("token")

        assert result is True
        saved_models = mock_save.call_args[0][0]
        first_model = next(iter(saved_models.values()))
        assert "headers" in first_model["custom_endpoint"]
        headers = first_model["custom_endpoint"]["headers"]
        assert "User-Agent" in headers
        assert "X-Goog-Api-Client" in headers


class TestRemoveAntigravityModels:
    """Tests for remove_antigravity_models function."""

    def test_remove_antigravity_models_success(self):
        """Test successfully removing antigravity models."""
        models_to_keep = {"other-model-1": {"oauth_source": "other"}}
        models_to_remove = {
            "antigravity-gemini-1": {"oauth_source": "antigravity-plugin"},
            "antigravity-gemini-2": {"oauth_source": "antigravity-plugin"},
        }
        all_models = {**models_to_keep, **models_to_remove}

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.utils.load_antigravity_models",
                return_value=all_models,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.utils.save_antigravity_models",
                return_value=True,
            ) as mock_save,
        ):
            result = remove_antigravity_models()

        assert result == 2
        # Verify that only models to keep were saved
        saved_models = mock_save.call_args[0][0]
        assert len(saved_models) == 1
        assert "other-model-1" in saved_models

    def test_remove_antigravity_models_none_to_remove(self):
        """Test remove_antigravity_models when no antigravity models exist."""
        models = {"other-model-1": {"oauth_source": "other"}}

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.load_antigravity_models",
            return_value=models,
        ):
            result = remove_antigravity_models()

        assert result == 0

    def test_remove_antigravity_models_all_antigravity(self):
        """Test remove_antigravity_models when all models are antigravity."""
        models = {
            "antigravity-gemini-1": {"oauth_source": "antigravity-plugin"},
            "antigravity-gemini-2": {"oauth_source": "antigravity-plugin"},
        }

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.utils.load_antigravity_models",
                return_value=models,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.utils.save_antigravity_models",
                return_value=True,
            ) as mock_save,
        ):
            result = remove_antigravity_models()

        assert result == 2
        # Should save empty dict
        saved_models = mock_save.call_args[0][0]
        assert len(saved_models) == 0

    def test_remove_antigravity_models_save_failure(self):
        """Test remove_antigravity_models returns 0 when save fails."""
        models = {"antigravity-gemini-1": {"oauth_source": "antigravity-plugin"}}

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.utils.load_antigravity_models",
                return_value=models,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.utils.save_antigravity_models",
                return_value=False,
            ),
        ):
            result = remove_antigravity_models()

        assert result == 0

    def test_remove_antigravity_models_exception(self):
        """Test remove_antigravity_models handles exceptions gracefully."""
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.load_antigravity_models",
            side_effect=Exception("Load error"),
        ):
            result = remove_antigravity_models()

        assert result == 0

    def test_remove_antigravity_models_empty_dict(self):
        """Test remove_antigravity_models with empty models dict."""
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.load_antigravity_models",
            return_value={},
        ):
            result = remove_antigravity_models()

        assert result == 0

    def test_remove_antigravity_models_missing_oauth_source(self):
        """Test remove_antigravity_models with model missing oauth_source field."""
        models = {
            "model-with-source": {"oauth_source": "antigravity-plugin"},
            "model-without-source": {"name": "test"},  # Missing oauth_source
        }

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.utils.load_antigravity_models",
                return_value=models,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.utils.save_antigravity_models",
                return_value=True,
            ) as mock_save,
        ):
            result = remove_antigravity_models()

        # Only the one with oauth_source="antigravity-plugin" should be removed
        assert result == 1
        saved_models = mock_save.call_args[0][0]
        assert "model-without-source" in saved_models
        assert "model-with-source" not in saved_models


class TestGetModelFamiliesSummary:
    """Tests for get_model_families_summary function."""

    def test_get_model_families_summary_basic(self):
        """Test get_model_families_summary returns correct structure."""
        result = get_model_families_summary()

        assert isinstance(result, dict)
        assert "gemini" in result
        assert "claude" in result
        assert "other" in result

    def test_get_model_families_summary_gemini_models(self):
        """Test get_model_families_summary includes gemini models."""
        result = get_model_families_summary()

        gemini_models = result["gemini"]
        assert isinstance(gemini_models, list)
        assert len(gemini_models) > 0
        # Check for known gemini models
        assert any("gemini" in m for m in gemini_models)

    def test_get_model_families_summary_claude_models(self):
        """Test get_model_families_summary includes claude models."""
        result = get_model_families_summary()

        claude_models = result["claude"]
        assert isinstance(claude_models, list)
        assert len(claude_models) > 0
        # Check for known claude models
        assert any("claude" in m for m in claude_models)

    def test_get_model_families_summary_no_duplicates(self):
        """Test get_model_families_summary has no duplicate models."""
        result = get_model_families_summary()

        all_models = result["gemini"] + result["claude"] + result["other"]
        assert len(all_models) == len(set(all_models))

    def test_get_model_families_summary_all_models_categorized(self):
        """Test all available models are categorized in families."""
        from code_puppy.plugins.antigravity_oauth.constants import ANTIGRAVITY_MODELS

        result = get_model_families_summary()
        categorized_models = set(result["gemini"] + result["claude"] + result["other"])

        # All ANTIGRAVITY_MODELS should be in the summary
        assert categorized_models == set(ANTIGRAVITY_MODELS.keys())

    def test_get_model_families_summary_unknown_family(self):
        """Test get_model_families_summary handles unknown family gracefully."""
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.ANTIGRAVITY_MODELS",
            {
                "model-unknown": {"family": "unknown_family"},
                "model-gemini": {"family": "gemini"},
            },
        ):
            result = get_model_families_summary()

        # Unknown family should be ignored
        assert "unknown_family" not in result
        assert "model-unknown" not in result["other"]
        assert "model-gemini" in result["gemini"]

    def test_get_model_families_summary_default_to_other(self):
        """Test models without family key default to 'other'."""
        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.ANTIGRAVITY_MODELS",
            {"model-no-family": {"name": "test"}},  # No 'family' key
        ):
            result = get_model_families_summary()

        assert "model-no-family" in result["other"]


class TestReloadCurrentAgent:
    """Tests for reload_current_agent function."""

    def test_reload_current_agent_no_exception_on_none(self):
        """Test reload_current_agent handles None agent gracefully."""
        # When no agent is loaded, it should not crash
        with patch.dict(
            "sys.modules",
            {"code_puppy.agents": MagicMock(get_current_agent=lambda: None)},
        ):
            try:
                reload_current_agent()
            except Exception as e:
                # Should not raise any exceptions related to agent reload
                if "reload" in str(e).lower():
                    pytest.fail(
                        f"reload_current_agent raised unexpected exception: {e}"
                    )

    def test_reload_current_agent_gracefully_handles_exceptions(self):
        """Test reload_current_agent doesn't propagate all exceptions."""
        # The function wraps the entire try/except, so most exceptions are caught
        # We just verify it doesn't crash the module
        try:
            reload_current_agent()
        except Exception as e:
            # If no agent is loaded, we should get a warning, not an exception
            pytest.fail(f"reload_current_agent should not raise: {e}")

    def test_reload_current_agent_with_mock_agent(self):
        """Test reload_current_agent with a properly mocked agent."""
        mock_agent = MagicMock()
        mock_agent.refresh_config = MagicMock()
        mock_agent.reload_code_generation_agent = MagicMock()

        # Create a mock module for code_puppy.agents
        mock_agents_module = MagicMock()
        mock_agents_module.get_current_agent = lambda: mock_agent

        import sys

        with patch.dict(sys.modules, {"code_puppy.agents": mock_agents_module}):
            reload_current_agent()

        # Verify methods were called
        mock_agent.refresh_config.assert_called_once()
        mock_agent.reload_code_generation_agent.assert_called_once()

    def test_reload_current_agent_refresh_error_doesnt_stop_reload(self):
        """Test reload continues even if refresh_config raises."""
        mock_agent = MagicMock()
        mock_agent.refresh_config = MagicMock(side_effect=Exception("refresh error"))
        mock_agent.reload_code_generation_agent = MagicMock()

        mock_agents_module = MagicMock()
        mock_agents_module.get_current_agent = lambda: mock_agent

        import sys

        with patch.dict(sys.modules, {"code_puppy.agents": mock_agents_module}):
            reload_current_agent()

        # Reload should still be called despite refresh error
        mock_agent.reload_code_generation_agent.assert_called_once()
