"""Comprehensive test coverage for Claude Code OAuth utilities."""

import base64
import hashlib
import json
import secrets
import time
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest
import requests

from code_puppy.plugins.claude_code_oauth.config import (
    CLAUDE_CODE_OAUTH_CONFIG,
)
from code_puppy.plugins.claude_code_oauth.utils import (
    OAuthContext,
    _compute_code_challenge,
    _generate_code_verifier,
    _urlsafe_b64encode,
    add_models_to_extra_config,
    assign_redirect_uri,
    build_authorization_url,
    clear_oauth_context,
    exchange_code_for_tokens,
    fetch_claude_code_models,
    filter_latest_claude_models,
    get_oauth_context,
    load_claude_models,
    load_claude_models_filtered,
    load_stored_tokens,
    parse_authorization_code,
    prepare_oauth_context,
    remove_claude_code_models,
    save_claude_models,
    save_tokens,
)


@pytest.fixture
def temp_token_file(tmp_path):
    """Create a temporary token file for testing."""
    token_file = tmp_path / "test_claude_tokens.json"
    return token_file


@pytest.fixture
def temp_models_file(tmp_path):
    """Create a temporary models file for testing."""
    models_file = tmp_path / "test_claude_models.json"
    return models_file


@pytest.fixture
def sample_token_data():
    """Sample token data for testing."""
    return {
        "access_token": "claude_access_token_123",
        "refresh_token": "claude_refresh_token_456",
        "token_type": "Bearer",
        "scope": "org:create_api_key user:profile user:inference",
        "expires_in": 3600,
    }


class TestUrlSafeB64Encode:
    """Test URL-safe base64 encoding utilities."""

    def test_urlsafe_b64encode_basic(self):
        """Test basic URL-safe base64 encoding."""
        data = b"hello world"
        result = _urlsafe_b64encode(data)

        # Should be URL-safe and without padding
        assert "=" not in result
        assert "+" not in result
        assert "/" not in result

        # Should be valid base64
        decoded = base64.urlsafe_b64decode(result + "=")
        assert decoded == data

    def test_urlsafe_b64encode_empty(self):
        """Test URL-safe base64 encoding of empty data."""
        result = _urlsafe_b64encode(b"")
        assert result == ""

    def test_urlsafe_b64encode_bytes_input(self):
        """Test encoding with bytes input."""
        data = secrets.token_bytes(64)
        result = _urlsafe_b64encode(data)

        assert isinstance(result, str)
        assert len(result) > 0
        assert "=" not in result


class TestCodeVerifierGeneration:
    """Test PKCE code verifier generation for Claude OAuth."""

    def test_generate_code_verifier_format(self):
        """Test code verifier follows correct format."""
        verifier = _generate_code_verifier()

        # Should be a string
        assert isinstance(verifier, str)

        # Should be URL-safe base64 (no +=/ characters)
        assert "=" not in verifier
        assert "+" not in verifier
        assert "/" not in verifier

        # Should be valid base64
        decoded = base64.urlsafe_b64decode(verifier + "==")  # Add padding back
        assert len(decoded) == 64  # Should decode to 64 bytes

    def test_generate_code_verifier_uniqueness(self):
        """Test code verifiers are unique."""
        verifiers = [_generate_code_verifier() for _ in range(10)]

        # All should be unique
        assert len(set(verifiers)) == len(verifiers)

    def test_generate_code_verifier_randomness(self):
        """Test code verifiers appear random."""
        verifier1 = _generate_code_verifier()
        verifier2 = _generate_code_verifier()

        # Should be different
        assert verifier1 != verifier2

        # Should not follow predictable patterns
        assert not verifier1.startswith(verifier2[:10])


class TestCodeChallengeComputation:
    """Test PKCE code challenge computation for Claude OAuth."""

    def test_compute_code_challenge(self):
        """Test code challenge computation from verifier."""
        verifier = "test_verifier_string"
        challenge = _compute_code_challenge(verifier)

        # Should be URL-safe base64
        assert "=" not in challenge
        assert "+" not in challenge
        assert "/" not in challenge

        # Should be different from verifier
        assert challenge != verifier

        # Should be reproducible
        challenge2 = _compute_code_challenge(verifier)
        assert challenge == challenge2

    def test_compute_code_challenge_sha256(self):
        """Test that code challenge is based on SHA256."""
        verifier = "test_verifier_fixed"
        challenge = _compute_code_challenge(verifier)

        # Manually compute expected SHA256
        expected_hash = hashlib.sha256(verifier.encode()).digest()
        expected_challenge = (
            base64.urlsafe_b64encode(expected_hash).decode().rstrip("=")
        )

        assert challenge == expected_challenge


