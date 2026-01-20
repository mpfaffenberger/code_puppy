"""Comprehensive test suite for the Claude Code OAuth plugin.

Covers OAuth flow, token handling, API integration, error paths,
model discovery, and CLI command handlers with comprehensive mocking.
"""

import json
import time
from unittest.mock import Mock, patch

import pytest
import requests

from code_puppy.plugins.claude_code_oauth.config import (
    CLAUDE_CODE_OAUTH_CONFIG,
)
from code_puppy.plugins.claude_code_oauth.utils import (
    OAuthContext,
    _calculate_expires_at,
    _compute_code_challenge,
    _generate_code_verifier,
    assign_redirect_uri,
    build_authorization_url,
    clear_oauth_context,
    exchange_code_for_tokens,
    get_oauth_context,
    get_valid_access_token,
    is_token_expired,
    load_stored_tokens,
    parse_authorization_code,
    prepare_oauth_context,
    refresh_access_token,
    save_tokens,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_token_response():
    """Sample OAuth token response from server."""
    return {
        "access_token": "claude_access_token_test_12345",
        "refresh_token": "claude_refresh_token_test_67890",
        "token_type": "Bearer",
        "scope": "org:create_api_key user:profile user:inference",
        "expires_in": 3600,
    }


@pytest.fixture
def sample_token_data():
    """Sample stored token data.

    Uses 7200 seconds (2 hours) for expires_at to be safely outside
    the 1-hour proactive refresh buffer (TOKEN_REFRESH_BUFFER_SECONDS=3600).
    """
    now = time.time()
    return {
        "access_token": "claude_access_token_test_12345",
        "refresh_token": "claude_refresh_token_test_67890",
        "token_type": "Bearer",
        "scope": "org:create_api_key user:profile user:inference",
        "expires_in": 7200,
        "expires_at": now + 7200,  # 2 hours, safely outside 1-hour refresh buffer
    }


@pytest.fixture
def expired_token_data():
    """Sample expired token data."""
    return {
        "access_token": "claude_access_token_test_12345",
        "refresh_token": "claude_refresh_token_test_67890",
        "expires_at": time.time() - 100,  # Expired 100 seconds ago
    }


# ============================================================================
# PKCE FLOW TESTS
# ============================================================================


class TestPKCEGeneration:
    """Test PKCE (Proof Key for Public Clients) generation and validation."""

    def test_generate_code_verifier(self):
        """Test code verifier generation."""
        verifier = _generate_code_verifier()
        assert isinstance(verifier, str)
        assert len(verifier) > 0
        # Should be URL-safe base64 (no padding, no +/)
        assert "+" not in verifier
        assert "/" not in verifier
        assert "=" not in verifier

    def test_code_verifier_determinism(self):
        """Test that code verifier generation is random."""
        v1 = _generate_code_verifier()
        v2 = _generate_code_verifier()
        assert v1 != v2

    def test_compute_code_challenge(self):
        """Test PKCE code challenge computation."""
        verifier = "test_verifier_value"
        challenge = _compute_code_challenge(verifier)
        assert isinstance(challenge, str)
        assert len(challenge) > 0
        # Challenge should be valid base64
        assert "+" not in challenge
        assert "/" not in challenge
        assert "=" not in challenge

    def test_code_challenge_determinism(self):
        """Test that same verifier produces same challenge."""
        verifier = "same_test_value"
        c1 = _compute_code_challenge(verifier)
        c2 = _compute_code_challenge(verifier)
        assert c1 == c2

    def test_code_challenge_different_verifiers(self):
        """Test that different verifiers produce different challenges."""
        c1 = _compute_code_challenge("verifier1")
        c2 = _compute_code_challenge("verifier2")
        assert c1 != c2


# ============================================================================
# OAUTH CONTEXT TESTS
# ============================================================================


class TestOAuthContext:
    """Test OAuth context creation and management."""

    def test_prepare_oauth_context_creates_context(self):
        """Test that preparing OAuth context creates valid context."""
        clear_oauth_context()
        context = prepare_oauth_context()

        assert context is not None
        assert isinstance(context, OAuthContext)
        assert context.state
        assert context.code_verifier
        assert context.code_challenge
        assert context.created_at > 0
        assert context.redirect_uri is None  # Not assigned yet

    def test_prepare_oauth_context_caches(self):
        """Test that context is cached."""
        clear_oauth_context()
        context1 = prepare_oauth_context()
        context2 = get_oauth_context()

        assert context1 is context2

    def test_assign_redirect_uri(self):
        """Test assigning redirect URI to context."""
        clear_oauth_context()
        context = prepare_oauth_context()
        uri = assign_redirect_uri(context, 8765)

        assert "localhost:8765" in uri
        assert "callback" in uri
        assert context.redirect_uri == uri

    def test_assign_redirect_uri_different_ports(self):
        """Test assigning different ports produces different URIs."""
        clear_oauth_context()
        context = prepare_oauth_context()
        uri1 = assign_redirect_uri(context, 8765)

        clear_oauth_context()
        context = prepare_oauth_context()
        uri2 = assign_redirect_uri(context, 8766)

        assert "8765" in uri1
        assert "8766" in uri2

    def test_build_authorization_url(self):
        """Test building OAuth authorization URL."""
        clear_oauth_context()
        context = prepare_oauth_context()
        assign_redirect_uri(context, 8765)
        auth_url = build_authorization_url(context)

        assert "https://" in auth_url
        assert "response_type=code" in auth_url
        assert f"client_id={CLAUDE_CODE_OAUTH_CONFIG['client_id']}" in auth_url
        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url
        assert f"state={context.state}" in auth_url
        assert "redirect_uri=" in auth_url

    def test_build_authorization_url_requires_redirect_uri(self):
        """Test that authorization URL requires redirect URI."""
        clear_oauth_context()
        context = prepare_oauth_context()
        # Don't assign redirect_uri

        with pytest.raises(RuntimeError, match="Redirect URI"):
            build_authorization_url(context)


# ============================================================================
# AUTHORIZATION CODE PARSING
# ============================================================================


class TestAuthorizationCodeParsing:
    """Test parsing authorization codes in various formats."""

    def test_parse_authorization_code_with_state_suffix(self):
        """Test parsing code with state suffix (code#state format)."""
        code, state = parse_authorization_code("ABC123#STATE456")
        assert code == "ABC123"
        assert state == "STATE456"

    def test_parse_authorization_code_space_separated(self):
        """Test parsing space-separated code and state."""
        code, state = parse_authorization_code("ABC123 STATE456")
        assert code == "ABC123"
        assert state == "STATE456"

    def test_parse_authorization_code_bare(self):
        """Test parsing bare code without state."""
        code, state = parse_authorization_code("ABC123")
        assert code == "ABC123"
        assert state is None

    def test_parse_authorization_code_strips_whitespace(self):
        """Test that whitespace is stripped."""
        code, state = parse_authorization_code("  ABC123#STATE456  ")
        assert code == "ABC123"
        assert state == "STATE456"

    def test_parse_authorization_code_empty_raises(self):
        """Test that empty code raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_authorization_code("")


# ============================================================================
# TOKEN STORAGE AND LOADING
# ============================================================================


class TestTokenStorage:
    """Test token saving and loading."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path")
    def test_save_tokens_creates_file(self, mock_path, tmp_path, sample_token_data):
        """Test that tokens are saved to file."""
        token_file = tmp_path / "tokens.json"
        mock_path.return_value = token_file

        result = save_tokens(sample_token_data)

        assert result is True
        assert token_file.exists()
        with open(token_file) as f:
            saved_data = json.load(f)
        assert saved_data == sample_token_data

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path")
    def test_save_tokens_sets_permissions(self, mock_path, tmp_path, sample_token_data):
        """Test that saved token file has restricted permissions."""
        token_file = tmp_path / "tokens.json"
        mock_path.return_value = token_file

        save_tokens(sample_token_data)

        # Check file permissions (0o600 = rw-------)
        stat_info = token_file.stat()
        mode = stat_info.st_mode & 0o777
        assert mode == 0o600

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path")
    def test_load_stored_tokens_existing_file(
        self, mock_path, tmp_path, sample_token_data
    ):
        """Test loading tokens from existing file."""
        token_file = tmp_path / "tokens.json"
        token_file.write_text(json.dumps(sample_token_data))
        mock_path.return_value = token_file

        loaded = load_stored_tokens()

        assert loaded == sample_token_data

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path")
    def test_load_stored_tokens_nonexistent_file(self, mock_path, tmp_path):
        """Test loading tokens when file doesn't exist."""
        token_file = tmp_path / "nonexistent.json"
        mock_path.return_value = token_file

        loaded = load_stored_tokens()

        assert loaded is None

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path")
    def test_load_stored_tokens_corrupted_file(self, mock_path, tmp_path):
        """Test loading corrupted JSON file."""
        token_file = tmp_path / "corrupted.json"
        token_file.write_text("{ invalid json")
        mock_path.return_value = token_file

        loaded = load_stored_tokens()

        assert loaded is None

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_token_storage_path")
    def test_save_tokens_write_failure(self, mock_path):
        """Test save tokens handles write failures."""
        mock_path.side_effect = Exception("Permission denied")

        result = save_tokens({"test": "data"})

        assert result is False


