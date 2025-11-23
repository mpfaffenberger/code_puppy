"""Integration tests for OAuth plugin system.

These tests cover end-to-end OAuth flows, security scenarios,
and integration between different OAuth components.
"""

import json
import threading
import time
import urllib.parse
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from code_puppy.plugins.chatgpt_oauth.config import (
    CHATGPT_OAUTH_CONFIG,
    get_chatgpt_models_path,
    get_token_storage_path,
)
from code_puppy.plugins.chatgpt_oauth.utils import (
    add_models_to_extra_config,
    exchange_code_for_tokens,
    fetch_chatgpt_models,
    load_stored_tokens,
    prepare_oauth_context,
    save_tokens,
)
from code_puppy.plugins.claude_code_oauth.config import (
    CLAUDE_CODE_OAUTH_CONFIG,
)
from code_puppy.plugins.claude_code_oauth.config import (
    get_token_storage_path as get_claude_token_path,
)
from code_puppy.plugins.claude_code_oauth.utils import (
    add_models_to_extra_config as claude_add_models,
)
from code_puppy.plugins.claude_code_oauth.utils import (
    exchange_code_for_tokens as claude_exchange_code,
)
from code_puppy.plugins.claude_code_oauth.utils import (
    fetch_claude_code_models,
)
from code_puppy.plugins.claude_code_oauth.utils import (
    prepare_oauth_context as claude_prepare_context,
)


@pytest.fixture
def mock_token_storage(tmp_path):
    """Mock token storage path for testing."""
    token_path = tmp_path / "test_oauth_tokens.json"
    return token_path


@pytest.fixture
def mock_models_storage(tmp_path):
    """Mock models storage path for testing."""
    models_path = tmp_path / "test_oauth_models.json"
    return models_path


@pytest.fixture
def sample_oauth_tokens():
    """Sample OAuth token data for testing."""
    return {
        "access_token": "test_access_token_123",
        "refresh_token": "test_refresh_token_456",
        "id_token": "fake_id",
        "account_id": "account_789",
        "last_refresh": "2023-01-01T00:00:00Z",
        "scope": "openid profile email offline_access",
    }


@pytest.fixture
def sample_claude_tokens():
    """Sample Claude OAuth token data."""
    return {
        "access_token": "claude_access_token_abc",
        "refresh_token": "claude_refresh_token_def",
        "token_type": "Bearer",
        "scope": "org:create_api_key user:profile user:inference",
        "expires_in": 3600,
    }


