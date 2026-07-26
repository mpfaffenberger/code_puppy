"""Tests for the Grok (x.ai) OAuth plugin."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from code_puppy.plugins.grok_oauth import config as grok_config
from code_puppy.plugins.grok_oauth import register_callbacks as rc
from code_puppy.plugins.grok_oauth import utils
from code_puppy.plugins.grok_oauth.config import GROK_OAUTH_CONFIG


@pytest.fixture
def token_path(tmp_path):
    path = tmp_path / "grok_oauth.json"
    with (
        patch.object(grok_config, "get_token_storage_path", return_value=path),
        patch.object(utils, "get_token_storage_path", return_value=path),
        patch.object(rc, "get_token_storage_path", return_value=path),
    ):
        yield path


def _save_valid_tokens(**overrides):
    tokens = {
        "access_token": "fake-token",
        "refresh_token": "fake-refresh",
        "expires_at": time.time() + 3600,
        "token_endpoint": "https://auth.x.ai/oauth2/token",
    }
    tokens.update(overrides)
    assert utils.save_tokens(tokens)
    return tokens


def test_config_values():
    assert GROK_OAUTH_CONFIG["issuer"] == "https://auth.x.ai"
    assert "grok-cli:access" in GROK_OAUTH_CONFIG["scope"]
    assert "api:access" in GROK_OAUTH_CONFIG["scope"]
    assert GROK_OAUTH_CONFIG["api_base_url"] == "https://api.x.ai/v1"
    assert GROK_OAUTH_CONFIG["default_model"] in grok_config.GROK_MODELS


def test_pkce_pair_shape():
    verifier, challenge = utils.generate_pkce_pair()
    assert len(verifier) >= 43
    assert "=" not in verifier and "=" not in challenge
    # Deterministic: same verifier always hashes to the same challenge
    import base64
    import hashlib

    digest = hashlib.sha256(verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    assert challenge == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://auth.x.ai/oauth2/token",  # not https
        "https://evil.com/oauth2/token",  # wrong host
        "https://notx.ai/oauth2/token",  # suffix trickery
        "https://x.ai.evil.com/token",  # prefix trickery
    ],
)
def test_validate_xai_endpoint_rejects(url):
    with pytest.raises(ValueError):
        utils.validate_xai_endpoint(url)


def test_validate_xai_endpoint_accepts():
    assert utils.validate_xai_endpoint("https://auth.x.ai/oauth2/token")
    assert utils.validate_xai_endpoint("https://x.ai/oauth2/token")


def test_save_and_load_tokens(token_path):
    _save_valid_tokens()
    loaded = utils.load_stored_tokens()
    assert loaded["access_token"] == "fake-token"
    assert oct(token_path.stat().st_mode & 0o777) == oct(0o600)


def test_get_valid_access_token_fresh(token_path):
    _save_valid_tokens()
    assert utils.get_valid_access_token() == "fake-token"


def test_get_valid_access_token_refreshes_expired(token_path):
    _save_valid_tokens(access_token="stale", expires_at=time.time() - 10)
    payload = {
        "access_token": "fresh-token",
        "refresh_token": "new-refresh",
        "expires_in": 3600,
    }
    with patch.object(utils, "exchange_token", return_value=payload) as exchange:
        assert utils.get_valid_access_token() == "fresh-token"

    body = exchange.call_args[0][1]
    assert body["grant_type"] == "refresh_token"
    assert body["client_id"] == GROK_OAUTH_CONFIG["client_id"]
    assert utils.load_stored_tokens()["refresh_token"] == "new-refresh"


def test_get_valid_access_token_unauthenticated(token_path):
    assert utils.get_valid_access_token() is None


def test_load_grok_models_requires_auth(token_path):
    assert rc._load_grok_models() == {}


def test_load_grok_models_when_authenticated(token_path):
    _save_valid_tokens()
    models = rc._load_grok_models()
    assert "xai-grok-4.5" in models
    entry = models["xai-grok-4.5"]
    assert entry["type"] == "grok_oauth"
    assert entry["name"] == "grok-4.5"
    assert entry["context_length"] == 500_000


def test_model_type_registration():
    handlers = rc._register_model_types()
    assert handlers == [{"type": "grok_oauth", "handler": rc._create_grok_oauth_model}]


def test_create_model_returns_none_without_auth(token_path):
    model = rc._create_grok_oauth_model("xai-grok-4.5", {"name": "grok-4.5"}, {})
    assert model is None


def test_create_model_when_authenticated(token_path):
    _save_valid_tokens()
    model = rc._create_grok_oauth_model("xai-grok-4.5", {"name": "grok-4.5"}, {})
    assert type(model).__name__ == "OpenAIResponsesModel"
    assert model.model_name == "grok-4.5"


def test_custom_command_ignores_unknown():
    assert rc._handle_custom_command("/other", "not-ours") is None
    assert rc._handle_custom_command("/other", "") is None


def test_custom_command_handles_status(token_path):
    assert rc._handle_custom_command("/grok-status", "grok-status") is True


def test_custom_command_logout(token_path):
    _save_valid_tokens()
    assert rc._handle_custom_command("/grok-logout", "grok-logout") is True
    assert not token_path.exists()


def test_custom_help_entries():
    entries = rc._custom_help()
    names = [name for name, _ in entries]
    assert names == ["grok-auth", "grok-status", "grok-logout"]
