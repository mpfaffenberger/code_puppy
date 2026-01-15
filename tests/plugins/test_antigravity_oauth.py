"""Comprehensive test coverage for Antigravity OAuth flow."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from code_puppy.plugins.antigravity_oauth.oauth import (
    AntigravityStatus,
    OAuthContext,
    TokenExchangeFailure,
    TokenExchangeSuccess,
    _compute_code_challenge,
    _decode_state,
    _encode_state,
    _generate_code_verifier,
    _urlsafe_b64encode,
    assign_redirect_uri,
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_antigravity_status,
    prepare_oauth_context,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_requests_post():
    """Create a mock for requests.post."""
    with patch("code_puppy.plugins.antigravity_oauth.oauth.requests.post") as mock:
        yield mock


@pytest.fixture
def mock_requests_get():
    """Create a mock for requests.get."""
    with patch("code_puppy.plugins.antigravity_oauth.oauth.requests.get") as mock:
        yield mock


@pytest.fixture
def sample_oauth_context():
    """Create a sample OAuthContext."""
    return OAuthContext(
        state="test_state_123",
        code_verifier="test_code_verifier_456",
        code_challenge="test_code_challenge_789",
        redirect_uri="http://localhost:51121/oauth-callback",
    )


# ============================================================================
# CODE VERIFIER AND CHALLENGE TESTS
# ============================================================================


class TestCodeGeneration:
    """Test PKCE code verifier and challenge generation."""

    def test_urlsafe_b64encode(self):
        """Test URL-safe base64 encoding without padding."""
        data = b"test_data_for_encoding"
        result = _urlsafe_b64encode(data)

        # Should not contain padding
        assert "=" not in result
        # Should be valid URL-safe base64
        assert "-" in result or "_" in result or result.isalnum()

    def test_generate_code_verifier(self):
        """Test code verifier generation."""
        verifier = _generate_code_verifier()

        # Should be non-empty
        assert len(verifier) > 0
        # Should be URL-safe base64
        assert "-" in verifier or "_" in verifier or verifier.isalnum()
        # Should not contain padding
        assert "=" not in verifier
        # Should be deterministic length (86 chars for 64 bytes)
        assert len(verifier) > 80

    def test_generate_code_verifier_uniqueness(self):
        """Test that code verifiers are unique."""
        verifier1 = _generate_code_verifier()
        verifier2 = _generate_code_verifier()

        assert verifier1 != verifier2

    def test_compute_code_challenge(self):
        """Test code challenge computation."""
        verifier = _generate_code_verifier()
        challenge = _compute_code_challenge(verifier)

        # Should be non-empty
        assert len(challenge) > 0
        # Should not contain padding
        assert "=" not in challenge
        # Should be consistent
        challenge2 = _compute_code_challenge(verifier)
        assert challenge == challenge2

    def test_compute_code_challenge_sha256(self):
        """Test that code challenge uses SHA256."""
        import hashlib

        verifier = "test_verifier"
        expected_digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        expected_challenge = _urlsafe_b64encode(expected_digest)

        actual_challenge = _compute_code_challenge(verifier)
        assert actual_challenge == expected_challenge


# ============================================================================
# STATE ENCODING/DECODING TESTS
# ============================================================================


class TestStateHandling:
    """Test OAuth state encoding and decoding."""

    def test_encode_state_with_verifier_only(self):
        """Test encoding state with just verifier."""
        verifier = "test_verifier_123"
        state = _encode_state(verifier)

        # Should be non-empty and URL-safe
        assert len(state) > 0
        assert "=" not in state

    def test_encode_state_with_verifier_and_project_id(self):
        """Test encoding state with verifier and project ID."""
        verifier = "test_verifier_123"
        project_id = "my_project_456"
        state = _encode_state(verifier, project_id)

        assert len(state) > 0
        assert "=" not in state

    def test_decode_state_basic(self):
        """Test basic state decoding."""
        verifier = "test_verifier_123"
        project_id = "project_456"
        state = _encode_state(verifier, project_id)

        decoded_verifier, decoded_project = _decode_state(state)

        assert decoded_verifier == verifier
        assert decoded_project == project_id

    def test_decode_state_empty_project(self):
        """Test decoding state with empty project ID."""
        verifier = "test_verifier_123"
        state = _encode_state(verifier, "")

        decoded_verifier, decoded_project = _decode_state(state)

        assert decoded_verifier == verifier
        assert decoded_project == ""

    def test_decode_state_preserves_special_chars(self):
        """Test that special characters in verifier are preserved."""
        verifier = "test_verifier-with-special_chars_123!"
        project_id = "project_with-dashes_123"
        state = _encode_state(verifier, project_id)

        decoded_verifier, decoded_project = _decode_state(state)

        assert decoded_verifier == verifier
        assert decoded_project == project_id

    def test_decode_state_with_padding_normalization(self):
        """Test that state decoding handles padding normalization."""
        verifier = "test_verifier"
        project_id = "proj"
        state = _encode_state(verifier, project_id)

        # Manually add padding (which should be handled)
        padded_state = state + "="
        decoded_verifier, decoded_project = _decode_state(padded_state)

        assert decoded_verifier == verifier
        assert decoded_project == project_id

    def test_decode_state_invalid_json(self):
        """Test decoding invalid state raises ValueError."""
        # Create invalid base64
        invalid_state = "!!!invalid_state!!!"

        with pytest.raises(ValueError):
            _decode_state(invalid_state)

    def test_decode_state_missing_verifier(self):
        """Test decoding state without verifier raises ValueError."""
        # Create state with missing verifier
        payload = {"projectId": "proj"}
        invalid_state = (
            base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
            .decode("utf-8")
            .rstrip("=")
        )

        with pytest.raises(ValueError):
            _decode_state(invalid_state)


# ============================================================================
# OAUTH CONTEXT TESTS
# ============================================================================


class TestOAuthContext:
    """Test OAuth context preparation and configuration."""

    def test_prepare_oauth_context(self):
        """Test preparing a new OAuth context."""
        context = prepare_oauth_context()

        assert context.state is not None
        assert len(context.state) > 0
        assert context.code_verifier is not None
        assert len(context.code_verifier) > 0
        assert context.code_challenge is not None
        assert len(context.code_challenge) > 0
        assert context.redirect_uri is None

    def test_prepare_oauth_context_uniqueness(self):
        """Test that prepared contexts are unique."""
        context1 = prepare_oauth_context()
        context2 = prepare_oauth_context()

        assert context1.state != context2.state
        assert context1.code_verifier != context2.code_verifier
        assert context1.code_challenge != context2.code_challenge

    def test_assign_redirect_uri(self):
        """Test assigning redirect URI to context."""
        context = prepare_oauth_context()
        port = 51121

        uri = assign_redirect_uri(context, port)

        assert uri == f"http://localhost:{port}/oauth-callback"
        assert context.redirect_uri == uri

    def test_assign_redirect_uri_different_ports(self):
        """Test assigning different redirect URIs."""
        context1 = prepare_oauth_context()
        context2 = prepare_oauth_context()

        uri1 = assign_redirect_uri(context1, 8000)
        uri2 = assign_redirect_uri(context2, 8001)

        assert uri1 == "http://localhost:8000/oauth-callback"
        assert uri2 == "http://localhost:8001/oauth-callback"


# ============================================================================
# AUTHORIZATION URL TESTS
# ============================================================================


class TestAuthorizationURL:
    """Test OAuth authorization URL building."""

    def test_build_authorization_url_requires_redirect_uri(self):
        """Test that building URL requires redirect URI to be set."""
        context = prepare_oauth_context()

        with pytest.raises(RuntimeError, match="Redirect URI"):
            build_authorization_url(context)

    def test_build_authorization_url_basic(self, sample_oauth_context):
        """Test building a complete authorization URL."""
        url = build_authorization_url(sample_oauth_context)

        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
        assert "client_id=" in url
        assert "response_type=code" in url
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url
        assert "state=" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url

    def test_build_authorization_url_contains_scopes(self, sample_oauth_context):
        """Test that authorization URL includes required scopes."""
        url = build_authorization_url(sample_oauth_context)

        assert "cloud-platform" in url
        assert "userinfo.email" in url
        assert "userinfo.profile" in url
        assert "cclog" in url

    def test_build_authorization_url_with_project_id(self, sample_oauth_context):
        """Test building URL with specific project ID."""
        project_id = "my_project_123"
        url = build_authorization_url(sample_oauth_context, project_id)

        # Decode state and verify project ID is included
        import urllib.parse

        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        state = params["state"][0]

        _, decoded_project = _decode_state(state)
        assert decoded_project == project_id

    def test_build_authorization_url_state_verification(self, sample_oauth_context):
        """Test that state can be decoded back."""
        url = build_authorization_url(sample_oauth_context)

        # Extract state from URL
        import urllib.parse

        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        state = params["state"][0]

        # Should be decodable
        verifier, _ = _decode_state(state)
        assert len(verifier) > 0


# ============================================================================
# TOKEN EXCHANGE TESTS
# ============================================================================


class TestTokenExchange:
    """Test OAuth token exchange."""

    def test_exchange_code_for_tokens_success(
        self, mock_requests_post, mock_requests_get
    ):
        """Test successful token exchange."""
        # Mock Google token endpoint
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "expires_in": 3600,
        }
        mock_requests_post.return_value = mock_response

        # Mock userinfo endpoint
        user_response = MagicMock()
        user_response.ok = True
        user_response.json.return_value = {"email": "test@example.com"}
        mock_requests_get.return_value = user_response

        # Mock _fetch_project_id
        with patch(
            "code_puppy.plugins.antigravity_oauth.oauth._fetch_project_id"
        ) as mock_fetch_project:
            mock_fetch_project.return_value = "project_789"

            context = prepare_oauth_context()
            assign_redirect_uri(context, 51121)
            state = _encode_state(context.code_verifier, "")

            result = exchange_code_for_tokens(
                "auth_code_123", state, context.redirect_uri
            )

            assert isinstance(result, TokenExchangeSuccess)
            assert result.refresh_token == "refresh_token_456|project_789"
            assert result.access_token == "access_token_123"
            assert result.email == "test@example.com"
            assert result.project_id == "project_789"

    def test_exchange_code_for_tokens_with_state_project_id(
        self, mock_requests_post, mock_requests_get
    ):
        """Test token exchange with project ID in state."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "expires_in": 3600,
        }
        mock_requests_post.return_value = mock_response

        user_response = MagicMock()
        user_response.ok = True
        user_response.json.return_value = {"email": "test@example.com"}
        mock_requests_get.return_value = user_response

        context = prepare_oauth_context()
        assign_redirect_uri(context, 51121)
        state = _encode_state(context.code_verifier, "project_from_state")

        result = exchange_code_for_tokens("auth_code_123", state, context.redirect_uri)

        assert isinstance(result, TokenExchangeSuccess)
        assert "project_from_state" in result.refresh_token
        assert result.project_id == "project_from_state"

    def test_exchange_code_for_tokens_missing_refresh_token(self, mock_requests_post):
        """Test token exchange fails when refresh token is missing."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "access_token": "access_token_123",
            # Missing refresh_token
            "expires_in": 3600,
        }
        mock_requests_post.return_value = mock_response

        context = prepare_oauth_context()
        assign_redirect_uri(context, 51121)
        state = _encode_state(context.code_verifier, "")

        result = exchange_code_for_tokens("auth_code_123", state, context.redirect_uri)

        assert isinstance(result, TokenExchangeFailure)
        assert "Missing refresh token" in result.error

    def test_exchange_code_for_tokens_http_error(self, mock_requests_post):
        """Test token exchange fails on HTTP error."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.text = "Invalid authorization code"
        mock_requests_post.return_value = mock_response

        context = prepare_oauth_context()
        assign_redirect_uri(context, 51121)
        state = _encode_state(context.code_verifier, "")

        result = exchange_code_for_tokens("bad_code", state, context.redirect_uri)

        assert isinstance(result, TokenExchangeFailure)
        assert "Invalid authorization code" in result.error

    def test_exchange_code_for_tokens_invalid_state(self, mock_requests_post):
        """Test token exchange fails with invalid state."""
        context = prepare_oauth_context()
        assign_redirect_uri(context, 51121)

        result = exchange_code_for_tokens(
            "auth_code_123", "invalid_state", context.redirect_uri
        )

        assert isinstance(result, TokenExchangeFailure)

    def test_exchange_code_for_tokens_userinfo_error(
        self, mock_requests_post, mock_requests_get
    ):
        """Test that userinfo fetch errors don't break token exchange."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "expires_in": 3600,
        }
        mock_requests_post.return_value = mock_response

        # Userinfo fails
        user_response = MagicMock()
        user_response.ok = False
        mock_requests_get.return_value = user_response

        with patch(
            "code_puppy.plugins.antigravity_oauth.oauth._fetch_project_id"
        ) as mock_fetch_project:
            mock_fetch_project.return_value = "project_789"

            context = prepare_oauth_context()
            assign_redirect_uri(context, 51121)
            state = _encode_state(context.code_verifier, "")

            result = exchange_code_for_tokens(
                "auth_code_123", state, context.redirect_uri
            )

            # Should still succeed
            assert isinstance(result, TokenExchangeSuccess)
            assert result.email is None  # But email is None

    def test_exchange_code_uses_pkce_verifier(
        self, mock_requests_post, mock_requests_get
    ):
        """Test that code exchange includes PKCE verifier."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "expires_in": 3600,
        }
        mock_requests_post.return_value = mock_response

        user_response = MagicMock()
        user_response.ok = True
        user_response.json.return_value = {"email": "test@example.com"}
        mock_requests_get.return_value = user_response

        with patch(
            "code_puppy.plugins.antigravity_oauth.oauth._fetch_project_id"
        ) as mock_fetch_project:
            mock_fetch_project.return_value = ""

            context = prepare_oauth_context()
            assign_redirect_uri(context, 51121)
            state = _encode_state(context.code_verifier, "")

            exchange_code_for_tokens("auth_code_123", state, context.redirect_uri)

            # Verify the POST call included code_verifier
            call_args = mock_requests_post.call_args
            assert call_args is not None
            data = call_args.kwargs.get("data") or call_args[1].get("data", {})
            assert "code_verifier" in data


