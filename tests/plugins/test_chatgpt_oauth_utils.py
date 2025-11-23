"""Comprehensive test coverage for ChatGPT OAuth utilities."""

import base64
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from code_puppy.plugins.chatgpt_oauth.config import (
    CHATGPT_OAUTH_CONFIG,
)
from code_puppy.plugins.chatgpt_oauth.utils import (
    OAuthContext,
    _compute_code_challenge,
    _generate_code_verifier,
    _urlsafe_b64encode,
    add_models_to_extra_config,
    assign_redirect_uri,
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_chatgpt_models,
    load_chatgpt_models,
    load_stored_tokens,
    parse_authorization_error,
    parse_jwt_claims,
    prepare_oauth_context,
    remove_chatgpt_models,
    save_chatgpt_models,
    save_tokens,
)


@pytest.fixture
def temp_token_file(tmp_path):
    """Create a temporary token file for testing."""
    token_file = tmp_path / "test_tokens.json"
    return token_file


@pytest.fixture
def temp_models_file(tmp_path):
    """Create a temporary models file for testing."""
    models_file = tmp_path / "test_models.json"
    return models_file


@pytest.fixture
def sample_jwt_claims():
    """Sample JWT claims for testing."""
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
    """Sample token data for testing."""
    return {
        "access_token": "sk-test_access_token_123",
        "refresh_token": "test_refresh_token_456",
        "id_token": "fake_id",
        "scope": "openid profile email offline_access",
        "token_type": "Bearer",
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

        # Should be valid base64 - add proper padding
        padding_needed = (-len(result)) % 4
        decoded = base64.urlsafe_b64decode(result + ("=" * padding_needed))
        assert decoded == data

    def test_urlsafe_b64encode_empty(self):
        """Test URL-safe base64 encoding of empty data."""
        result = _urlsafe_b64encode(b"")
        assert result == ""

    def test_urlsafe_b64encode_with_padding_removal(self):
        """Test that padding is properly removed."""
        # Data that would normally have padding
        data = b"test"
        result = _urlsafe_b64encode(data)

        # Should remove padding
        assert "=" not in result

        # But should still be decodable when padding is added back
        padding_needed = (-len(result)) % 4
        decoded = base64.urlsafe_b64decode(result + ("=" * padding_needed))
        assert decoded == data


class TestCodeVerifierGeneration:
    """Test PKCE code verifier generation."""

    def test_generate_code_verifier_length(self):
        """Test code verifier has correct length."""
        verifier = _generate_code_verifier()

        # Should be 128 characters (64 bytes hex-encoded)
        assert len(verifier) == 128

        # Should be valid hex
        int(verifier, 16)  # Should not raise exception

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
    """Test PKCE code challenge computation."""

    def test_compute_code_challenge(self):
        """Test code challenge computation from verifier."""
        verifier = "test_verifier"
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

    def test_compute_code_challenge_different_verifiers(self):
        """Test different verifiers produce different challenges."""
        verifier1 = "verifier_one"
        verifier2 = "verifier_two"

        challenge1 = _compute_code_challenge(verifier1)
        challenge2 = _compute_code_challenge(verifier2)

        assert challenge1 != challenge2

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
    """Test OAuthContext dataclass and methods."""

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
        assert context.expires_at is None

    def test_oauth_context_with_optional_fields(self):
        """Test OAuthContext creation with optional fields."""
        context = OAuthContext(
            state="test_state",
            code_verifier="test_verifier",
            code_challenge="test_challenge",
            created_at=time.time(),
            redirect_uri="http://localhost:1455/auth/callback",
            expires_at=time.time() + 300,
        )

        assert context.redirect_uri == "http://localhost:1455/auth/callback"
        assert context.expires_at is not None
        assert context.expires_at > context.created_at

    def test_is_expired_no_expiration_set(self):
        """Test expiration check when no expiration is set."""
        # Created 6 minutes ago (beyond default 5 minute timeout)
        old_context = OAuthContext(
            state="test",
            code_verifier="test",
            code_challenge="test",
            created_at=time.time() - 360,
        )

        assert old_context.is_expired() is True

        # Created 1 minute ago (within default 5 minute timeout)
        new_context = OAuthContext(
            state="test",
            code_verifier="test",
            code_challenge="test",
            created_at=time.time() - 60,
        )

        assert new_context.is_expired() is False

    def test_is_expired_with_expiration_set(self):
        """Test expiration check when expiration is explicitly set."""
        # Expired 1 minute ago
        expired_context = OAuthContext(
            state="test",
            code_verifier="test",
            code_challenge="test",
            created_at=time.time() - 300,
            expires_at=time.time() - 60,
        )

        assert expired_context.is_expired() is True

        # Expires in 5 minutes
        valid_context = OAuthContext(
            state="test",
            code_verifier="test",
            code_challenge="test",
            created_at=time.time(),
            expires_at=time.time() + 300,
        )

        assert valid_context.is_expired() is False


class TestPrepareOAuthContext:
    """Test OAuth context preparation."""

    def test_prepare_oauth_context_structure(self):
        """Test prepared OAuth context has correct structure."""
        context = prepare_oauth_context()

        assert isinstance(context, OAuthContext)
        assert isinstance(context.state, str)
        assert len(context.state) == 64  # 32 bytes hex-encoded

        assert isinstance(context.code_verifier, str)
        assert len(context.code_verifier) == 128  # 64 bytes hex-encoded

        assert isinstance(context.code_challenge, str)
        assert len(context.code_challenge) > 0
        assert context.code_challenge != context.code_verifier

        assert isinstance(context.created_at, float)
        assert context.created_at > 0

        assert isinstance(context.expires_at, float)
        assert context.expires_at > context.created_at
        assert context.expires_at - context.created_at == pytest.approx(
            240, rel=1e-2
        )  # 4 minutes

        assert context.redirect_uri is None

    def test_prepare_oauth_context_uniqueness(self):
        """Test each prepared context is unique."""
        contexts = [prepare_oauth_context() for _ in range(5)]

        states = [ctx.state for ctx in contexts]
        verifiers = [ctx.code_verifier for ctx in contexts]
        challenges = [ctx.code_challenge for ctx in contexts]

        # All should be unique
        assert len(set(states)) == len(states)
        assert len(set(verifiers)) == len(verifiers)
        assert len(set(challenges)) == len(challenges)

    def test_prepare_oauth_context_pkce_relationship(self):
        """Test PKCE verifier/challenge relationship."""
        context = prepare_oauth_context()

        # Challenge should be derived from verifier
        expected_challenge = _compute_code_challenge(context.code_verifier)
        assert context.code_challenge == expected_challenge


class TestAssignRedirectUri:
    """Test redirect URI assignment."""

    def test_assign_redirect_uri_success(self):
        """Test successful redirect URI assignment."""
        context = prepare_oauth_context()

        uri = assign_redirect_uri(context, 1455)

        assert uri == "http://localhost:1455/auth/callback"
        assert context.redirect_uri == uri

    def test_assign_redirect_uri_wrong_port(self):
        """Test redirect URI assignment fails with wrong port."""
        context = prepare_oauth_context()

        with pytest.raises(RuntimeError, match="OAuth flow must use port 1455"):
            assign_redirect_uri(context, 8080)

    def test_assign_redirect_uri_custom_config(self):
        """Test redirect URI with custom configuration."""
        # Temporarily modify config
        original_config = CHATGPT_OAUTH_CONFIG.copy()
        CHATGPT_OAUTH_CONFIG["redirect_host"] = "https://example.com"
        CHATGPT_OAUTH_CONFIG["redirect_path"] = "custom/path"

        try:
            context = prepare_oauth_context()
            uri = assign_redirect_uri(context, 1455)

            assert uri == "https://example.com:1455/custom/path"
            assert context.redirect_uri == uri
        finally:
            # Restore original config
            CHATGPT_OAUTH_CONFIG.clear()
            CHATGPT_OAUTH_CONFIG.update(original_config)


class TestBuildAuthorizationUrl:
    """Test authorization URL building."""

    def test_build_authorization_url_success(self):
        """Test successful authorization URL building."""
        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:1455/auth/callback"

        url = build_authorization_url(context)

        # Should contain base URL
        assert url.startswith("https://auth.openai.com/oauth/authorize?")

        # Should contain all required parameters
        assert "response_type=code" in url
        assert f"client_id={CHATGPT_OAUTH_CONFIG['client_id']}" in url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback" in url
        # Scope has spaces that get URL-encoded as + signs
        assert "scope=openid+profile+email+offline_access" in url
        assert f"code_challenge={context.code_challenge}" in url
        assert "code_challenge_method=S256" in url
        assert "id_token_add_organizations=true" in url
        assert "codex_cli_simplified_flow=true" in url
        assert f"state={context.state}" in url

    def test_build_authorization_url_no_redirect_uri(self):
        """Test authorization URL building fails without redirect URI."""
        context = prepare_oauth_context()
        # Don't set redirect_uri

        with pytest.raises(RuntimeError, match="Redirect URI has not been assigned"):
            build_authorization_url(context)

    def test_build_authorization_url_escaping(self):
        """Test URL parameter escaping in authorization URL."""
        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:1455/auth/callback?param=value&other=x"

        url = build_authorization_url(context)

        # Special characters should be encoded
        assert "%3F" in url  # Encoded question mark
        assert "%3D" in url  # Encoded equals
        assert "%26" in url  # Encoded ampersand


class TestParseAuthorizationError:
    """Test OAuth authorization error parsing."""

    def test_parse_authorization_error_with_error(self):
        """Test parsing authorization callback with error."""
        url = "http://localhost:1455/auth/callback?error=access_denied&error_description=User%20denied%20access"

        error = parse_authorization_error(url)

        assert error == "access_denied: User denied access"

    def test_parse_authorization_error_without_description(self):
        """Test parsing authorization error without description."""
        url = "http://localhost:1455/auth/callback?error=invalid_request"

        error = parse_authorization_error(url)

        assert error == "invalid_request: Unknown error"

    def test_parse_authorization_error_no_error(self):
        """Test parsing callback without error returns None."""
        url = "http://localhost:1455/auth/callback?code=test_code&state=test_state"

        error = parse_authorization_error(url)

        assert error is None

    def test_parse_authorization_error_invalid_url(self):
        """Test parsing invalid URL returns None."""
        invalid_url = "not a valid url"

        error = parse_authorization_error(invalid_url)

        assert error is None

    def test_parse_authorization_error_malformed_query(self):
        """Test parsing URL with malformed query returns None."""
        url = "http://localhost:1455/auth/callback?invalid"

        error = parse_authorization_error(url)

        assert error is None


class TestParseJwtClaims:
    """Test JWT claims parsing."""

    def test_parse_jwt_valid_token(self):
        """Test parsing valid JWT token."""
        # Create a simple JWT (header.payload.signature)
        header = (
            base64.urlsafe_b64encode(
                json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
            )
            .decode()
            .rstrip("=")
        )
        payload = (
            base64.urlsafe_b64encode(
                json.dumps({"sub": "123", "name": "test"}).encode()
            )
            .decode()
            .rstrip("=")
        )
        signature = "test_signature"

        token = f"{header}.{payload}.{signature}"

        claims = parse_jwt_claims(token)

        assert claims == {"sub": "123", "name": "test"}

    def test_parse_jwt_with_padding(self):
        """Test parsing JWT that requires padding."""
        # Create payload that needs padding
        payload_data = {"test": "data"}  # Short payload
        payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).decode()

        # Construct JWT with incomplete padding
        payload_incomplete = payload.rstrip("=")
        token = f"header.{payload_incomplete}.signature"

        claims = parse_jwt_claims(token)

        assert claims == payload_data

    def test_parse_jwt_empty_token(self):
        """Test parsing empty token returns None."""
        claims = parse_jwt_claims("")
        assert claims is None

    def test_parse_jwt_invalid_format(self):
        """Test parsing improperly formatted JWT returns None."""
        invalid_tokens = [
            "not.a.jwt",  # Missing third part
            "header.payload",  # Missing signature
            "header.payload.extra.signature",  # Too many parts
            "header.payload",  # Still invalid
        ]

        for token in invalid_tokens:
            claims = parse_jwt_claims(token)
            assert claims is None

    def test_parse_jwt_invalid_base64(self):
        """Test parsing JWT with invalid base64 returns None."""
        token = "header.invalid_payload.signature"

        claims = parse_jwt_claims(token)
        assert claims is None

    def test_parse_jwt_invalid_json(self):
        """Test parsing JWT with invalid JSON returns None."""
        invalid_payload = (
            base64.urlsafe_b64encode(b"not valid json").decode().rstrip("=")
        )
        token = f"header.{invalid_payload}.signature"

        claims = parse_jwt_claims(token)
        assert claims is None


