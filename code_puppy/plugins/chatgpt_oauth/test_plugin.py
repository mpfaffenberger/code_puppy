"""
Basic tests for ChatGPT OAuth plugin.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.chatgpt_oauth import config, utils


def test_config_paths():
    """Test configuration path helpers."""
    token_path = config.get_token_storage_path()
    assert token_path.name == "chatgpt_oauth.json"
    # XDG paths use "code_puppy" (without dot) in ~/.local/share or ~/.config
    assert "code_puppy" in str(token_path)

    config_dir = config.get_config_dir()
    # Default is ~/.code_puppy; XDG paths only used when XDG env vars are set
    assert config_dir.name in ("code_puppy", ".code_puppy")

    chatgpt_models = config.get_chatgpt_models_path()
    assert chatgpt_models.name == "chatgpt_models.json"


def test_oauth_config():
    """Test OAuth configuration values."""
    assert config.CHATGPT_OAUTH_CONFIG["issuer"] == "https://auth.openai.com"
    assert config.CHATGPT_OAUTH_CONFIG["client_id"] == "app_EMoamEEZ73f0CkXaXp7hrann"
    assert config.CHATGPT_OAUTH_CONFIG["prefix"] == "chatgpt-"


def test_jwt_parsing_with_nested_org():
    """Test JWT parsing with nested organization structure like the user's payload."""
    # This simulates the user's JWT payload structure
    mock_claims = {
        "aud": ["app_EMoamEEZ73f0CkXaXp7hrann"],
        "auth_provider": "google",
        "email": "mike.pfaf fenberger@gmail.com",
        "https://api.openai.com/auth": {
            "chatgpt_account_id": "d1844a91-9aac-419b-903e-f6a99c76f163",
            "organizations": [
                {
                    "id": "org-iydWjnSxSr51VuYhDVMDte5",
                    "is_default": True,
                    "role": "owner",
                    "title": "Personal",
                }
            ],
            "groups": ["api-data-sharing-incentives-program", "verified-organization"],
        },
        "sub": "google-oauth2|107692466937587138174",
    }

    # Test the org extraction logic
    auth_claims = mock_claims.get("https://api.openai.com/auth", {})
    organizations = auth_claims.get("organizations", [])

    org_id = None
    if organizations:
        default_org = next(
            (org for org in organizations if org.get("is_default")), organizations[0]
        )
        org_id = default_org.get("id")

    assert org_id == "org-iydWjnSxSr51VuYhDVMDte5"

    # Test fallback to top-level org_id (should not happen in this case)
    if not org_id:
        org_id = mock_claims.get("organization_id")

    assert org_id == "org-iydWjnSxSr51VuYhDVMDte5"
    assert config.CHATGPT_OAUTH_CONFIG["required_port"] == 1455


def test_code_verifier_generation():
    """Test PKCE code verifier generation."""
    verifier = utils._generate_code_verifier()
    assert isinstance(verifier, str)
    assert len(verifier) > 50  # Should be long


def test_code_challenge_computation():
    """Test PKCE code challenge computation."""
    verifier = "test_verifier_string"
    challenge = utils._compute_code_challenge(verifier)
    assert isinstance(challenge, str)
    assert len(challenge) > 0
    # Should be URL-safe base64
    assert all(
        c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for c in challenge
    )


def test_prepare_oauth_context():
    """Test OAuth context preparation."""
    context = utils.prepare_oauth_context()
    assert context.state
    assert context.code_verifier
    assert context.code_challenge
    assert context.created_at > 0
    assert context.redirect_uri is None


def test_assign_redirect_uri():
    """Test redirect URI assignment."""
    context = utils.prepare_oauth_context()
    redirect_uri = utils.assign_redirect_uri(context, 1455)
    assert redirect_uri == "http://localhost:1455/auth/callback"
    assert context.redirect_uri == redirect_uri


def test_build_authorization_url():
    """Test authorization URL building."""
    context = utils.prepare_oauth_context()
    utils.assign_redirect_uri(context, 1455)
    auth_url = utils.build_authorization_url(context)

    assert auth_url.startswith("https://auth.openai.com/oauth/authorize?")
    assert "response_type=code" in auth_url
    assert "client_id=" in auth_url
    assert "redirect_uri=" in auth_url
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url
    assert f"state={context.state}" in auth_url


def test_parse_jwt_claims():
    """Test JWT claims parsing."""
    # Valid JWT structure (header.payload.signature)
    import base64

    payload = base64.urlsafe_b64encode(json.dumps({"sub": "user123"}).encode()).decode()
    token = f"header.{payload}.signature"

    claims = utils.parse_jwt_claims(token)
    assert claims is not None
    assert claims["sub"] == "user123"

    # Invalid token
    assert utils.parse_jwt_claims("") is None
    assert utils.parse_jwt_claims("invalid") is None