class TestOAuthContext:
    """Test OAuthContext dataclass for Claude OAuth."""

    def test_oauth_context_creation(self):
        """Test OAuthContext creation with required fields."""
        context = OAuthContext(
            state="test_state",
            code_verifier="test_verifier",
            code_challenge="test_challenge",
            created_at=1234567890.0,
        )

        assert context.state == "test_state"
        assert context.code_verifier == "test_verifier"
        assert context.code_challenge == "test_challenge"
        assert context.created_at == 1234567890.0
        assert context.redirect_uri is None

    def test_oauth_context_with_redirect_uri(self):
        """Test OAuthContext creation with redirect URI."""
        context = OAuthContext(
            state="test_state",
            code_verifier="test_verifier",
            code_challenge="test_challenge",
            created_at=time.time(),
            redirect_uri="http://localhost:8765/callback",
        )

        assert context.redirect_uri == "http://localhost:8765/callback"


class TestPrepareOAuthContext:
    """Test OAuth context preparation for Claude OAuth."""

    def test_prepare_oauth_context_structure(self):
        """Test prepared OAuth context has correct structure."""
        with patch("code_puppy.plugins.claude_code_oauth.utils._oauth_context", None):
            context = prepare_oauth_context()

            assert isinstance(context, OAuthContext)
            assert isinstance(context.state, str)
            assert len(context.state) > 0

            assert isinstance(context.code_verifier, str)
            assert len(context.code_verifier) > 0
            assert context.code_verifier != context.state

            assert isinstance(context.code_challenge, str)
            assert len(context.code_challenge) > 0
            assert context.code_challenge != context.code_verifier

            assert isinstance(context.created_at, float)
            assert context.created_at > 0
            assert context.redirect_uri is None

    def test_prepare_oauth_context_caching(self):
        """Test that prepared context is cached globally."""
        import code_puppy.plugins.claude_code_oauth.utils as utils

        # Clear existing context
        utils.clear_oauth_context()

        context1 = utils.prepare_oauth_context()
        context2 = utils.get_oauth_context()

        assert context1 is context2
        assert utils._oauth_context is context1

    def test_prepare_oauth_context_uniqueness(self):
        """Test each prepared context is unique when cleared."""
        # Clear and prepare multiple contexts
        clear_oauth_context()
        context1 = prepare_oauth_context()

        clear_oauth_context()
        context2 = prepare_oauth_context()

        assert context1 != context2
        assert context1.state != context2.state
        assert context1.code_verifier != context2.code_verifier

    def test_get_oauth_context_none(self):
        """Test get_oauth_context returns None when no context exists."""
        clear_oauth_context()

        result = get_oauth_context()

        assert result is None

    def test_clear_oauth_context(self):
        """Test clear_oauth_context removes the cached context."""
        context = prepare_oauth_context()
        assert get_oauth_context() is context

        clear_oauth_context()
        assert get_oauth_context() is None


class TestAssignRedirectUri:
    """Test redirect URI assignment for Claude OAuth."""

    def test_assign_redirect_uri_success(self):
        """Test successful redirect URI assignment."""
        prepare_oauth_context()  # Create context first
        context = get_oauth_context()

        uri = assign_redirect_uri(context, 8765)

        assert uri == "http://localhost:8765/callback"
        assert context is not None
        assert context.redirect_uri == uri

    def test_assign_redirect_uri_no_context(self):
        """Test redirect URI assignment fails without context."""
        clear_oauth_context()

        with pytest.raises(RuntimeError, match="OAuth context cannot be None"):
            assign_redirect_uri(None, 8765)

    def test_assign_redirect_uri_different_port(self):
        """Test redirect URI assignment with different port."""
        prepare_oauth_context()
        context = get_oauth_context()

        uri = assign_redirect_uri(context, 8780)

        assert uri == "http://localhost:8780/callback"

        context = get_oauth_context()
        assert context.redirect_uri == uri