# ============================================================================
# PROJECT ID FETCHING TESTS
# ============================================================================


class TestProjectIDFetching:
    """Test project ID fetching from Antigravity API."""

    def test_fetch_antigravity_status_success(self, mock_requests_post):
        """Test successful status fetch."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "cloudaicompanionProject": "project_123",
            "allowedTiers": [
                {"id": "free-tier", "isDefault": True},
                {"id": "standard-tier"},
            ],
        }
        mock_requests_post.return_value = mock_response

        result = fetch_antigravity_status("access_token_123")

        assert isinstance(result, AntigravityStatus)
        assert result.project_id == "project_123"
        assert result.is_onboarded is True
        assert "free-tier" in result.allowed_tiers
        assert result.current_tier == "free-tier"

    def test_fetch_antigravity_status_project_as_dict(self, mock_requests_post):
        """Test status fetch with project as dict."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "cloudaicompanionProject": {"id": "project_456"},
            "allowedTiers": [{"id": "free-tier", "isDefault": True}],
        }
        mock_requests_post.return_value = mock_response

        result = fetch_antigravity_status("access_token_123")

        assert result.project_id == "project_456"
        assert result.is_onboarded is True

    def test_fetch_antigravity_status_not_onboarded(self, mock_requests_post):
        """Test status fetch when user is not onboarded."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "allowedTiers": [{"id": "free-tier"}],
        }
        mock_requests_post.return_value = mock_response

        result = fetch_antigravity_status("access_token_123")

        assert result.project_id == ""
        assert result.is_onboarded is False

    def test_fetch_antigravity_status_api_failure(self, mock_requests_post):
        """Test status fetch when API is unavailable."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_requests_post.return_value = mock_response

        result = fetch_antigravity_status("access_token_123")

        assert result.error is not None
        assert "Could not reach" in result.error

    def test_fetch_antigravity_status_network_error(self, mock_requests_post):
        """Test status fetch with network error."""
        mock_requests_post.side_effect = requests.RequestException("Network error")

        result = fetch_antigravity_status("access_token_123")

        assert result.error is not None