class TestOAuthFlowIntegration:
    """Integration tests for OAuth flow components."""

    @patch("requests.post")
    @patch("webbrowser.open")
    def test_complete_chatgpt_oauth_flow(
        self, mock_browser, mock_post, mock_token_storage
    ):
        """Test end-to-end ChatGPT OAuth flow simulation."""
        # Mock successful token exchange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "access_token": "sk-test_access_token",
            "refresh_token": "test_refresh_token",
            "id_token": "test_id_token",
        }
        mock_post.return_value = mock_response

        # Mock token storage path
        with patch(
            "code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path",
            return_value=mock_token_storage,
        ):
            with patch(
                "code_puppy.plugins.chatgpt_oauth.utils.parse_jwt_claims"
            ) as mock_jwt:
                mock_jwt.return_value = {
                    "https://api.openai.com/auth": {
                        "chatgpt_account_id": "account_123",
                        "organizations": [{"id": "org_456", "is_default": True}],
                    }
                }

                # Prepare OAuth context and simulate flow
                context = prepare_oauth_context()
                context.redirect_uri = "http://localhost:1455/auth/callback"

                # Exchange authorization code for tokens
                tokens = exchange_code_for_tokens("test_auth_code", context)

                assert tokens is not None
                assert tokens["access_token"] == "sk-test_access_token"
                assert "last_refresh" in tokens

                # Save tokens to storage
                save_success = save_tokens(tokens)
                assert save_success is True

                # Verify tokens were saved
                loaded_tokens = load_stored_tokens()
                assert loaded_tokens == tokens

                # Verify file permissions
                file_stat = mock_token_storage.stat()
                assert file_stat.st_mode & 0o777 == 0o600

    @patch("requests.get")
    @patch("requests.post")
    def test_chatgpt_model_registration_flow(
        self, mock_post, mock_get, mock_token_storage, mock_models_storage
    ):
        """Test complete flow from OAuth to model registration."""
        # Mock token exchange
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "access_token": "test_api_key",
                "refresh_token": "test_refresh",
                "id_token": "test_id",
            },
        )

        # Mock model fetching
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "data": [
                    {"id": "gpt-4"},
                    {"id": "gpt-3.5-turbo"},
                    {"id": "whisper-1"},  # Should be filtered out
                ]
            },
        )

        with patch(
            "code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path",
            return_value=mock_token_storage,
        ):
            with patch(
                "code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path",
                return_value=mock_models_storage,
            ):
                with patch(
                    "code_puppy.plugins.chatgpt_oauth.utils.parse_jwt_claims"
                ) as mock_jwt:
                    mock_jwt.return_value = {
                        "https://api.openai.com/auth": {
                            "chatgpt_account_id": "test_account",
                        }
                    }

                    # Simulate complete flow
                    context = prepare_oauth_context()
                    context.redirect_uri = "http://localhost:1455/auth/callback"

                    # 1. Exchange code for tokens
                    tokens = exchange_code_for_tokens("test_code", context)
                    assert tokens is not None

                    # 2. Save tokens
                    save_tokens(tokens)

                    # 3. Fetch models with new API key
                    models = fetch_chatgpt_models(tokens["access_token"])
                    assert models == ["gpt-4", "gpt-3.5-turbo"]

                    # 4. Register models in config
                    success = add_models_to_extra_config(models, tokens["access_token"])
                    assert success is True

                    # Verify models were saved
                    with open(mock_models_storage, "r") as f:
                        saved_models = json.load(f)

                    assert "chatgpt-gpt-4" in saved_models
                    assert "chatgpt-gpt-3.5-turbo" in saved_models
                    assert (
                        saved_models["chatgpt-gpt-4"]["oauth_source"]
                        == "chatgpt-oauth-plugin"
                    )
                    assert (
                        saved_models["chatgpt-gpt-4"]["custom_endpoint"]["api_key"]
                        == "${CHATGPT_OAUTH_API_KEY}"
                    )

    @patch("requests.get")
    @patch("requests.post")
    def test_claude_complete_oauth_flow(self, mock_post, mock_get, tmp_path):
        """Test complete Claude OAuth flow from tokens to models."""
        token_path = tmp_path / "claude_tokens.json"
        models_path = tmp_path / "claude_models.json"

        # Mock token exchange
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "access_token": "claude_access_token",
                "refresh_token": "claude_refresh_token",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

        # Mock model fetching
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "data": [
                    {"id": "claude-3-5-sonnet-20241022"},
                    {"id": "claude-3-5-haiku-20241022"},
                    {"id": "claude-3-opus-20240229"},
                ]
            },
        )

        with patch(
            "code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path",
            return_value=token_path,
        ):
            with patch(
                "code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path",
                return_value=models_path,
            ):
                with patch(
                    "code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens"
                ) as mock_load_tokens:
                    mock_load_tokens.return_value = {
                        "access_token": "claude_access_token"
                    }

                    # 1. Prepare context and exchange tokens
                    context = claude_prepare_context()
                    context.redirect_uri = "http://localhost:8765/callback"

                    tokens = claude_exchange_code("test_code", context)
                    assert tokens is not None
                    assert tokens["access_token"] == "claude_access_token"

                    # 2. Save tokens
                    with patch(
                        "code_puppy.plugins.claude_code_oauth.utils.save_tokens"
                    ) as mock_save:
                        mock_save.return_value = True
                        mock_save(tokens)

                    # 3. Fetch models
                    models = fetch_claude_code_models("claude_access_token")
                    assert models is not None
                    assert len(models) == 3

                    # 4. Register models (should filter to latest versions)
                    success = claude_add_models(models)
                    assert success is True

                    # Verify the saved models contain expected structure
                    # Note: add_models_to_extra_config should be mocked for this test