class TestBuildAuthorizationUrl:
    """Test authorization URL building for Claude OAuth."""

    def test_build_authorization_url_success(self):
        """Test successful authorization URL building."""
        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:8765/callback"

        url = build_authorization_url(context)

        # Should contain base URL
        assert url.startswith("https://claude.ai/oauth/authorize?")

        # Should contain all required parameters
        assert "response_type=code" in url
        assert f"client_id={CLAUDE_CODE_OAUTH_CONFIG['client_id']}" in url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback" in url
        assert "scope=org%3Acreate_api_key+user%3Aprofile+user%3Ainference" in url
        assert "code=true" in url
        assert f"code_challenge={context.code_challenge}" in url
        assert "code_challenge_method=S256" in url
        assert f"state={context.state}" in url

    def test_build_authorization_url_no_redirect_uri(self):
        """Test authorization URL building fails without redirect URI."""
        context = prepare_oauth_context()
        # Don't set redirect_uri

        with pytest.raises(RuntimeError, match="Redirect URI has not been assigned"):
            build_authorization_url(context)


class TestParseAuthorizationCode:
    """Test authorization code parsing for Claude OAuth."""

    def test_parse_authorization_code_basic(self):
        """Test parsing basic authorization code."""
        code, state = parse_authorization_code("test_code_123")

        assert code == "test_code_123"
        assert state is None

    def test_parse_authorization_code_with_state(self):
        """Test parsing authorization code with state."""
        input_str = "test_code_123#test_state_456"
        code, state = parse_authorization_code(input_str)

        assert code == "test_code_123"
        assert state == "test_state_456"

    def test_parse_authorization_code_space_separated(self):
        """Test parsing space-separated code and state."""
        input_str = "test_code_123 test_state_456"
        code, state = parse_authorization_code(input_str)

        assert code == "test_code_123"
        assert state == "test_state_456"

    def test_parse_authorization_code_with_trimming(self):
        """Test parsing with whitespace trimming."""
        input_str = "  test_code_123  #  test_state_456  "
        code, state = parse_authorization_code(input_str)

        assert code == "test_code_123"
        assert state == "test_state_456"

    def test_parse_authorization_code_empty(self):
        """Test parsing empty string raises error."""
        with pytest.raises(ValueError, match="Authorization code cannot be empty"):
            parse_authorization_code("")

    def test_parse_authorization_code_whitespace_only(self):
        """Test parsing whitespace-only string raises error."""
        with pytest.raises(ValueError, match="Authorization code cannot be empty"):
            parse_authorization_code("   ")

    def test_parse_authorization_code_state_missing(self):
        """Test parsing when state is not provided."""
        # With # but no state after
        code, state = parse_authorization_code("test_code_123#")

        assert code == "test_code_123"
        assert state is None  # Empty string becomes None


class TestTokenStorage:
    """Test token storage and retrieval for Claude OAuth."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path")
    def test_load_stored_tokens_success(self, mock_get_path, temp_token_file):
        """Test successful loading of stored tokens."""
        mock_get_path.return_value = temp_token_file

        test_tokens = {
            "access_token": "claude_access_token",
            "refresh_token": "claude_refresh_token",
            "expires_at": "2023-12-31T23:59:59Z",
        }

        with open(temp_token_file, "w") as f:
            json.dump(test_tokens, f)

        result = load_stored_tokens()

        assert result == test_tokens

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path")
    def test_load_stored_tokens_file_not_exists(self, mock_get_path):
        """Test loading tokens when file doesn't exist returns None."""
        mock_get_path.return_value = Path("/nonexistent/file.json")

        result = load_stored_tokens()

        assert result is None

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path")
    def test_save_stored_tokens_success(self, mock_get_path, temp_token_file):
        """Test successful saving of stored tokens."""
        mock_get_path.return_value = temp_token_file

        test_tokens = {
            "access_token": "new_claude_token",
            "refresh_token": "new_claude_refresh",
        }

        result = save_tokens(test_tokens)

        assert result is True

        # Verify file was created
        assert temp_token_file.exists()

        with open(temp_token_file, "r") as f:
            saved_data = json.load(f)

        assert saved_data == test_tokens

        # Verify permissions are set to 0o600
        file_stat = temp_token_file.stat()
        assert file_stat.st_mode & 0o777 == 0o600

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path")
    def test_save_stored_tokens_error(self, mock_get_path):
        """Test saving tokens with error returns False."""
        mock_get_path.return_value = Path("/root/protected.json")

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            result = save_tokens({"test": "data"})
            assert result is False