# ============================================================================
# TOKEN EXPIRY AND REFRESH
# ============================================================================


class TestTokenExpiry:
    """Test token expiry checking and refresh logic."""

    def test_is_token_expired_not_expired(self, sample_token_data):
        """Test that fresh token is not expired."""
        assert is_token_expired(sample_token_data) is False

    def test_is_token_expired_actually_expired(self, expired_token_data):
        """Test that old token is detected as expired."""
        assert is_token_expired(expired_token_data) is True

    def test_is_token_expired_no_expires_at(self):
        """Test token without expires_at is not expired."""
        token_data = {"access_token": "test"}
        assert is_token_expired(token_data) is False

    def test_is_token_expired_invalid_expires_at(self):
        """Test token with invalid expires_at doesn't crash."""
        token_data = {"expires_at": "not_a_number"}
        assert is_token_expired(token_data) is False

    def test_calculate_expires_at_valid(self):
        """Test calculating expiry time."""
        before = time.time()
        expires_at = _calculate_expires_at(3600)
        after = time.time()

        assert before + 3600 <= expires_at <= after + 3600

    def test_calculate_expires_at_none(self):
        """Test calculating expiry time with None."""
        result = _calculate_expires_at(None)
        assert result is None

    def test_calculate_expires_at_invalid(self):
        """Test calculating expiry with invalid value."""
        result = _calculate_expires_at("not_a_number")
        assert result is None