class TestTokenStorage:
    """Test token storage and retrieval."""

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_load_stored_tokens_success(self, mock_get_path, temp_token_file):
        """Test successful loading of stored tokens."""
        mock_get_path.return_value = temp_token_file

        # Create test token file
        test_tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": "2023-12-31T23:59:59Z",
        }

        with open(temp_token_file, "w") as f:
            json.dump(test_tokens, f)

        # Set appropriate permissions (simulate 0o600)
        temp_token_file.chmod(0o600)

        result = load_stored_tokens()

        assert result == test_tokens

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_load_stored_tokens_file_not_exists(self, mock_get_path):
        """Test loading tokens when file doesn't exist returns None."""
        mock_get_path.return_value = Path("/nonexistent/file.json")

        result = load_stored_tokens()

        assert result is None

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_load_stored_tokens_invalid_json(self, mock_get_path, temp_token_file):
        """Test loading tokens with invalid JSON returns None."""
        mock_get_path.return_value = temp_token_file

        # Write invalid JSON
        with open(temp_token_file, "w") as f:
            f.write("not valid json")

        result = load_stored_tokens()

        assert result is None

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_load_stored_tokens_permission_error(self, mock_get_path):
        """Test loading tokens with permission error returns None."""
        mock_get_path.return_value = Path("/root/protected.json")

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            result = load_stored_tokens()
            assert result is None

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_save_stored_tokens_success(self, mock_get_path, temp_token_file):
        """Test successful saving of stored tokens."""
        mock_get_path.return_value = temp_token_file

        test_tokens = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "last_refresh": "2023-01-01T00:00:00Z",
        }

        result = save_tokens(test_tokens)

        assert result is True

        # Verify file was created with correct content
        assert temp_token_file.exists()

        with open(temp_token_file, "r") as f:
            saved_data = json.load(f)

        assert saved_data == test_tokens

        # Verify permissions are set to 0o600
        file_stat = temp_token_file.stat()
        assert file_stat.st_mode & 0o777 == 0o600

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_save_stored_tokens_permission_error(self, mock_get_path):
        """Test saving tokens with permission error returns False."""
        mock_get_path.return_value = Path("/root/protected.json")

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            result = save_tokens({"test": "data"})
            assert result is False

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_save_stored_tokens_serialization_error(
        self, mock_get_path, temp_token_file
    ):
        """Test saving tokens with serialization error returns False."""
        mock_get_path.return_value = temp_token_file

        # Use non-serializable data
        non_serializable = {"data": set([1, 2, 3])}  # sets are not JSON serializable

        result = save_tokens(non_serializable)

        assert result is False


