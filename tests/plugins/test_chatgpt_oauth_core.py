"""Core ChatGPT OAuth tests - PKCE, JWT, token storage.

Covers:
- OAuth PKCE flow generation (code verifier, challenge)
- JWT token parsing and validation
- Token storage and retrieval
- Token refresh and expiration
"""

import base64
import hashlib
import json
import time
from unittest.mock import Mock, patch

import pytest
import requests

from code_puppy.plugins.chatgpt_oauth.utils import (
    OAuthContext,
    _compute_code_challenge,
    _generate_code_verifier,
    _urlsafe_b64encode,
    get_valid_access_token,
    load_stored_tokens,
    parse_jwt_claims,
    prepare_oauth_context,
    refresh_access_token,
    save_tokens,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_jwt_claims():
    """Sample JWT claims matching ChatGPT format."""
    return {
        "sub": "user_123",
        "email": "test@example.com",
        "https://api.openai.com/auth": {
            "chatgpt_account_id": "account_789",
            "organizations": [
                {"id": "org_123", "is_default": True},
                {"id": "org_456", "is_default": False},
            ],
        },
        "organization_id": "org_fallback",
        "exp": int(time.time()) + 3600,
    }


@pytest.fixture
def sample_token_data():
    """Sample OAuth token response."""
    return {
        "access_token": "sk-test_access_token_123",
        "refresh_token": "test_refresh_token_456",
        "id_token": "fake_id_token",
        "scope": "openid profile email offline_access",
        "token_type": "Bearer",
        "expires_in": 3600,
    }


@pytest.fixture
def mock_oauth_context():
    """Mock OAuth context for testing."""
    return OAuthContext(
        state="test_state_123",
        code_verifier="test_verifier_456",
        code_challenge="test_challenge_789",
        created_at=time.time(),
        redirect_uri="http://localhost:1455/auth/callback",
    )


# ============================================================================
# PKCE (Proof Key for Code Exchange) Tests
# ============================================================================


class TestPKCE:
    """Test PKCE flow generation and validation."""

    def test_urlsafe_b64encode_removes_padding(self):
        """Test URL-safe B64 encoding removes padding."""
        data = b"hello world"
        result = _urlsafe_b64encode(data)

        # No padding should be present
        assert "=" not in result
        assert "+" not in result  # URL-safe
        assert "/" not in result  # URL-safe

    def test_urlsafe_b64encode_valid_decoding(self):
        """Test encoded data can be decoded back correctly."""
        data = b"test data"
        encoded = _urlsafe_b64encode(data)

        # Add padding for decoding
        padding_needed = (-len(encoded)) % 4
        decoded = base64.urlsafe_b64decode(encoded + ("=" * padding_needed))
        assert decoded == data

    def test_code_verifier_generation(self):
        """Test code verifier is generated correctly."""
        verifier = _generate_code_verifier()

        # Should be hex string (128 chars for 64 bytes)
        assert len(verifier) == 128
        assert all(c in "0123456789abcdef" for c in verifier)

    def test_code_verifier_randomness(self):
        """Test code verifier is randomized."""
        verifier1 = _generate_code_verifier()
        verifier2 = _generate_code_verifier()

        assert verifier1 != verifier2

    def test_code_challenge_computation(self):
        """Test code challenge is computed from verifier."""
        verifier = "test_verifier_string"
        challenge = _compute_code_challenge(verifier)

        # Should be URL-safe base64 without padding
        assert "=" not in challenge
        assert "+" not in challenge
        assert "/" not in challenge

        # Verify the computation is deterministic
        challenge2 = _compute_code_challenge(verifier)
        assert challenge == challenge2

    def test_code_challenge_is_sha256_hash(self):
        """Test code challenge is SHA256 hash of verifier."""
        verifier = "test_verifier"
        challenge = _compute_code_challenge(verifier)

        # Manually compute expected value
        expected_digest = hashlib.sha256(verifier.encode()).digest()
        expected_challenge = (
            base64.urlsafe_b64encode(expected_digest).decode().rstrip("=")
        )

        assert challenge == expected_challenge

    def test_prepare_oauth_context(self):
        """Test OAuth context is created with all required fields."""
        context = prepare_oauth_context()

        assert context.state  # Should have state
        assert context.code_verifier  # Should have verifier
        assert context.code_challenge  # Should have challenge
        assert context.created_at  # Should have timestamp
        assert context.expires_at  # Should have expiration
        assert context.expires_at > context.created_at  # Expiry should be in future

    def test_oauth_context_expiration(self):
        """Test OAuth context expiration check."""
        # Fresh context should not be expired
        fresh_context = prepare_oauth_context()
        assert not fresh_context.is_expired()

        # Old context should be expired
        old_context = OAuthContext(
            state="test",
            code_verifier="test",
            code_challenge="test",
            created_at=time.time() - 600,  # 10 minutes ago
            expires_at=time.time() - 300,  # Expired 5 minutes ago
        )
        assert old_context.is_expired()


# ============================================================================
# JWT Parsing Tests
# ============================================================================


class TestJWTParsing:
    """Test JWT token parsing and claim extraction."""

    def _encode_jwt_payload(self, claims):
        """Helper to encode JWT claims for testing."""
        payload = json.dumps(claims).encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        # Return minimal JWT format (header.payload.signature)
        return f"header.{encoded}.signature"

    def test_parse_jwt_claims_success(self, sample_jwt_claims):
        """Test successful JWT claims parsing."""
        token = self._encode_jwt_payload(sample_jwt_claims)
        claims = parse_jwt_claims(token)

        assert claims is not None
        assert claims["sub"] == "user_123"
        assert claims["email"] == "test@example.com"
        assert "https://api.openai.com/auth" in claims

    def test_parse_jwt_claims_invalid_token(self):
        """Test parsing invalid JWT returns None."""
        invalid_tokens = [
            "not.a.jwt",  # Only 2 parts
            "not.a.jwt.with.too.many.parts",  # Too many parts
            "invalid",  # No dots
            "",  # Empty
        ]

        for token in invalid_tokens:
            assert parse_jwt_claims(token) is None

    def test_parse_jwt_claims_bad_base64(self):
        """Test parsing JWT with invalid base64 returns None."""
        bad_token = "header.not_valid_base64!!!.signature"
        assert parse_jwt_claims(bad_token) is None

    def test_parse_jwt_claims_bad_json(self):
        """Test parsing JWT with invalid JSON returns None."""
        payload = base64.urlsafe_b64encode(b"not json").decode().rstrip("=")
        bad_token = f"header.{payload}.signature"
        assert parse_jwt_claims(bad_token) is None

    def test_parse_jwt_with_padding(self):
        """Test JWT parsing handles various padding styles."""
        claims = {"sub": "user_123", "email": "test@example.com"}
        payload_json = json.dumps(claims).encode()

        # Test with different padding scenarios
        for padding in ["", "=", "=="]:
            payload = base64.urlsafe_b64encode(payload_json).decode().rstrip("=")
            payload = payload + padding  # Add padding
            token = f"header.{payload}.signature"
            parsed = parse_jwt_claims(token)
            assert parsed is not None
            assert parsed["sub"] == "user_123"


# ============================================================================
# Token Storage and Retrieval Tests
# ============================================================================


class TestTokenStorage:
    """Test token loading, saving, and retrieval."""

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_save_tokens_success(self, mock_path, sample_token_data, tmp_path):
        """Test tokens are saved successfully."""
        token_file = tmp_path / "tokens.json"
        mock_path.return_value = token_file

        result = save_tokens(sample_token_data)

        assert result is True
        assert token_file.exists()

        # Verify file contents
        with open(token_file) as f:
            saved = json.load(f)
        assert saved == sample_token_data

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_save_tokens_file_permissions(self, mock_path, sample_token_data, tmp_path):
        """Test token file has secure permissions (0o600)."""
        token_file = tmp_path / "tokens.json"
        mock_path.return_value = token_file

        save_tokens(sample_token_data)

        # Check file permissions
        mode = token_file.stat().st_mode & 0o777
        assert mode == 0o600  # User read/write only

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_save_tokens_none_raises_error(self, mock_path):
        """Test save_tokens raises error for None input."""
        with pytest.raises(TypeError):
            save_tokens(None)

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_load_tokens_success(self, mock_path, sample_token_data, tmp_path):
        """Test tokens are loaded successfully."""
        token_file = tmp_path / "tokens.json"
        token_file.write_text(json.dumps(sample_token_data))
        mock_path.return_value = token_file

        loaded = load_stored_tokens()

        assert loaded == sample_token_data

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_load_tokens_file_not_found(self, mock_path, tmp_path):
        """Test load_tokens returns None when file doesn't exist."""
        token_file = tmp_path / "nonexistent.json"
        mock_path.return_value = token_file

        loaded = load_stored_tokens()

        assert loaded is None

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_load_tokens_invalid_json(self, mock_path, tmp_path):
        """Test load_tokens returns None for invalid JSON."""
        token_file = tmp_path / "tokens.json"
        token_file.write_text("invalid json {")
        mock_path.return_value = token_file

        loaded = load_stored_tokens()

        assert loaded is None

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_save_tokens_write_error(self, mock_path, sample_token_data, tmp_path):
        """Test save_tokens handles write errors gracefully."""
        token_file = tmp_path / "tokens.json"
        mock_path.return_value = token_file

        # Make directory read-only to cause write error
        tmp_path.chmod(0o444)

        try:
            result = save_tokens(sample_token_data)
            assert result is False
        finally:
            # Restore permissions for cleanup
            tmp_path.chmod(0o755)


# ============================================================================
# Token Refresh Tests
# ============================================================================


class TestTokenRefresh:
    """Test access token refresh functionality."""

    def _encode_jwt_with_exp(self, exp_time):
        """Helper to create JWT with specific expiration."""
        claims = {"exp": exp_time, "sub": "user_123"}
        payload = json.dumps(claims).encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        return f"header.{encoded}.signature"

    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_stored_tokens")
    def test_get_valid_access_token_fresh(self, mock_load):
        """Test fresh token is returned as-is."""
        # Token expiring in 1 hour
        future_exp = int(time.time()) + 3600
        fresh_token = self._encode_jwt_with_exp(future_exp)

        mock_load.return_value = {
            "access_token": fresh_token,
            "refresh_token": "refresh_token",
        }

        result = get_valid_access_token()

        assert result == fresh_token

    @patch("code_puppy.plugins.chatgpt_oauth.utils.refresh_access_token")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_stored_tokens")
    def test_get_valid_access_token_expired(self, mock_load, mock_refresh):
        """Test expired token triggers refresh."""
        # Token expired 1 hour ago
        past_exp = int(time.time()) - 3600
        expired_token = self._encode_jwt_with_exp(past_exp)

        mock_load.return_value = {
            "access_token": expired_token,
            "refresh_token": "refresh_token",
        }
        new_token = self._encode_jwt_with_exp(int(time.time()) + 3600)
        mock_refresh.return_value = new_token

        result = get_valid_access_token()

        assert result == new_token
        mock_refresh.assert_called_once()

    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_stored_tokens")
    def test_get_valid_access_token_no_tokens(self, mock_load):
        """Test returns None when no tokens stored."""
        mock_load.return_value = None

        result = get_valid_access_token()

        assert result is None

    @patch("code_puppy.plugins.chatgpt_oauth.utils.save_tokens")
    @patch("requests.post")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_stored_tokens")
    def test_refresh_access_token_success(self, mock_load, mock_post, mock_save):
        """Test successful token refresh."""
        old_tokens = {
            "access_token": "old_token",
            "refresh_token": "refresh_token_123",
            "id_token": "id_token_123",
        }
        mock_load.return_value = old_tokens

        new_response = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "id_token": "new_id_token",
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = new_response
        mock_post.return_value = mock_response
        mock_save.return_value = True

        result = refresh_access_token()

        assert result == "new_access_token"
        mock_post.assert_called_once()
        mock_save.assert_called_once()

    @patch("requests.post")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_stored_tokens")
    def test_refresh_access_token_no_refresh_token(self, mock_load, mock_post):
        """Test refresh fails when no refresh token available."""
        mock_load.return_value = {"access_token": "token"}

        result = refresh_access_token()

        assert result is None
        mock_post.assert_not_called()

    @patch("requests.post")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_stored_tokens")
    def test_refresh_access_token_http_error(self, mock_load, mock_post):
        """Test refresh handles HTTP errors."""
        mock_load.return_value = {
            "access_token": "token",
            "refresh_token": "refresh_token",
        }

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        result = refresh_access_token()

        assert result is None

    @patch("requests.post")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_stored_tokens")
    def test_refresh_access_token_network_error(self, mock_load, mock_post):
        """Test refresh handles network errors."""
        mock_load.return_value = {
            "access_token": "token",
            "refresh_token": "refresh_token",
        }
        mock_post.side_effect = requests.ConnectionError("Network error")

        result = refresh_access_token()

        assert result is None