# ============================================================================
# TOKEN EXCHANGE
# ============================================================================


class TestTokenExchange:
    """Test OAuth token exchange flow."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.requests.post")
    def test_exchange_code_for_tokens_success(self, mock_post, sample_token_response):
        """Test successful token exchange."""
        clear_oauth_context()
        context = prepare_oauth_context()
        assign_redirect_uri(context, 8765)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_token_response
        mock_post.return_value = mock_response

        result = exchange_code_for_tokens("AUTH_CODE_123", context)

        assert result is not None
        assert result["access_token"] == sample_token_response["access_token"]
        assert result["refresh_token"] == sample_token_response["refresh_token"]
        assert "expires_at" in result

        # Verify the HTTP call was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert CLAUDE_CODE_OAUTH_CONFIG["token_url"] in call_args[0]
        assert call_args[1]["json"]["grant_type"] == "authorization_code"
        assert call_args[1]["json"]["code"] == "AUTH_CODE_123"

    @patch("code_puppy.plugins.claude_code_oauth.utils.requests.post")
    def test_exchange_code_for_tokens_failure(self, mock_post):
        """Test token exchange failure."""
        clear_oauth_context()
        context = prepare_oauth_context()
        assign_redirect_uri(context, 8765)

        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid code"
        mock_post.return_value = mock_response

        result = exchange_code_for_tokens("INVALID_CODE", context)

        assert result is None

    @patch("code_puppy.plugins.claude_code_oauth.utils.requests.post")
    def test_exchange_code_for_tokens_network_error(self, mock_post):
        """Test token exchange with network error."""
        clear_oauth_context()
        context = prepare_oauth_context()
        assign_redirect_uri(context, 8765)

        mock_post.side_effect = requests.RequestException("Network error")

        result = exchange_code_for_tokens("AUTH_CODE_123", context)

        assert result is None

    def test_exchange_code_for_tokens_missing_redirect_uri(self):
        """Test token exchange fails without redirect URI."""
        context = OAuthContext(
            state="test_state",
            code_verifier="test_verifier",
            code_challenge="test_challenge",
            created_at=time.time(),
        )
        # Don't assign redirect_uri

        with pytest.raises(RuntimeError, match="Redirect URI"):
            exchange_code_for_tokens("AUTH_CODE", context)


# ============================================================================
# TOKEN REFRESH
# ============================================================================


class TestTokenRefresh:
    """Test token refresh functionality."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.requests.post")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    @patch("code_puppy.plugins.claude_code_oauth.utils.save_tokens")
    def test_refresh_access_token_success(
        self, mock_save, mock_load, mock_post, expired_token_data
    ):
        """Test successful token refresh."""
        mock_load.return_value = expired_token_data
        new_token = "new_access_token_123"
        new_refresh = "new_refresh_token_456"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": new_token,
            "refresh_token": new_refresh,
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response
        mock_save.return_value = True

        result = refresh_access_token()

        assert result == new_token
        mock_save.assert_called_once()
        # Verify updated token data was saved
        saved_data = mock_save.call_args[0][0]
        assert saved_data["access_token"] == new_token

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_refresh_access_token_no_refresh_token(self, mock_load):
        """Test refresh when no refresh token available."""
        # Token is expired to force refresh attempt
        mock_load.return_value = {
            "access_token": "token_only",
            "expires_at": time.time() - 100,  # Expired
        }

        result = refresh_access_token()

        assert result is None

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_refresh_access_token_no_tokens(self, mock_load):
        """Test refresh when no tokens stored."""
        mock_load.return_value = None

        result = refresh_access_token()

        assert result is None

    @patch("code_puppy.plugins.claude_code_oauth.utils.requests.post")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_refresh_access_token_network_error(
        self, mock_load, mock_post, expired_token_data
    ):
        """Test refresh with network error."""
        mock_load.return_value = expired_token_data
        mock_post.side_effect = requests.RequestException("Network error")

        result = refresh_access_token()

        assert result is None

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_refresh_access_token_forced_refresh(self, mock_load, sample_token_data):
        """Test forced refresh even for valid tokens."""
        mock_load.return_value = sample_token_data

        with patch(
            "code_puppy.plugins.claude_code_oauth.utils.requests.post"
        ) as mock_post:
            new_token = "forced_new_token"
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": new_token,
                "refresh_token": "new_refresh",
                "expires_in": 3600,
            }
            mock_post.return_value = mock_response

            with patch(
                "code_puppy.plugins.claude_code_oauth.utils.save_tokens"
            ) as mock_save:
                mock_save.return_value = True
                result = refresh_access_token(force=True)

                assert result == new_token
                # Verify post was called even though token not expired
                mock_post.assert_called_once()