class TestModelStorage:
    """Test model configuration storage."""

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path")
    def test_load_chatgpt_models_success(self, mock_get_path, temp_models_file):
        """Test successful loading of ChatGPT models configuration."""
        mock_get_path.return_value = temp_models_file

        test_models = {
            "chatgpt-gpt-4": {
                "type": "openai",
                "name": "gpt-4",
                "context_length": 8192,
            },
            "chatgpt-gpt-3.5-turbo": {
                "type": "openai",
                "name": "gpt-3.5-turbo",
                "context_length": 4096,
            },
        }

        with open(temp_models_file, "w") as f:
            json.dump(test_models, f)

        result = load_chatgpt_models()

        assert result == test_models

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path")
    def test_load_chatgpt_models_not_exists(self, mock_get_path):
        """Test loading models when file doesn't exist returns empty dict."""
        mock_get_path.return_value = Path("/nonexistent/models.json")

        result = load_chatgpt_models()

        assert result == {}

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path")
    def test_save_chatgpt_models_success(self, mock_get_path, temp_models_file):
        """Test successful saving of ChatGPT models configuration."""
        mock_get_path.return_value = temp_models_file

        test_models = {
            "chatgpt-new-model": {
                "type": "openai",
                "name": "gpt-5",
                "context_length": 32768,
            },
        }

        result = save_chatgpt_models(test_models)

        assert result is True

        # Verify file content
        with open(temp_models_file, "r") as f:
            saved_data = json.load(f)

        assert saved_data == test_models

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path")
    def test_save_chatgpt_models_error(self, mock_get_path):
        """Test saving models with error returns False."""
        mock_get_path.return_value = Path("/root/protected.json")

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            result = save_chatgpt_models({})
            assert result is False