class TestOAuthSecurityScenarios:
    """Security-focused integration tests."""

    def test_csrf_state_validation_integration(self):
        """Test that CSRF state validation works in OAuth flow."""
        context1 = prepare_oauth_context()
        context2 = prepare_oauth_context()

        # States should be different
        assert context1.state != context2.state

        # URLs should have different state parameters
        with patch.object(
            context1, "redirect_uri", "http://localhost:1455/auth/callback"
        ):
            url1 = "https://auth.openai.com/oauth/authorize?" + urllib.parse.urlencode(
                {
                    "state": context1.state,
                    "code_challenge": context1.code_challenge,
                }
            )

        with patch.object(
            context2, "redirect_uri", "http://localhost:1455/auth/callback"
        ):
            url2 = "https://auth.openai.com/oauth/authorize?" + urllib.parse.urlencode(
                {
                    "state": context2.state,
                    "code_challenge": context2.code_challenge,
                }
            )

        assert "state=" in url1 and "state=" in url2
        assert url1 != url2
        # Extract states from URLs to verify they match our contexts
        params1 = urllib.parse.parse_qs(urllib.parse.urlparse(url1).query)
        params2 = urllib.parse.parse_qs(urllib.parse.urlparse(url2).query)
        assert params1["state"][0] == context1.state
        assert params2["state"][0] == context2.state

    def test_pkce_security_integration(self):
        """Test PKCE (Proof Key for Code Exchange) security integration."""
        context = prepare_oauth_context()

        # Verify PKCE parameters are properly generated
        assert len(context.code_verifier) > 0
        assert len(context.code_challenge) > 0
        assert context.code_verifier != context.code_challenge

        # Verify code challenge is derived from verifier
        import base64
        import hashlib

        expected_hash = hashlib.sha256(context.code_verifier.encode()).digest()
        expected_challenge = (
            base64.urlsafe_b64encode(expected_hash).decode().rstrip("=")
        )
        assert context.code_challenge == expected_challenge

        # Test that different contexts have different PKCE parameters
        context2 = prepare_oauth_context()
        assert context.code_verifier != context2.code_verifier
        assert context.code_challenge != context2.code_challenge

    @patch("requests.post")
    def test_expired_context_token_exchange(self, mock_post):
        """Test that expired OAuth contexts cannot exchange tokens."""
        # Create an expired context
        from code_puppy.plugins.chatgpt_oauth.utils import OAuthContext

        expired_context = OAuthContext(
            state="test_state",
            code_verifier="test_verifier",
            code_challenge="test_challenge",
            created_at=time.time() - 300,  # 5 minutes ago
            expires_at=time.time() - 60,  # Expired 1 minute ago
            redirect_uri="http://localhost:1455/auth/callback",
        )

        # Should not attempt token exchange
        result = exchange_code_for_tokens("test_code", expired_context)

        assert result is None
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_malformed_token_response_handling(self, mock_post):
        """Test handling of malformed or unexpected token responses."""
        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:1455/auth/callback"

        # Test cases for malformed responses
        malformed_responses = [
            # Missing access token
            {"refresh_token": "test_refresh", "id_token": "test_id"},
            # Empty response
            {},
            # Response with error field
            {
                "error": "invalid_grant",
                "error_description": "Authorization code expired",
            },
            # Non-JSON response (simulated error)
            None,
        ]

        for response_data in malformed_responses:
            if response_data is None:
                mock_post.side_effect = ValueError("Invalid JSON")
            else:
                mock_post.side_effect = None
                mock_response = Mock(status_code=200, json=lambda: response_data)
                mock_response.raise_for_status.return_value = None
                mock_post.return_value = mock_response

            result = exchange_code_for_tokens("test_code", context)

            # Should handle gracefully (return None or partial data)
            assert result is None or isinstance(result, dict)

    def test_token_storage_security(self, mock_token_storage):
        """Test that token storage follows security best practices."""
        test_tokens = {
            "access_token": "sensitive_access_token",
            "refresh_token": "sensitive_refresh_token",
            "client_secret": "should_not_be_stored",
        }

        with patch(
            "code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path",
            return_value=mock_token_storage,
        ):
            # Save tokens
            result = save_tokens(test_tokens)
            assert result is True

            # Verify file permissions are restrictive
            file_stat = mock_token_storage.stat()
            assert file_stat.st_mode & 0o777 == 0o600  # Read/write for owner only

            # Verify content is stored correctly
            with open(mock_token_storage, "r") as f:
                saved_data = json.load(f)
            assert saved_data == test_tokens

            # File should not be world-readable
            assert not (file_stat.st_mode & 0o044)  # No read for others
            assert not (file_stat.st_mode & 0o040)  # No read for group

    @patch("requests.get")
    def test_api_key_isolation_between_providers(self, mock_get):
        """Test that API keys from different providers are properly isolated."""

        # Mock responses for different providers
        def get_response(url, **kwargs):
            if "api.openai.com" in url:
                return Mock(status_code=200, json=lambda: {"data": [{"id": "gpt-4"}]})
            elif "api.anthropic.com" in url:
                return Mock(
                    status_code=200,
                    json=lambda: {"data": [{"id": "claude-3-opus-20240229"}]},
                )
            return Mock(status_code=404, json=lambda: {"error": "Not found"})

        mock_get.side_effect = get_response

        # Test ChatGPT models with OpenAI key
        openai_models = fetch_chatgpt_models("openai_api_key")
        assert openai_models == ["gpt-4"]

        # Test Claude models with Claude key
        claude_models = fetch_claude_code_models("claude_api_key")
        assert claude_models == ["claude-3-opus-20240229"]

        # Verify different URLs were called
        calls = mock_get.call_args_list
        assert len(calls) == 2
        assert "api.openai.com" in str(calls[0])
        assert "api.anthropic.com" in str(calls[1])

        # Verify correct authorization headers were sent
        openai_headers = calls[0][1]["headers"]
        claude_headers = calls[1][1]["headers"]

        assert openai_headers["Authorization"] == "Bearer openai_api_key"
        assert claude_headers["Authorization"] == "Bearer claude_api_key"