# ============================================================================
# VALID ACCESS TOKEN RETRIEVAL
# ============================================================================


class TestValidAccessToken:
    """Test getting valid access token (with auto-refresh)."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_get_valid_access_token_fresh(self, mock_load, sample_token_data):
        """Test getting valid fresh token."""
        mock_load.return_value = sample_token_data

        result = get_valid_access_token()

        assert result == sample_token_data["access_token"]
        # Verify load_stored_tokens was called
        mock_load.assert_called()

    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_get_valid_access_token_no_tokens(self, mock_load):
        """Test when no tokens stored."""
        mock_load.return_value = None

        result = get_valid_access_token()

        assert result is None

    @patch("code_puppy.plugins.claude_code_oauth.utils.refresh_access_token")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_get_valid_access_token_expired_refreshes(
        self, mock_load, mock_refresh, expired_token_data
    ):
        """Test that expired token triggers refresh."""
        mock_load.return_value = expired_token_data
        new_token = "refreshed_token_123"
        mock_refresh.return_value = new_token

        result = get_valid_access_token()

        assert result == new_token
        mock_refresh.assert_called_once()

    @patch("code_puppy.plugins.claude_code_oauth.utils.refresh_access_token")
    @patch("code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens")
    def test_get_valid_access_token_refresh_fails(
        self, mock_load, mock_refresh, expired_token_data
    ):
        """Test when refresh fails."""
        mock_load.return_value = expired_token_data
        mock_refresh.return_value = None

        result = get_valid_access_token()

        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