class TestTokenExchange:
    """Test token exchange functionality."""

    @patch("requests.post")
    def test_exchange_code_for_tokens_success(self, mock_post):
        """Test successful token exchange."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "id_token": "test_id_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:1455/auth/callback"

        result = exchange_code_for_tokens("test_auth_code", context)

        assert result is not None
        assert result["access_token"] == "test_access_token"
        assert result["refresh_token"] == "test_refresh_token"
        assert result["id_token"] == "test_id_token"
        assert "last_refresh" in result

        # Verify proper timestamp format
        timestamp = result["last_refresh"]
        assert isinstance(timestamp, str)
        assert timestamp.endswith("Z")

        # Verify request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == CHATGPT_OAUTH_CONFIG["token_url"]
        assert call_args[1]["data"]["code"] == "test_auth_code"
        assert call_args[1]["data"]["client_id"] == CHATGPT_OAUTH_CONFIG["client_id"]
        assert call_args[1]["data"]["code_verifier"] == context.code_verifier

    @patch("requests.post")
    def test_exchange_code_for_tokens_http_error(self, mock_post):
        """Test token exchange handles HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:1455/auth/callback"

        result = exchange_code_for_tokens("invalid_code", context)

        assert result is None

    @patch("requests.post")
    def test_exchange_code_for_tokens_network_error(self, mock_post):
        """Test token exchange handles network errors."""
        mock_post.side_effect = requests.ConnectionError("Network error")

        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:1455/auth/callback"

        result = exchange_code_for_tokens("test_code", context)

        assert result is None

    @patch("requests.post")
    def test_exchange_code_for_tokens_timeout(self, mock_post):
        """Test token exchange handles timeout."""
        mock_post.side_effect = requests.Timeout("Request timed out")

        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:1455/auth/callback"

        result = exchange_code_for_tokens("test_code", context)

        assert result is None

    @patch("requests.post")
    def test_exchange_code_for_tokens_json_error_response(self, mock_post):
        """Test token exchange handles JSON error responses."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Authorization code expired",
        }
        mock_post.return_value = mock_response

        context = prepare_oauth_context()
        context.redirect_uri = "http://localhost:1455/auth/callback"

        result = exchange_code_for_tokens("expired_code", context)

        assert result is None

    def test_exchange_code_for_tokens_missing_redirect_uri(self):
        """Test token exchange fails without redirect URI."""
        context = prepare_oauth_context()
        # Don't set redirect_uri

        with pytest.raises(RuntimeError, match="Redirect URI missing"):
            exchange_code_for_tokens("test_code", context)

    def test_exchange_code_for_tokens_expired_context(self):
        """Test token exchange fails with expired context."""
        context = OAuthContext(
            state="test",
            code_verifier="test",
            code_challenge="test",
            created_at=time.time() - 300,
            expires_at=time.time() - 60,  # Expired
            redirect_uri="http://localhost:1455/auth/callback",
        )

        result = exchange_code_for_tokens("test_code", context)

        assert result is None


class TestFetchChatGPTModels:
    """Test ChatGPT model fetching functionality."""

    @patch("requests.get")
    def test_fetch_chatgpt_models_success(self, mock_get):
        """Test successful model fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4"},
                {"id": "gpt-3.5-turbo"},
                {"id": "gpt-4-32k"},
                {"id": "whisper-1"},  # Should be filtered out
                {"id": "o1-preview"},
                {"id": "o1-mini"},
            ]
        }
        mock_get.return_value = mock_response

        result = fetch_chatgpt_models("test_api_key")

        assert result == [
            "gpt-4",
            "gpt-3.5-turbo",
            "gpt-4-32k",
            "o1-preview",
            "o1-mini",
        ]

        # Verify request was made correctly
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://api.openai.com/v1/models"
        assert call_args[1]["headers"]["Authorization"] == "Bearer test_api_key"

    @patch("requests.get")
    def test_fetch_chatgpt_models_deduplication(self, mock_get):
        """Test model deduplication while preserving order."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4"},
                {"id": "gpt-3.5-turbo"},
                {"id": "gpt-4"},  # Duplicate
                {"id": "gpt-4"},  # Another duplicate
                {"id": "gpt-3.5-turbo"},  # Duplicate
                {"id": "o1-preview"},
            ]
        }
        mock_get.return_value = mock_response

        result = fetch_chatgpt_models("test_api_key")

        # Should preserve order and remove duplicates
        assert result == ["gpt-4", "gpt-3.5-turbo", "o1-preview"]

    @patch("requests.get")
    def test_fetch_chatgpt_models_filtering(self, mock_get):
        """Test model filtering by prefix and blocklist."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4"},  # Include (gpt- prefix)
                {"id": "gpt-3.5-turbo"},  # Include (gpt- prefix)
                {"id": "o1-preview"},  # Include (o1- prefix)
                {"id": "whisper-1"},  # Exclude (blocklisted)
                {"id": "text-davinci-003"},  # Exclude (no gpt- or o1- prefix)
                {"id": "dall-e-3"},  # Exclude (no gpt- or o1- prefix)
                {"id": "o1-mini"},  # Include (o1- prefix)
            ]
        }
        mock_get.return_value = mock_response

        result = fetch_chatgpt_models("test_api_key")

        assert result == ["gpt-4", "gpt-3.5-turbo", "o1-preview", "o1-mini"]

    @patch("requests.get")
    def test_fetch_chatgpt_models_http_error(self, mock_get):
        """Test model fetching handles HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_get.return_value = mock_response

        result = fetch_chatgpt_models("invalid_api_key")

        assert result is None

    @patch("requests.get")
    def test_fetch_chatgpt_models_network_error(self, mock_get):
        """Test model fetching handles network errors."""
        mock_get.side_effect = requests.ConnectionError("Network error")

        result = fetch_chatgpt_models("test_api_key")

        assert result is None

    @patch("requests.get")
    def test_fetch_chatgpt_models_timeout(self, mock_get):
        """Test model fetching handles timeout."""
        mock_get.side_effect = requests.Timeout("Request timed out")

        result = fetch_chatgpt_models("test_api_key")

        assert result is None

    @patch("requests.get")
    def test_fetch_chatgpt_models_invalid_json(self, mock_get):
        """Test model fetching handles invalid JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "{}", 0)
        mock_get.return_value = mock_response

        result = fetch_chatgpt_models("test_api_key")

        assert result is None

    @patch("requests.get")
    def test_fetch_chatgpt_models_missing_data_field(self, mock_get):
        """Test model fetching handles missing data field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "Missing data field"}
        mock_get.return_value = mock_response

        result = fetch_chatgpt_models("test_api_key")

        assert result is None

    @patch("requests.get")
    def test_fetch_chatgpt_models_invalid_data_type(self, mock_get):
        """Test model fetching handles invalid data field type."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "not a list"}
        mock_get.return_value = mock_response

        result = fetch_chatgpt_models("test_api_key")

        assert result is None

    @patch("requests.get")
    def test_fetch_chatgpt_models_empty_list(self, mock_get):
        """Test model fetching handles empty model list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        result = fetch_chatgpt_models("test_api_key")

        assert result == []  # Should return empty list, not None


class TestAddModelsToConfig:
    """Test adding models to configuration."""

    @patch("code_puppy.plugins.chatgpt_oauth.utils.save_chatgpt_models")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_chatgpt_models")
    def test_add_models_to_extra_config_success(self, mock_load, mock_save):
        """Test successful addition of models to configuration."""
        mock_load.return_value = {
            "existing-model": {
                "type": "other",
                "name": "existing",
            }
        }
        mock_save.return_value = True

        models = ["gpt-4", "gpt-3.5-turbo"]
        api_key = "test_api_key"

        result = add_models_to_extra_config(models, api_key)

        assert result is True

        # Verify save was called with correct data
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]

        # Should contain existing model
        assert "existing-model" in saved_config

        # Should contain new models with correct structure
        assert "chatgpt-gpt-4" in saved_config
        assert "chatgpt-gpt-3.5-turbo" in saved_config

        gpt4_config = saved_config["chatgpt-gpt-4"]
        assert gpt4_config["type"] == "openai"
        assert gpt4_config["name"] == "gpt-4"
        assert (
            gpt4_config["custom_endpoint"]["url"]
            == CHATGPT_OAUTH_CONFIG["api_base_url"]
        )
        assert gpt4_config["custom_endpoint"]["api_key"] == "${CHATGPT_OAUTH_API_KEY}"
        assert (
            gpt4_config["context_length"]
            == CHATGPT_OAUTH_CONFIG["default_context_length"]
        )
        assert gpt4_config["oauth_source"] == "chatgpt-oauth-plugin"

    @patch("code_puppy.plugins.chatgpt_oauth.utils.save_chatgpt_models")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_chatgpt_models")
    def test_add_models_to_extra_config_save_failure(self, mock_load, mock_save):
        """Test model addition fails when save fails."""
        mock_load.return_value = {}
        mock_save.return_value = False

        result = add_models_to_extra_config(["gpt-4"], "test_api_key")

        assert result is False

    @patch("code_puppy.plugins.chatgpt_oauth.utils.save_chatgpt_models")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_chatgpt_models")
    def test_add_models_to_extra_config_load_failure(self, mock_load, mock_save):
        """Test model addition handles load failure gracefully."""
        mock_load.return_value = {}  # Returns empty dict on failure
        mock_save.return_value = True

        result = add_models_to_extra_config(["gpt-4"], "test_api_key")

        assert result is True

        # Should still save the new models
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        assert "chatgpt-gpt-4" in saved_config


class TestRemoveChatGPTModels:
    """Test removing ChatGPT models from configuration."""

    @patch("code_puppy.plugins.chatgpt_oauth.utils.save_chatgpt_models")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_chatgpt_models")
    def test_remove_chatgpt_models_success(self, mock_load, mock_save):
        """Test successful removal of ChatGPT models."""
        mock_load.return_value = {
            "chatgpt-gpt-4": {
                "name": "gpt-4",
                "oauth_source": "chatgpt-oauth-plugin",
            },
            "chatgpt-gpt-3.5-turbo": {
                "name": "gpt-3.5-turbo",
                "oauth_source": "chatgpt-oauth-plugin",
            },
            "custom-model": {
                "name": "custom",
                "type": "other",
            },
        }
        mock_save.return_value = True

        result = remove_chatgpt_models()

        assert result == 2  # Two models removed

        # Verify save was called with correct data
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]

        # Should only contain non-OAuth models
        assert "chatgpt-gpt-4" not in saved_config
        assert "chatgpt-gpt-3.5-turbo" not in saved_config
        assert "custom-model" in saved_config

    @patch("code_puppy.plugins.chatgpt_oauth.utils.save_chatgpt_models")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_chatgpt_models")
    def test_remove_chatgpt_models_no_oauth_models(self, mock_load, mock_save):
        """Test removal when no OAuth models exist."""
        mock_load.return_value = {
            "custom-model-1": {
                "name": "custom1",
                "type": "other",
            },
            "custom-model-2": {
                "name": "custom2",
                "type": "other",
            },
        }
        mock_save.return_value = True

        result = remove_chatgpt_models()

        assert result == 0  # No models removed

        # Config should remain unchanged
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        assert len(saved_config) == 2

    @patch("code_puppy.plugins.chatgpt_oauth.utils.save_chatgpt_models")
    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_chatgpt_models")
    def test_remove_chatgpt_models_save_failure(self, mock_load, mock_save):
        """Test model removal fails when save fails."""
        mock_load.return_value = {
            "chatgpt-gpt-4": {
                "name": "gpt-4",
                "oauth_source": "chatgpt-oauth-plugin",
            },
        }
        mock_save.return_value = False

        result = remove_chatgpt_models()

        assert result == 0  # Returns 0 on.failure

    @patch("code_puppy.plugins.chatgpt_oauth.utils.load_chatgpt_models")
    def test_remove_chatgpt_models_load_failure(self, mock_load):
        """Test model removal handles load failure gracefully."""
        mock_load.return_value = {}  # Returns empty dict on failure

        result = remove_chatgpt_models()

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
        context.redirect_uri = "http://localhost:1455/auth/callback"

        for status_code, error_text in test_cases:
            mock_response = Mock()
            mock_response.status_code = status_code
            mock_response.text = error_text
            mock_post.return_value = mock_response

            result = exchange_code_for_tokens("test_code", context)

            assert result is None, f"Should return None for {status_code} error"

    @patch("requests.get")
    def test_fetch_chatgpt_models_various_http_errors(self, mock_get):
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

            result = fetch_chatgpt_models("test_api_key")

            assert result is None, f"Should return None for {status_code} error"

    def test_all_functions_handle_none_inputs_gracefully(self):
        """Test that utility functions handle None inputs gracefully."""
        # Most functions should handle None without crashing
        assert parse_authorization_error(None) is None
        assert parse_jwt_claims(None) is None
        assert parse_jwt_claims("") is None

        # These should raise appropriate errors for invalid inputs
        with pytest.raises(TypeError):
            save_tokens(None)  # type: ignore
        with pytest.raises(RuntimeError):
            assign_redirect_uri(None, 1455)  # type: ignore

    def test_model_filtering_edge_cases(self):
        """Test model filtering with edge cases."""
        test_cases = [
            # Empty models list
            ([], []),
            # Models without id field
            ([{"name": "test"}], []),
            # None model entries
            ([None, {"id": "gpt-4"}], ["gpt-4"]),
            # Empty string IDs
            ([{"id": ""}, {"id": "gpt-4"}], ["gpt-4"]),
        ]

        for input_models, expected_output in test_cases:
            with patch("requests.get") as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"data": input_models}
                mock_get.return_value = mock_response

                result = fetch_chatgpt_models("test_api_key")
                assert result == expected_output, f"Failed for input: {input_models}"