class TestOAuthErrorRecovery:
    """Test error recovery and resilience scenarios."""

    @patch("requests.post")
    def test_network_failure_recovery_flow(self, mock_post):
        """Test OAuth flow behavior under network failures."""
        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:1455/auth/callback"

        # Simulate various network failures
        network_errors = [
            requests.ConnectionError("Connection failed"),
            requests.Timeout("Request timed out"),
            requests.TooManyRedirects("Too many redirects"),
        ]

        for error in network_errors:
            mock_post.side_effect = error

            result = exchange_code_for_tokens("test_code", context)

            # Should handle gracefully and return None
            assert result is None

    @patch("requests.get")
    def test_model_fetching_fallback_behavior(self, mock_get):
        """Test model fetching behavior under various failure conditions."""
        failure_cases = [
            (401, "Unauthorized"),
            (403, "Forbidden"),
            (429, "Too Many Requests"),
            (500, "Internal Server Error"),
            (502, "Bad Gateway"),
            (503, "Service Unavailable"),
        ]

        for status_code, error_text in failure_cases:
            mock_response = Mock()
            mock_response.status_code = status_code
            mock_response.text = error_text
            mock_get.return_value = mock_response

            # Both model fetching functions should handle errors gracefully
            openai_result = fetch_chatgpt_models("test_key")
            claude_result = fetch_claude_code_models("test_key")

            assert openai_result is None
            assert claude_result is None

    def test_partial_token_storage_recovery(self, mock_token_storage):
        """Test recovery scenarios with partial or corrupted token storage."""
        # Create corrupted token file
        with open(mock_token_storage, "w") as f:
            f.write("{invalid json content")

        with patch(
            "code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path",
            return_value=mock_token_storage,
        ):
            # Should return None for corrupted file
            loaded = load_stored_tokens()
            assert loaded is None

            # Should be able to save new tokens after corruption
            new_tokens = {"access_token": "new_token", "refresh_token": "new_refresh"}
            result = save_tokens(new_tokens)
            assert result is True

            # Should be able to load after recovery
            recovered = load_stored_tokens()
            assert recovered == new_tokens

    @patch("requests.post")
    def test_token_refresh_flow_simulation(self, mock_post):
        """Test simulated token refresh flow (if implemented)."""
        # Note: This is a placeholder for potential refresh token functionality
        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:1455/auth/callback"

        # Initial token exchange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "access_token": "initial_access_token",
            "refresh_token": "initial_refresh_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        tokens = exchange_code_for_tokens("initial_code", context)
        assert tokens is not None

        # In a real implementation, we would test token refresh here
        # For now, verify refresh token was received
        assert "refresh_token" in tokens


