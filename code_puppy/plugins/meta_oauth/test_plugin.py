"""Tests for the Meta Muse OAuth plugin."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from code_puppy.plugins.meta_oauth import config as meta_config
from code_puppy.plugins.meta_oauth import oauth_flow
from code_puppy.plugins.meta_oauth import register_callbacks as rc
from code_puppy.plugins.meta_oauth import utils
from code_puppy.plugins.meta_oauth.config import META_OAUTH_CONFIG


@pytest.fixture
def credential_paths(tmp_path, monkeypatch):
    own = tmp_path / "code-puppy" / "meta_oauth.json"
    own.parent.mkdir()
    muse = tmp_path / "muse" / "auth.json"
    muse.parent.mkdir()
    monkeypatch.delenv("META_API_KEY", raising=False)
    with (
        patch.object(meta_config, "get_token_storage_path", return_value=own),
        patch.object(utils, "get_token_storage_path", return_value=own),
        patch.object(rc, "get_token_storage_path", return_value=own),
        patch.object(meta_config, "get_muse_auth_path", return_value=muse),
        patch.object(utils, "get_muse_auth_path", return_value=muse),
    ):
        rc._model_cache = None
        yield own, muse
        rc._model_cache = None


def _response(status: int, payload: dict) -> Mock:
    response = Mock()
    response.status_code = status
    response.ok = 200 <= status < 300
    response.json.return_value = payload
    return response


def _credentials(**overrides):
    data = {
        "api_key": "LLM-fake",
        "access_token": "oauth-fake",
        "api_base_url": "https://api.meta.ai/v1",
        "models": {
            "muse-spark-1.2-contributor": {
                "context_length": 1_007_997,
                "supported_settings": ["reasoning_effort"],
            }
        },
    }
    data.update(overrides)
    return data


def test_config_matches_official_muse_flow():
    assert META_OAUTH_CONFIG["auth_base_url"] == "https://auth.meta.com"
    assert META_OAUTH_CONFIG["client_id"] == "1031625952748946"
    assert META_OAUTH_CONFIG["device_authorization_path"].startswith("/oidc/device/")
    assert META_OAUTH_CONFIG["mint_url"] == "https://api.meta.ai/muse-code/key"
    assert META_OAUTH_CONFIG["api_base_url"] == "https://api.meta.ai/v1"


@pytest.mark.parametrize(
    "url",
    [
        "http://api.meta.ai/v1",
        "https://evil.example/v1",
        "https://api.meta.ai.evil.example/v1",
    ],
)
def test_validate_api_base_url_rejects_untrusted_hosts(url):
    with pytest.raises(ValueError):
        utils.validate_api_base_url(url)


def test_validate_meta_urls_accept_expected_hosts():
    assert utils.validate_api_base_url("https://api.meta.ai/v1")
    assert utils.validate_verification_url("https://auth.meta.com/device")
    assert utils.validate_verification_url("https://meta.com/device")


def test_save_and_load_code_puppy_credentials(credential_paths):
    own, _ = credential_paths
    assert utils.save_credentials(_credentials())
    loaded = utils.load_credentials()
    assert loaded["api_key"] == "LLM-fake"
    assert loaded["_source"] == "code-puppy"
    assert own.stat().st_mode & 0o777 == 0o600


def test_loads_official_muse_credentials(credential_paths):
    _, muse = credential_paths
    muse.write_text(json.dumps({"providers": {"meta": _credentials()}}))
    loaded = utils.load_credentials()
    assert loaded["api_key"] == "LLM-fake"
    assert loaded["_source"] == "muse"


def test_malformed_muse_credentials_are_ignored(credential_paths):
    _, muse = credential_paths
    muse.write_text(json.dumps({"providers": None}))
    assert utils.load_credentials() is None


def test_environment_credential_has_highest_precedence(credential_paths, monkeypatch):
    assert utils.save_credentials(_credentials(api_key="saved"))
    monkeypatch.setenv("META_API_KEY", "environment")
    loaded = utils.load_credentials()
    assert loaded["api_key"] == "environment"
    assert loaded["_source"] == "environment"


def test_request_device_authorization_uses_public_client():
    payload = {
        "device_code": "device",
        "user_code": "PUPPY",
        "verification_uri": "https://auth.meta.com/device",
    }
    with patch.object(
        utils.requests, "post", return_value=_response(200, payload)
    ) as post:
        assert utils.request_device_authorization() == payload
    assert post.call_args.kwargs["data"] == {
        "client_id": META_OAUTH_CONFIG["client_id"]
    }
    assert post.call_args.kwargs["allow_redirects"] is False


def test_poll_device_token_handles_pending_and_success():
    pending = _response(400, {"error": "authorization_pending"})
    success = _response(200, {"access_token": "oauth-token"})
    with patch.object(utils.requests, "post", side_effect=[pending, success]):
        assert utils.poll_device_token("device")[0] == "authorization_pending"
        state, payload = utils.poll_device_token("device")
    assert state == "authorized"
    assert payload["access_token"] == "oauth-token"


def test_mint_api_credentials_uses_bearer_and_validates_base_url():
    response = _response(
        200,
        {
            "api_key": "LLM-minted",
            "base_url": "https://api.meta.ai/v1",
            "user_email": "puppy@example.test",
        },
    )
    with patch.object(utils.requests, "post", return_value=response) as post:
        minted = utils.mint_api_credentials("oauth-token")
    assert minted["api_key"] == "LLM-minted"
    assert minted["api_base_url"] == "https://api.meta.ai/v1"
    assert "base_url" not in minted
    headers = post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer oauth-token"
    assert headers["x-api-version"] == "1.0.0"


def test_discover_models_converts_muse_metadata():
    response = _response(
        200,
        {
            "data": [
                {
                    "id": "muse-spark-1.2",
                    "metadata": {
                        "muse-code": {
                            "is_hidden": False,
                            "reasoning": True,
                            "limit": {"context": 1_007_997},
                        }
                    },
                },
                {
                    "id": "hidden-model",
                    "metadata": {"muse-code": {"is_hidden": True}},
                },
            ]
        },
    )
    with patch.object(utils.requests, "get", return_value=response):
        models = utils.discover_models(_credentials())
    assert models == {
        "muse-spark-1.2": {
            "context_length": 1_007_997,
            "supported_settings": ["reasoning_effort"],
        }
    }


def test_oauth_flow_mints_discovers_and_saves():
    device = {
        "device_code": "device",
        "user_code": "PUPPY",
        "verification_uri": "https://auth.meta.com/device",
    }
    token = {"access_token": "oauth-token", "refresh_token": "refresh"}
    minted = {"api_key": "LLM-key", "api_base_url": "https://api.meta.ai/v1"}
    with (
        patch.object(oauth_flow, "load_credentials", return_value=None),
        patch.object(oauth_flow, "request_device_authorization", return_value=device),
        patch.object(oauth_flow, "_open_verification_page"),
        patch.object(oauth_flow, "_poll_for_access_token", return_value=token),
        patch.object(oauth_flow, "mint_api_credentials", return_value=minted),
        patch.object(
            oauth_flow, "discover_models", return_value=_credentials()["models"]
        ),
        patch.object(oauth_flow, "save_credentials", return_value=True) as save,
    ):
        assert oauth_flow.run_oauth_flow() is True
    saved = save.call_args.args[0]
    assert saved["access_token"] == "oauth-token"
    assert saved["api_key"] == "LLM-key"
    assert saved["models"]


def test_model_catalogue_and_type_registration(credential_paths):
    assert utils.save_credentials(_credentials())
    models = rc._load_meta_models()
    entry = models["meta-muse-spark-1.2-contributor"]
    assert entry["type"] == "meta_oauth"
    assert entry["provider"] == "meta"
    assert entry["context_length"] == 1_007_997
    assert rc._register_model_types() == [
        {"type": "meta_oauth", "handler": rc._create_meta_oauth_model}
    ]


def test_create_model_uses_responses_api(credential_paths):
    assert utils.save_credentials(_credentials())
    model = rc._create_meta_oauth_model(
        "meta-muse-spark-1.2-contributor",
        {"name": "muse-spark-1.2-contributor"},
        {},
    )
    assert type(model).__name__ == "OpenAIResponsesModel"
    assert model.model_name == "muse-spark-1.2-contributor"
    assert model.system == "meta"


def test_commands_and_help(credential_paths):
    assert rc._handle_custom_command("/unknown", "unknown") is None
    assert rc._handle_custom_command("/meta-status", "meta-status") is True
    assert rc._handle_custom_command("/meta-logout", "meta-logout") is True
    assert [name for name, _ in rc._custom_help()] == [
        "meta-auth",
        "meta-status",
        "meta-logout",
    ]