def test_save_and_load_tokens(tmp_path):
    """Test token storage and retrieval."""
    with patch.object(
        config, "get_token_storage_path", return_value=tmp_path / "tokens.json"
    ):
        tokens = {
            "access_token": "test_access",
            "refresh_token": "test_refresh",
            "api_key": "sk-test",
        }

        # Save tokens
        assert utils.save_tokens(tokens)

        # Load tokens
        loaded = utils.load_stored_tokens()
        assert loaded == tokens


def test_save_and_load_chatgpt_models(tmp_path):
    """Test ChatGPT models configuration."""
    with patch.object(
        config, "get_chatgpt_models_path", return_value=tmp_path / "chatgpt_models.json"
    ):
        models = {
            "chatgpt-gpt-4o": {
                "type": "openai",
                "name": "gpt-4o",
                "oauth_source": "chatgpt-oauth-plugin",
            }
        }

        # Save models
        assert utils.save_chatgpt_models(models)

        # Load models
        loaded = utils.load_chatgpt_models()
        assert loaded == models


def test_remove_chatgpt_models(tmp_path):
    """Test removal of ChatGPT models from config."""
    with patch.object(
        config, "get_chatgpt_models_path", return_value=tmp_path / "chatgpt_models.json"
    ):
        models = {
            "chatgpt-gpt-4o": {
                "type": "openai",
                "oauth_source": "chatgpt-oauth-plugin",
            },
            "claude-3-opus": {
                "type": "anthropic",
                "oauth_source": "other",
            },
        }
        utils.save_chatgpt_models(models)

        # Remove only ChatGPT models
        removed_count = utils.remove_chatgpt_models()
        assert removed_count == 1

        # Verify only ChatGPT model was removed
        remaining = utils.load_chatgpt_models()
        assert "chatgpt-gpt-4o" not in remaining
        assert "claude-3-opus" in remaining


@patch("code_puppy.plugins.chatgpt_oauth.utils.requests.post")
def test_exchange_code_for_tokens(mock_post):
    """Test authorization code exchange."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "test_access",
        "refresh_token": "test_refresh",
        "id_token": "test_id",
    }
    mock_post.return_value = mock_response

    context = utils.prepare_oauth_context()
    utils.assign_redirect_uri(context, 1455)

    tokens = utils.exchange_code_for_tokens("test_code", context)
    assert tokens is not None
    assert tokens["access_token"] == "test_access"
    assert "last_refresh" in tokens


@patch("code_puppy.plugins.chatgpt_oauth.utils.requests.get")
def test_fetch_chatgpt_models(mock_get):
    """Test fetching models from ChatGPT Codex API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    # New response format uses "models" key with "slug" field
    mock_response.json.return_value = {
        "models": [
            {"slug": "gpt-4o"},
            {"slug": "gpt-3.5-turbo"},
            {"slug": "o1-preview"},
            {"slug": "codex-mini"},
        ]
    }
    mock_get.return_value = mock_response

    models = utils.fetch_chatgpt_models("test_access_token", "test_account_id")
    assert models is not None
    assert "gpt-4o" in models
    assert "gpt-3.5-turbo" in models
    assert "o1-preview" in models
    assert "codex-mini" in models


@patch("code_puppy.plugins.chatgpt_oauth.utils.requests.get")
def test_fetch_chatgpt_models_fallback(mock_get):
    """Test that fetch_chatgpt_models returns default list on API failure."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = '{"detail":"Not Found"}'
    mock_get.return_value = mock_response

    models = utils.fetch_chatgpt_models("test_access_token", "test_account_id")
    assert models is not None
    # Should return default models
    assert "gpt-5.2" in models
    assert "gpt-4o" in models


def test_add_models_to_chatgpt_config(tmp_path):
    """Test adding models to chatgpt_models.json."""
    with patch.object(
        config, "get_chatgpt_models_path", return_value=tmp_path / "chatgpt_models.json"
    ):
        models = ["gpt-4o", "gpt-3.5-turbo"]

        assert utils.add_models_to_extra_config(models)

        loaded = utils.load_chatgpt_models()
        assert "chatgpt-gpt-4o" in loaded
        assert "chatgpt-gpt-3.5-turbo" in loaded
        assert loaded["chatgpt-gpt-4o"]["type"] == "chatgpt_oauth"
        assert loaded["chatgpt-gpt-4o"]["name"] == "gpt-4o"
        assert loaded["chatgpt-gpt-4o"]["oauth_source"] == "chatgpt-oauth-plugin"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