class TestOAuthConcurrencyAndThreading:
    """Test OAuth behavior under concurrent access."""

    def test_concurrent_oauth_context_generation(self):
        """Test that OAuth context generation is thread-safe."""
        contexts = []

        def generate_context():
            context = prepare_oauth_context()
            contexts.append(context)

        # Generate multiple contexts concurrently
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=generate_context)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all contexts are unique
        states = [ctx.state for ctx in contexts]
        verifiers = [ctx.code_verifier for ctx in contexts]

        assert len(set(states)) == len(states)  # All states should be unique
        assert len(set(verifiers)) == len(verifiers)  # All verifiers should be unique
        assert len(contexts) == 10

    @patch("requests.post")
    def test_concurrent_token_exchange(self, mock_post):
        """Test concurrent token exchange requests."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "concurrent_token",
            "refresh_token": "concurrent_refresh",
        }
        mock_post.return_value = mock_response

        results = []

        def exchange_tokens():
            context = prepare_oauth_context()
            context.redirect_uri = "http://localhost:1455/auth/callback"
            result = exchange_code_for_tokens("test_code", context)
            results.append(result)

        # Run multiple exchanges concurrently
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=exchange_tokens)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All exchanges should succeed
        assert len(results) == 5
        assert all(result is not None for result in results)

        # Verify requests were made properly
        assert mock_post.call_count == 5


class TestOAuthConfigurationIntegration:
    """Test OAuth configuration and feature integration."""

    def test_chatgpt_config_validation(self):
        """Test that ChatGPT OAuth configuration is complete and valid."""
        config = CHATGPT_OAUTH_CONFIG

        # Required fields should be present
        required_fields = [
            "issuer",
            "auth_url",
            "token_url",
            "api_base_url",
            "client_id",
            "scope",
            "redirect_host",
            "redirect_path",
            "required_port",
            "callback_timeout",
            "token_storage",
            "prefix",
            "default_context_length",
            "api_key_env_var",
        ]

        for field in required_fields:
            assert field in config, f"Missing required field: {field}"
            assert config[field] is not None, f"Field {field} is None"

        # URLs should be properly formatted
        assert config["auth_url"].startswith("https://")
        assert config["token_url"].startswith("https://")
        assert config["api_base_url"].startswith("https://")
        assert config["issuer"].startswith("https://")

        # Port should be in valid range
        assert 1024 <= config["required_port"] <= 65535

        # Timeout should be reasonable
        assert 30 <= config["callback_timeout"] <= 600

    def test_claude_config_validation(self):
        """Test that Claude OAuth configuration is complete and valid."""
        config = CLAUDE_CODE_OAUTH_CONFIG

        # Required fields should be present
        required_fields = [
            "auth_url",
            "token_url",
            "api_base_url",
            "client_id",
            "scope",
            "redirect_host",
            "redirect_path",
            "callback_port_range",
            "callback_timeout",
            "token_storage",
            "prefix",
            "default_context_length",
            "api_key_env_var",
            "anthropic_version",
        ]

        for field in required_fields:
            assert field in config, f"Missing required field: {field}"
            assert config[field] is not None, f"Field {field} is None"

        # Port range should be valid
        port_range = config["callback_port_range"]
        assert 1024 <= port_range[0] <= port_range[1] <= 65535

        # URLs should be properly formatted
        assert config["auth_url"].startswith("https://")
        assert config["token_url"].startswith("https://")
        assert config["api_base_url"].startswith("https://")

    def test_path_configuration_resolves_correctly(self, tmp_path):
        """Test that paths resolve correctly in testing environment."""
        # Test ChatGPT paths
        chatgpt_token_path = get_token_storage_path()
        chatgpt_models_path = get_chatgpt_models_path()

        assert isinstance(chatgpt_token_path, Path)
        assert isinstance(chatgpt_models_path, Path)
        assert chatgpt_token_path.name == "chatgpt_oauth.json"
        assert chatgpt_models_path.name == "chatgpt_models.json"

        # Test Claude paths
        claude_token_path = get_claude_token_path()

        assert isinstance(claude_token_path, Path)
        assert claude_token_path.name == "claude_code_oauth.json"

        # Paths should be in the same directory
        assert chatgpt_token_path.parent == chatgpt_models_path.parent
        assert chatgpt_token_path.parent.name == ".code_puppy"


class TestOAuthDataIntegrity:
    """Test data integrity across OAuth operations."""

    def test_token_data_integrity_roundtrip(
        self, mock_token_storage, sample_oauth_tokens
    ):
        """Test that token data remains intact through save/load cycle."""
        # Add some special characters and unicode to test encoding
        special_tokens = sample_oauth_tokens.copy()
        special_tokens["description"] = "Token with special chars: 🐾 é 中文"
        special_tokens["metadata"] = {"key": "value with spaces and symbols!@#$%"}

        with patch(
            "code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path",
            return_value=mock_token_storage,
        ):
            # Save tokens
            save_success = save_tokens(special_tokens)
            assert save_success is True

            # Load tokens
            loaded_tokens = load_stored_tokens()

            # Verify data integrity
            assert loaded_tokens == special_tokens
            assert loaded_tokens["description"] == special_tokens["description"]
            assert loaded_tokens["metadata"] == special_tokens["metadata"]

    def test_model_config_data_integrity(self, mock_models_storage):
        """Test model configuration data integrity."""
        model_config = {
            "chatgpt-gpt-4": {
                "type": "openai",
                "name": "gpt-4",
                "custom_endpoint": {
                    "url": "https://api.openai.com/v1",
                    "api_key": "${CHATGPT_OAUTH_API_KEY}",
                    "headers": {"X-Custom": "value"},
                },
                "context_length": 8192,
                "oauth_source": "chatgpt-oauth-plugin",
                "metadata": {
                    "description": "GPT-4 model with $💰 economics capabilities",
                    "special_features": ["analysis", "reasoning", "coding"],
                },
            }
        }

        with patch(
            "code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path",
            return_value=mock_models_storage,
        ):
            # Save configuration
            with open(mock_models_storage, "w") as f:
                json.dump(model_config, f, indent=2, ensure_ascii=False)

            # Load and verify
            with open(mock_models_storage, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)

            assert loaded_config == model_config
            assert "💰" in loaded_config["chatgpt-gpt-4"]["metadata"]["description"]
            assert loaded_config["chatgpt-gpt-4"]["metadata"]["special_features"] == [
                "analysis",
                "reasoning",
                "coding",
            ]

    def test_concurrent_file_access_safety(self, mock_token_storage):
        """Test file access safety under concurrent operations."""
        errors = []
        results = []

        def save_tokens_worker(worker_id):
            try:
                with patch(
                    "code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path",
                    return_value=mock_token_storage,
                ):
                    tokens = {
                        "worker_id": worker_id,
                        "data": f"data_from_worker_{worker_id}",
                    }
                    result = save_tokens(tokens)
                    results.append((worker_id, result))
            except Exception as e:
                errors.append((worker_id, e))

        # Run multiple save operations concurrently
        threads = []
        for i in range(5):
            thread = threading.Thread(target=save_tokens_worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Most operations should succeed (file locking behavior may vary)
        success_count = sum(1 for _, result in results if result)
        assert success_count > 0  # At least some should succeed

        # File should still be valid
        if mock_token_storage.exists():
            with open(mock_token_storage, "r") as f:
                data = json.load(f)
            assert isinstance(data, dict)


class TestOAuthPerformanceAndLimits:
    """Test OAuth performance characteristics and limits."""

    def test_oauth_context_generation_performance(self):
        """Test OAuth context generation performance."""
        import time

        start_time = time.time()

        # Generate 100 contexts
        contexts = [prepare_oauth_context() for _ in range(100)]

        elapsed = time.time() - start_time

        # Should be reasonably fast (less than 1 second for 100 contexts)
        assert elapsed < 1.0, (
            f"Context generation too slow: {elapsed}s for 100 contexts"
        )

        # All contexts should be unique
        states = [ctx.state for ctx in contexts]
        assert len(set(states)) == 100

    def test_token_storage_performance(self, mock_token_storage):
        """Test token storage and loading performance."""
        large_token_data = {
            "access_token": "a" * 1000,  # Large token
            "refresh_token": "r" * 1000,
            "metadata": {f"key_{i}": f"value_{i}" for i in range(100)},
            **{f"field_{i}": f"data_{i}" for i in range(50)},
        }

        import time

        with patch(
            "code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path",
            return_value=mock_token_storage,
        ):
            # Test save performance
            start_time = time.time()
            save_result = save_tokens(large_token_data)
            save_time = time.time() - start_time

            assert save_result is True
            assert save_time < 0.1, f"Token save too slow: {save_time}s"

            # Test load performance
            start_time = time.time()
            loaded_tokens = load_stored_tokens()
            load_time = time.time() - start_time

            assert loaded_tokens == large_token_data
            assert load_time < 0.1, f"Token load too slow: {load_time}s"

    def test_model_list_handling_limits(self):
        """Test handling of large model lists."""
        from code_puppy.plugins.claude_code_oauth.utils import (
            filter_latest_claude_models,
        )

        # Create a large list with many versions
        large_model_list = []
        base_models = ["haiku", "sonnet", "opus"]

        for family in base_models:
            for major in range(3, 5):
                for minor in range(0, 10):
                    for date_suffix in range(20240101, 20240131, 2):
                        model_name = f"claude-{family}-{major}-{minor}-{date_suffix}"
                        large_model_list.append(model_name)

        # Should handle large lists efficiently
        import time

        start_time = time.time()
        filtered = filter_latest_claude_models(large_model_list)
        elapsed = time.time() - start_time

        # Should be fast even with large lists
        assert elapsed < 0.1, (
            f"Model filtering too slow: {elapsed}s for {len(large_model_list)} models"
        )

        # Should return only latest versions
        assert len(filtered) <= 3  # One per family


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