class TestModelStorage:
    """Test model configuration storage for Claude OAuth."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path")
    def test_load_claude_models_success(self, mock_get_path, temp_models_file):
        """Test successful loading of Claude models configuration."""
        mock_get_path.return_value = temp_models_file

        test_models = {
            "claude-code-claude-3-haiku-20240307": {
                "type": "claude_code",
                "name": "claude-3-haiku-20240307",
                "context_length": 200000,
            },
        }

        with open(temp_models_file, "w") as f:
            json.dump(test_models, f)

        result = load_claude_models()

        assert result == test_models

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path")
    def test_load_claude_models_filtered_oauth_models(
        self, mock_get_path, temp_models_file
    ):
        """Test loading and filtering Claude OAuth models."""
        mock_get_path.return_value = temp_models_file

        test_models = {
            "claude-code-claude-haiku-3-5-20241022": {
                "type": "claude_code",
                "name": "claude-haiku-3-5-20241022",
                "oauth_source": "claude-code-plugin",
            },
            "claude-code-claude-sonnet-3-5-20241022": {
                "type": "claude_code",
                "name": "claude-sonnet-3-5-20241022",
                "oauth_source": "claude-code-plugin",
            },
            "claude-code-claude-opus-3-5-20241022": {
                "type": "claude_code",
                "name": "claude-opus-3-5-20241022",
                "oauth_source": "claude-code-plugin",
            },
            "claude-code-old-haiku": {
                "type": "claude_code",
                "name": "claude-haiku-3-0-20240229",
                "oauth_source": "claude-code-plugin",
            },
            "non-oauth-model": {
                "type": "other",
                "name": "some-other-model",
            },
        }

        with open(temp_models_file, "w") as f:
            json.dump(test_models, f)

        result = load_claude_models_filtered()

        # Should filter to only latest models
        assert "claude-code-claude-haiku-3-5-20241022" in result  # Latest haiku
        assert "claude-code-claude-sonnet-3-5-20241022" in result  # Latest sonnet
        assert "claude-code-claude-opus-3-5-20241022" in result  # Latest opus
        assert "claude-code-old-haiku" not in result  # Filtered out as older version
        assert "non-oauth-model" not in result  # Not OAuth source

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path")
    def test_save_claude_models_success(self, mock_get_path, temp_models_file):
        """Test successful saving of Claude models configuration."""
        mock_get_path.return_value = temp_models_file

        test_models = {
            "claude-code-new-model": {
                "type": "claude_code",
                "name": "claude-3-5-sonnet-20241022",
                "context_length": 200000,
            },
        }

        result = save_claude_models(test_models)

        assert result is True

        with open(temp_models_file, "r") as f:
            saved_data = json.load(f)

        assert saved_data == test_models


class TestTokenExchange:
    """Test token exchange functionality for Claude OAuth."""

    @patch("requests.post")
    def test_exchange_code_for_tokens_success(self, mock_post):
        """Test successful token exchange."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "claude_access_token",
            "refresh_token": "claude_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:8765/callback"

        result = exchange_code_for_tokens("test_auth_code", context)

        assert result is not None
        assert result["access_token"] == "claude_access_token"
        assert result["refresh_token"] == "claude_refresh_token"

        # Verify request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == CLAUDE_CODE_OAUTH_CONFIG["token_url"]

        # Check JSON payload
        json_data = call_args[1]["json"]
        assert json_data["grant_type"] == "authorization_code"
        assert json_data["code"] == "test_auth_code"
        assert json_data["client_id"] == CLAUDE_CODE_OAUTH_CONFIG["client_id"]
        assert json_data["state"] == context.state
        assert json_data["code_verifier"] == context.code_verifier
        assert json_data["redirect_uri"] == context.redirect_uri

        # Check headers
        headers = call_args[1]["headers"]
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"
        assert headers["anthropic-beta"] == "oauth-2025-04-20"

    @patch("requests.post")
    def test_exchange_code_for_tokens_http_error(self, mock_post):
        """Test token exchange handles HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:8765/callback"

        result = exchange_code_for_tokens("invalid_code", context)

        assert result is None

    @patch("requests.post")
    def test_exchange_code_for_tokens_network_error(self, mock_post):
        """Test token exchange handles network errors."""
        mock_post.side_effect = requests.ConnectionError("Network error")

        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:8765/callback"

        result = exchange_code_for_tokens("test_code", context)

        assert result is None

    def test_exchange_code_for_tokens_missing_redirect_uri(self):
        """Test token exchange fails without redirect URI."""
        context = prepare_oauth_context()
        # Don't set redirect_uri

        with pytest.raises(RuntimeError, match="Redirect URI missing"):
            exchange_code_for_tokens("test_code", context)


class TestFilterLatestClaudeModels:
    """Test Claude model filtering to only latest versions."""

    def test_filter_latest_claude_models_basic(self):
        """Test basic model filtering."""
        models = [
            "claude-haiku-3-5-20241022",
            "claude-haiku-3-0-20240229",  # Older haiku
            "claude-sonnet-3-5-20241022",
            "claude-sonnet-3-0-20240229",  # Older sonnet
            "claude-opus-3-0-20240229",
            "claude-opus-2-0-20240101",  # Older opus
        ]

        result = filter_latest_claude_models(models)

        # Should only return latest versions, preserving original order if possible
        expected = [
            "claude-haiku-3-5-20241022",
            "claude-sonnet-3-5-20241022",
            "claude-opus-3-0-20240229",
        ]
        # Order might not be preserved, so we check as sets
        assert set(result) == set(expected)
        assert len(result) == 3

    def test_filter_latest_claude_models_dot_version_format(self):
        """Test filtering with dot version format."""
        models = [
            "claude-haiku-3.5-20241022",
            "claude-haiku-3.0-20240229",  # Older
            "claude-sonnet-4.0-20250929",
            "claude-sonnet-3.5-20241022",  # Older
        ]

        result = filter_latest_claude_models(models)

        expected = ["claude-haiku-3.5-20241022", "claude-sonnet-4.0-20250929"]
        assert set(result) == set(expected)

    def test_filter_latest_claude_models_version_comparison(self):
        """Test proper version comparison (major > minor > date)."""
        models = [
            "claude-sonnet-3-5-20241022",  # 3.5
            "claude-sonnet-4-0-20240101",  # 4.0 but older date - should be newer due to major
            "claude-sonnet-3-6-20241023",  # 3.6 newer minor but same major
            "claude-sonnet-3-5-20241023",  # Same version but newer date
        ]

        result = filter_latest_claude_models(models)

        # 4.0 should win over 3.x due to major version
        assert "claude-sonnet-4-0-20240101" in result
        assert len(result) == 1

    def test_filter_latest_claude_models_invalid_names(self):
        """Test filtering ignores invalid model names."""
        models = [
            "claude-haiku-3-5-20241022",
            "invalid-model-name",
            "claude-3-haiku-3-5-20241022",  # Wrong format
            "gpt-4",  # Non-Claude model
            "claude-sonnet-3-5-20241022",
            "random-string",
        ]

        result = filter_latest_claude_models(models)

        # Should only filter valid Claude models
        assert set(result) == {
            "claude-haiku-3-5-20241022",
            "claude-sonnet-3-5-20241022",
        }

    def test_filter_latest_claude_models_empty(self):
        """Test filtering empty list returns empty list."""
        result = filter_latest_claude_models([])
        assert result == []

    def test_filter_latest_claude_models_no_valid_models(self):
        """Test filtering list with no valid models."""
        models = ["gpt-4", "invalid-name", "random-string"]

        result = filter_latest_claude_models(models)

        assert result == []

    def test_filter_latest_claude_models_same_versions_different_dates(self):
        """Test filtering when same version has different dates."""
        models = [
            "claude-haiku-3-5-20241022",
            "claude-haiku-3-5-20241023",  # Same version, newer date
            "claude-sonnet-3-5-20241022",
        ]

        result = filter_latest_claude_models(models)

        # Should pick the newer date for same version
        assert "claude-haiku-3-5-20241023" in result
        assert "claude-sonnet-3-5-20241022" in result
        assert len(result) == 2


class TestFetchClaudeCodeModels:
    """Test Claude Code model fetching functionality."""

    @patch("requests.get")
    def test_fetch_claude_code_models_success(self, mock_get):
        """Test successful model fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "claude-3-opus-20240229"},
                {"id": "claude-3-sonnet-20240229"},
                {"id": "claude-3-haiku-20240307"},
                {"name": "claude-3-5-sonnet-20241022"},  # Different field name
            ]
        }
        mock_get.return_value = mock_response

        result = fetch_claude_code_models("test_access_token")

        assert result == [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-3-5-sonnet-20241022",
        ]

        # Verify request was made correctly
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://api.anthropic.com/v1/models"
        assert call_args[1]["headers"]["Authorization"] == "Bearer test_access_token"
        assert call_args[1]["headers"]["anthropic-beta"] == "oauth-2025-04-20"
        assert call_args[1]["headers"]["anthropic-version"] == "2023-06-01"

    @patch("requests.get")
    def test_fetch_claude_code_models_missing_name_fields(self, mock_get):
        """Test model fetching handles missing name/id fields."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "claude-3-opus-20240229"},
                {},  # Missing both id and name
                {"name": "claude-3-sonnet-20240229"},
                {"id": ""},  # Empty id
                {"name": ""},  # Empty name
            ]
        }
        mock_get.return_value = mock_response

        result = fetch_claude_code_models("test_access_token")

        # Should only include models with non-empty names
        assert result == ["claude-3-opus-20240229", "claude-3-sonnet-20240229"]

    @patch("requests.get")
    def test_fetch_claude_code_models_http_error(self, mock_get):
        """Test model fetching handles HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_get.return_value = mock_response

        result = fetch_claude_code_models("invalid_token")

        assert result is None

    @patch("requests.get")
    def test_fetch_claude_code_models_non_list_data(self, mock_get):
        """Test model fetching handles non-list data field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "not a list"}
        mock_get.return_value = mock_response

        result = fetch_claude_code_models("test_token")

        assert result is None

    @patch("requests.get")
    def test_fetch_claude_code_models_no_data_field(self, mock_get):
        """Test model fetching handles missing data field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "Missing data field"}
        mock_get.return_value = mock_response

        result = fetch_claude_code_models("test_token")

        assert result is None

    @patch("requests.get")
    def test_fetch_claude_code_models_empty_data(self, mock_get):
        """Test model fetching handles empty data list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        result = fetch_claude_code_models("test_token")

        assert result == []  # Return empty list, not None


class TestAddModelsToConfig:
    """Test adding Claude models to configuration."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.save_claude_models")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_add_models_to_extra_config_success(self, mock_load_tokens, mock_save):
        """Test successful addition of models to configuration."""
        mock_load_tokens.return_value = {"access_token": "test_access_token"}
        mock_save.return_value = True

        models = [
            "claude-opus-3-0-20240229",
            "claude-sonnet-3-0-20240229",
            "claude-haiku-3-0-20240307",
            "claude-sonnet-3-5-20241022",  # Latest version
            "claude-haiku-3-5-20241022",  # Latest version
        ]

        result = add_models_to_extra_config(models)

        assert result is True

        # Verify save was called
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]

        # Should contain filtered (latest) models only
        assert "claude-code-claude-opus-3-0-20240229" in saved_config
        assert "claude-code-claude-sonnet-3-5-20241022" in saved_config  # Latest sonnet
        assert "claude-code-claude-haiku-3-5-20241022" in saved_config  # Latest haiku

        # Should not contain older versions
        assert (
            "claude-code-claude-sonnet-3-0-20240229" not in saved_config
        )  # Older sonnet
        assert (
            "claude-code-claude-haiku-3-0-20240307" not in saved_config
        )  # Older haiku

        # Check structure of a saved model
        haiku_config = saved_config["claude-code-claude-haiku-3-5-20241022"]
        assert haiku_config["type"] == "claude_code"
        assert haiku_config["name"] == "claude-haiku-3-5-20241022"
        assert (
            haiku_config["custom_endpoint"]["url"]
            == CLAUDE_CODE_OAUTH_CONFIG["api_base_url"]
        )
        assert haiku_config["custom_endpoint"]["api_key"] == "test_access_token"
        assert haiku_config["custom_endpoint"]["headers"] == {
            "anthropic-beta": "oauth-2025-04-20"
        }
        assert (
            haiku_config["context_length"]
            == CLAUDE_CODE_OAUTH_CONFIG["default_context_length"]
        )
        assert haiku_config["oauth_source"] == "claude-code-plugin"

    @patch("code_puppy.plugins.claude_code_oauth.utils.save_claude_models")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_add_models_to_extra_config_no_tokens(self, mock_load_tokens, mock_save):
        """Test model addition when no tokens are available."""
        mock_load_tokens.return_value = {}
        mock_save.return_value = True

        result = add_models_to_extra_config(["claude-sonnet-3-5-20241022"])

        assert result is True  # Still succeeds, but may have issues

        saved_config = mock_save.call_args[0][0]
        # API key should be empty/missing
        api_key = saved_config["claude-code-claude-sonnet-3-5-20241022"][
            "custom_endpoint"
        ]["api_key"]
        assert api_key == ""  # or None depending on implementation

    @patch("code_puppy.plugins.claude_code_oauth.utils.save_claude_models")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_add_models_to_extra_config_save_failure(self, mock_load_tokens, mock_save):
        """Test model addition fails when save fails."""
        mock_load_tokens.return_value = {"access_token": "test_token"}
        mock_save.return_value = False

        result = add_models_to_extra_config(["claude-sonnet-3-5-20241022"])

        assert result is False

    @patch("code_puppy.plugins.claude_code_oauth.utils.save_claude_models")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_add_models_to_extra_config_load_token_failure(
        self, mock_load_tokens, mock_save
    ):
        """Test model addition handles token loading failure."""
        mock_load_tokens.return_value = None  # Returns None on failure
        mock_save.return_value = True

        result = add_models_to_extra_config(["claude-sonnet-3-5-20241022"])

        assert result is True  # Still tries to save

        saved_config = mock_save.call_args[0][0]
        # API key should be empty string due to graceful handling
        api_key = saved_config["claude-code-claude-sonnet-3-5-20241022"][
            "custom_endpoint"
        ]["api_key"]
        assert api_key == ""