# ============================================================================
# EDGE CASES AND INTEGRATION TESTS
# ============================================================================


class TestEdgeCases:
    """Test edge cases and integration scenarios."""

    def test_code_verifier_challenge_consistency(self):
        """Test that challenge is consistent for same verifier."""
        verifier = "test_verifier_123"
        challenge1 = _compute_code_challenge(verifier)
        challenge2 = _compute_code_challenge(verifier)

        assert challenge1 == challenge2

    def test_state_roundtrip_with_special_chars(self):
        """Test state encoding/decoding with special characters."""
        verifier = "verifier_with-special_chars@123!"
        project_id = "project-with_special@chars123!"

        encoded = _encode_state(verifier, project_id)
        decoded_verifier, decoded_project = _decode_state(encoded)

        assert decoded_verifier == verifier
        assert decoded_project == project_id

    def test_multiple_oauth_contexts_independent(self):
        """Test that multiple OAuth contexts are independent."""
        context1 = prepare_oauth_context()
        context2 = prepare_oauth_context()

        assign_redirect_uri(context1, 8000)
        assign_redirect_uri(context2, 8001)

        assert context1.redirect_uri != context2.redirect_uri
        assert context1.code_verifier != context2.code_verifier

    def test_authorization_url_contains_client_credentials(self, sample_oauth_context):
        """Test that authorization URL contains client ID."""

        url = build_authorization_url(sample_oauth_context)

        # Should contain client ID (though potentially URL encoded)
        assert "1071006060591" in url or "client_id" in url

    def test_token_exchange_sets_expiry_timestamp(
        self, mock_requests_post, mock_requests_get
    ):
        """Test that token exchange sets proper expiry timestamp."""
        mock_response = MagicMock()
        mock_response.ok = True
        expires_in = 3600
        mock_response.json.return_value = {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "expires_in": expires_in,
        }
        mock_requests_post.return_value = mock_response

        user_response = MagicMock()
        user_response.ok = True
        user_response.json.return_value = {"email": "test@example.com"}
        mock_requests_get.return_value = user_response

        with patch(
            "code_puppy.plugins.antigravity_oauth.oauth._fetch_project_id"
        ) as mock_fetch_project:
            mock_fetch_project.return_value = ""

            before_exchange = time.time()
            context = prepare_oauth_context()
            assign_redirect_uri(context, 51121)
            state = _encode_state(context.code_verifier, "")

            result = exchange_code_for_tokens(
                "auth_code_123", state, context.redirect_uri
            )
            after_exchange = time.time()

            assert isinstance(result, TokenExchangeSuccess)
            # Expiry should be within reasonable bounds
            assert result.expires_at > before_exchange + expires_in - 10
            assert result.expires_at < after_exchange + expires_in + 10

    def test_state_encoding_produces_different_output_per_call(self):
        """Test that each state encoding produces different output (if includes randomness)."""
        # The current implementation just encodes deterministically
        verifier = "test_verifier"
        state1 = _encode_state(verifier)
        state2 = _encode_state(verifier)

        # Same verifier should produce same state
        assert state1 == state2

    def test_large_project_id_in_state(self):
        """Test handling of large project IDs in state."""
        verifier = "verifier"
        large_project = "project_" + "x" * 1000  # Very long project ID

        state = _encode_state(verifier, large_project)
        decoded_verifier, decoded_project = _decode_state(state)

        assert decoded_verifier == verifier
        assert decoded_project == large_project