class TestRemoveClaudeCodeModels:
    """Test removing Claude Code models from configuration."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.save_claude_models")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_claude_models")
    def test_remove_claude_code_models_success(self, mock_load, mock_save):
        """Test successful removal of Claude Code models."""
        mock_load.return_value = {
            "claude-code-claude-3-opus-20240229": {
                "name": "claude-3-opus-20240229",
                "oauth_source": "claude-code-plugin",
            },
            "claude-code-claude-3-sonnet-20240229": {
                "name": "claude-3-sonnet-20240229",
                "oauth_source": "claude-code-plugin",
            },
            "custom-claude-model": {
                "name": "custom-claude",
                "type": "other",
            },
        }
        mock_save.return_value = True

        result = remove_claude_code_models()

        assert result == 2  # Two models removed

        # Verify save was called with correct data
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]

        # Should only contain non-OAuth models
        assert "claude-code-claude-3-opus-20240229" not in saved_config
        assert "claude-code-claude-3-sonnet-20240229" not in saved_config
        assert "custom-claude-model" in saved_config

    @patch("code_puppy.plugins.claude_code_oauth.utils.save_claude_models")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_claude_models")
    def test_remove_claude_code_models_no_oauth_models(self, mock_load, mock_save):
        """Test removal when no OAuth models exist."""
        mock_load.return_value = {
            "custom-model-1": {
                "name": "custom1",
                "type": "claude",
                "oauth_source": "other-source",
            },
            "custom-model-2": {
                "name": "custom2",
                "type": "claude_code",
                # No oauth_source field
            },
        }
        mock_save.return_value = True

        result = remove_claude_code_models()

        assert result == 0  # No models removed

    @patch("code_puppy.plugins.claude_code_oauth.utils.save_claude_models")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_claude_models")
    def test_remove_claude_code_models_save_failure(self, mock_load, mock_save):
        """Test model removal fails when save fails."""
        mock_load.return_value = {
            "claude-code-claude-3-opus-20240229": {
                "name": "claude-3-opus-20240229",
                "oauth_source": "claude-code-plugin",
            },
        }
        mock_save.return_value = False

        result = remove_claude_code_models()

        assert result == 0  # Returns 0 on failure

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_claude_models")
    def test_remove_claude_code_models_load_failure(self, mock_load):
        """Test model removal handles load failure gracefully."""
        mock_load.return_value = {}  # Returns empty dict on failure

        result = remove_claude_code_models()

        assert result == 0


class TestErrorHandling:
    """Test comprehensive error handling scenarios."""

    @patch("requests.post")
    def test_exchange_code_for_tokens_various_http_errors(self, mock_post):
        """Test token exchange handles various HTTP error codes."""
        test_cases = [
            (400, "Bad Request"),
            (401, "Unauthorized"),
            (403, "Forbidden"),
            (429, "Too Many Requests"),
            (500, "Internal Server Error"),
            (502, "Bad Gateway"),
            (503, "Service Unavailable"),
        ]

        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:8765/callback"

        for status_code, error_text in test_cases:
            mock_response = Mock()
            mock_response.status_code = status_code
            mock_response.text = error_text
            mock_post.return_value = mock_response

            result = exchange_code_for_tokens("test_code", context)

            assert result is None, f"Should return None for {status_code} error"

    @patch("requests.get")
    def test_fetch_claude_code_models_various_http_errors(self, mock_get):
        """Test model fetching handles various HTTP error codes."""
        test_cases = [
            (400, "Bad Request"),
            (401, "Unauthorized"),
            (403, "Forbidden"),
            (429, "Too Many Requests"),
            (500, "Internal Server Error"),
            (502, "Bad Gateway"),
            (503, "Service Unavailable"),
        ]

        for status_code, error_text in test_cases:
            mock_response = Mock()
            mock_response.status_code = status_code
            mock_response.text = error_text
            mock_get.return_value = mock_response

            result = fetch_claude_code_models("test_token")

            assert result is None, f"Should return None for {status_code} error"

    def test_all_functions_handle_none_inputs_gracefully(self):
        """Test that utility functions handle None inputs gracefully."""
        clear_oauth_context()

        # These should fail appropriately for None inputs
        with pytest.raises(ValueError):
            parse_authorization_code("")
        with pytest.raises(ValueError):
            parse_authorization_code("   ")

        with pytest.raises(RuntimeError):
            assign_redirect_uri(None, 8765)  # type: ignore

        # These should handle None gracefully
        assert get_oauth_context() is None

    def test_filter_models_edge_cases(self):
        """Test model filtering with edge cases."""
        test_cases = [
            # Empty models list
            ([], []),
            # Only invalid names
            (["gpt-4", "invalid", "random"], []),
            # Mixed valid and invalid with newer versions
            (
                [
                    "claude-sonnet-3-5-20241022",
                    "invalid",
                    "claude-sonnet-4-0-20250929",
                    "gpt-4",
                    "claude-sonnet-3-0-20240229",
                ],
                ["claude-sonnet-4-0-20250929"],
            ),
        ]

        for input_models, expected_output in test_cases:
            result = filter_latest_claude_models(input_models)
            assert set(result) == set(expected_output), (
                f"Failed for input: {input_models}"
            )

    def test_assign_redirect_uri_various_ports(self):
        """Test redirect URI assignment with various port ranges."""
        prepare_oauth_context()
        context = get_oauth_context()

        test_ports = [8765, 8770, 8780, 8790, 8795]

        for port in test_ports:
            uri = assign_redirect_uri(context, port)
            assert uri == f"http://localhost:{port}/callback"

            context = get_oauth_context()
            assert context.redirect_uri == uri

    def test_model_storage_permissions_and_errors(self):
        """Test model storage with permission errors and edge cases."""
        # These tests are mainly to ensure error handling doesn't crash
        with patch(
            "code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path",
            return_value=Path("/root/protected.json"),
        ):
            with patch(
                "builtins.open", side_effect=PermissionError("Permission denied")
            ):
                result = save_claude_models({})
                assert result is False

                result = load_claude_models()
                assert result == {}

    def test_token_storage_with_corrupted_json(self):
        """Test token loading with corrupted JSON files."""
        with patch(
            "code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path",
            return_value=Path("/tmp/corrupted.json"),
        ):
            with patch("builtins.open", mock_open(read_data="invalid json {")):
                result = load_stored_tokens()
                assert result is None
