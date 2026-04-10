"""Tests for the copilot_auth plugin's _create_copilot_model and _CopilotAuth.

Verifies that the dynamic token refresh auth flow correctly refreshes
the Copilot session token before every HTTP request, preventing the
30-minute token expiry issue during long-running conversations.
"""

from dataclasses import dataclass
from unittest.mock import patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeCopilotToken:
    host: str
    oauth_token: str
    user: str = ""


FAKE_CONFIG = {
    "editor_version": "JetBrains-IU/2024.3",
    "editor_plugin_version": "copilot/2.0.0",
    "copilot_integration_id": "vscode-chat",
    "openai_intent": "conversation-panel",
    "api_base_url": "https://api.githubcopilot.com",
    "prefix": "copilot-",
}


def _model_config(name: str = "gpt-4o", host: str = "github.com") -> dict:
    return {
        "name": name,
        "copilot_host": host,
        "custom_endpoint": {"url": "https://custom.example.com/v1"},
    }


# ---------------------------------------------------------------------------
# _CopilotAuth auth flow tests
# ---------------------------------------------------------------------------

class TestCopilotAuth:
    """Test the _CopilotAuth httpx.Auth subclass injected per-request."""

    def _make_auth(self, oauth_token: str = "ghp_fake123", host: str = "github.com"):
        """Import and instantiate _CopilotAuth from within _create_copilot_model's closure.

        Since _CopilotAuth is defined inside _create_copilot_model, we replicate
        it here for direct unit testing.  The integration test below validates
        the real wiring.
        """
        import httpx as _httpx

        from code_puppy.plugins.copilot_auth.utils import get_valid_session_token

        class _CopilotAuth(_httpx.Auth):
            def __init__(self, oauth_token: str, token_host: str):
                self._oauth_token = oauth_token
                self._host = token_host

            def auth_flow(self, request: _httpx.Request):
                token = get_valid_session_token(self._oauth_token, self._host)
                if token:
                    request.headers["Authorization"] = f"Bearer {token}"
                yield request

        return _CopilotAuth(oauth_token, host)

    @patch("code_puppy.plugins.copilot_auth.utils.get_valid_session_token")
    def test_auth_flow_sets_authorization_header(self, mock_get_token):
        """Auth flow should set Authorization header with fresh session token."""
        mock_get_token.return_value = "fresh_session_token_abc"

        auth = self._make_auth("ghp_oauth_token", "github.com")
        request = httpx.Request("POST", "https://api.githubcopilot.com/chat/completions")

        # Exhaust the generator (httpx auth_flow protocol)
        flow = auth.auth_flow(request)
        modified_request = next(flow)

        assert modified_request.headers["Authorization"] == "Bearer fresh_session_token_abc"
        mock_get_token.assert_called_once_with("ghp_oauth_token", "github.com")

    @patch("code_puppy.plugins.copilot_auth.utils.get_valid_session_token")
    def test_auth_flow_skips_header_when_token_is_none(self, mock_get_token):
        """Auth flow should not set Authorization if get_valid_session_token returns None."""
        mock_get_token.return_value = None

        auth = self._make_auth("ghp_dead_token", "github.com")
        request = httpx.Request("POST", "https://api.githubcopilot.com/chat/completions")

        flow = auth.auth_flow(request)
        modified_request = next(flow)

        assert "Authorization" not in modified_request.headers
        mock_get_token.assert_called_once()

    @patch("code_puppy.plugins.copilot_auth.utils.get_valid_session_token")
    def test_auth_flow_refreshes_on_every_call(self, mock_get_token):
        """Each request should trigger a fresh get_valid_session_token call."""
        mock_get_token.side_effect = ["token_1", "token_2", "token_3"]

        auth = self._make_auth()

        for i, expected in enumerate(["token_1", "token_2", "token_3"], 1):
            request = httpx.Request("POST", "https://api.githubcopilot.com/chat/completions")
            flow = auth.auth_flow(request)
            modified = next(flow)
            assert modified.headers["Authorization"] == f"Bearer {expected}"

        assert mock_get_token.call_count == 3

    @patch("code_puppy.plugins.copilot_auth.utils.get_valid_session_token")
    def test_auth_flow_passes_correct_host(self, mock_get_token):
        """Auth flow should pass the configured host to get_valid_session_token."""
        mock_get_token.return_value = "ghe_token"

        auth = self._make_auth("ghp_enterprise", "github.enterprise.com")
        request = httpx.Request("POST", "https://api.githubcopilot.com/chat/completions")

        flow = auth.auth_flow(request)
        next(flow)

        mock_get_token.assert_called_once_with("ghp_enterprise", "github.enterprise.com")


# ---------------------------------------------------------------------------
# _create_copilot_model integration tests
# ---------------------------------------------------------------------------

class TestCreateCopilotModel:
    """Test the _create_copilot_model factory function."""

    MODULE = "code_puppy.plugins.copilot_auth.register_callbacks"

    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_token_for_host")
    def test_returns_none_when_no_token(self, mock_get_token):
        """Should return None and warn when no Copilot token is available."""
        mock_get_token.return_value = None

        from code_puppy.plugins.copilot_auth.register_callbacks import (
            _create_copilot_model,
        )

        with patch(f"{self.MODULE}.emit_warning") as mock_warn:
            result = _create_copilot_model("copilot-gpt-4o", _model_config(), {})

        assert result is None
        mock_warn.assert_called_once()
        assert "No Copilot token" in mock_warn.call_args[0][0]

    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_valid_session_token")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_token_for_host")
    def test_returns_none_when_session_token_fails(self, mock_get_token, mock_session):
        """Should return None when session token exchange fails."""
        mock_get_token.return_value = FakeCopilotToken(
            host="github.com", oauth_token="ghp_test"
        )
        mock_session.return_value = None

        from code_puppy.plugins.copilot_auth.register_callbacks import (
            _create_copilot_model,
        )

        with patch(f"{self.MODULE}.emit_warning") as mock_warn:
            result = _create_copilot_model("copilot-gpt-4o", _model_config(), {})

        assert result is None
        mock_warn.assert_called_once()
        assert "session token" in mock_warn.call_args[0][0]

    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_api_endpoint_for_host")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_valid_session_token")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_token_for_host")
    def test_creates_model_with_dynamic_auth(
        self, mock_get_token, mock_session, mock_endpoint
    ):
        """Should create an OpenAIChatModel with _CopilotAuth attached to the client."""
        mock_get_token.return_value = FakeCopilotToken(
            host="github.com", oauth_token="ghp_real"
        )
        mock_session.return_value = "initial_session_token"
        mock_endpoint.return_value = "https://api.githubcopilot.com"

        from code_puppy.plugins.copilot_auth.register_callbacks import (
            _create_copilot_model,
        )

        config = _model_config()
        result = _create_copilot_model("copilot-gpt-4o", config, {})

        assert result is not None
        # Verify the model was created
        assert hasattr(result, "provider")

        # Verify the HTTP client has auth attached
        # provider.client is AsyncOpenAI; provider.client._client is the httpx client
        http_client = result.provider.client._client
        assert http_client.auth is not None
        # The auth should be an instance of the inner _CopilotAuth class
        assert hasattr(http_client.auth, "_oauth_token")
        assert http_client.auth._oauth_token == "ghp_real"
        assert http_client.auth._host == "github.com"

    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_api_endpoint_for_host")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_valid_session_token")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_token_for_host")
    def test_provider_uses_placeholder_api_key(
        self, mock_get_token, mock_session, mock_endpoint
    ):
        """Provider should use a placeholder API key, not the session token."""
        mock_get_token.return_value = FakeCopilotToken(
            host="github.com", oauth_token="ghp_real"
        )
        mock_session.return_value = "session_token_that_expires"
        mock_endpoint.return_value = "https://api.githubcopilot.com"

        from code_puppy.plugins.copilot_auth.register_callbacks import (
            _create_copilot_model,
        )

        result = _create_copilot_model("copilot-gpt-4o", _model_config(), {})
        assert result is not None

        # The provider should NOT have the session token baked in as api_key.
        # The api_key lives on the AsyncOpenAI client inside the provider.
        assert result.provider.client.api_key == "copilot-session-managed"

    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_api_endpoint_for_host")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_valid_session_token")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_token_for_host")
    def test_falls_back_to_config_url(
        self, mock_get_token, mock_session, mock_endpoint
    ):
        """Should use custom_endpoint URL when api endpoint matches default."""
        mock_get_token.return_value = FakeCopilotToken(
            host="github.com", oauth_token="ghp_real"
        )
        mock_session.return_value = "tok"
        # Return the default — triggers fallback to config URL
        mock_endpoint.return_value = FAKE_CONFIG["api_base_url"]

        from code_puppy.plugins.copilot_auth.register_callbacks import (
            _create_copilot_model,
        )

        config = _model_config()
        result = _create_copilot_model("copilot-gpt-4o", config, {})
        assert result is not None

        # Should have fallen back to the custom_endpoint URL
        provider = result.provider
        assert "custom.example.com" in str(provider.base_url)

    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_api_endpoint_for_host")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_valid_session_token")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_token_for_host")
    def test_uses_discovered_endpoint(
        self, mock_get_token, mock_session, mock_endpoint
    ):
        """Should use the discovered endpoint when it differs from default."""
        mock_get_token.return_value = FakeCopilotToken(
            host="github.com", oauth_token="ghp_real"
        )
        mock_session.return_value = "tok"
        mock_endpoint.return_value = "https://copilot-proxy.us-east.com"

        from code_puppy.plugins.copilot_auth.register_callbacks import (
            _create_copilot_model,
        )

        result = _create_copilot_model("copilot-gpt-4o", _model_config(), {})
        assert result is not None

        provider = result.provider
        assert "copilot-proxy.us-east.com" in str(provider.base_url)

    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_api_endpoint_for_host")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_valid_session_token")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_token_for_host")
    def test_client_has_copilot_headers(
        self, mock_get_token, mock_session, mock_endpoint
    ):
        """HTTP client should include Copilot-specific headers."""
        mock_get_token.return_value = FakeCopilotToken(
            host="github.com", oauth_token="ghp_real"
        )
        mock_session.return_value = "tok"
        mock_endpoint.return_value = "https://api.githubcopilot.com"

        from code_puppy.plugins.copilot_auth.register_callbacks import (
            _create_copilot_model,
        )

        result = _create_copilot_model("copilot-gpt-4o", _model_config(), {})
        assert result is not None

        client = result.provider.client._client
        client_headers = dict(client.headers)

        assert client_headers.get("editor-version") == FAKE_CONFIG["editor_version"]
        assert client_headers.get("editor-plugin-version") == FAKE_CONFIG["editor_plugin_version"]
        assert client_headers.get("copilot-integration-id") == FAKE_CONFIG["copilot_integration_id"]
        assert client_headers.get("openai-intent") == FAKE_CONFIG["openai_intent"]

    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_api_endpoint_for_host")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_valid_session_token")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_token_for_host")
    def test_ghe_host_is_passed_through(
        self, mock_get_token, mock_session, mock_endpoint
    ):
        """Should pass GHE host through to token lookups and auth."""
        ghe_host = "github.enterprise.corp"
        mock_get_token.return_value = FakeCopilotToken(
            host=ghe_host, oauth_token="ghp_ghe"
        )
        mock_session.return_value = "ghe_session"
        mock_endpoint.return_value = "https://copilot-proxy.enterprise.corp"

        from code_puppy.plugins.copilot_auth.register_callbacks import (
            _create_copilot_model,
        )

        config = _model_config(host=ghe_host)
        result = _create_copilot_model("copilot-gpt-4o", config, {})
        assert result is not None

        mock_get_token.assert_called_once_with(ghe_host)
        mock_session.assert_called_once_with("ghp_ghe", ghe_host)

        # Auth should use the GHE host
        auth = result.provider.client._client.auth
        assert auth._host == ghe_host

    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_api_endpoint_for_host")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_valid_session_token")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_token_for_host")
    def test_claude_model_has_interleaved_thinking_profile(
        self, mock_get_token, mock_session, mock_endpoint
    ):
        """Claude models should send thinking parts back via field mode.

        This ensures interleaved thinking works across tool calls —
        without it, thinking only appears on the first response.
        """
        mock_get_token.return_value = FakeCopilotToken(
            host="github.com", oauth_token="ghp_real"
        )
        mock_session.return_value = "tok"
        mock_endpoint.return_value = "https://api.githubcopilot.com"

        from code_puppy.plugins.copilot_auth.register_callbacks import (
            _create_copilot_model,
        )

        # Claude underlying model — should get thinking profile
        config = _model_config(name="claude-sonnet-4")
        result = _create_copilot_model("copilot-claude-sonnet-4", config, {})
        assert result is not None

        from pydantic_ai.profiles.openai import OpenAIModelProfile

        profile = OpenAIModelProfile.from_profile(result.profile)
        assert profile.openai_chat_thinking_field == "reasoning_text"
        assert profile.openai_supports_reasoning is True
        # Must be 'field' — NOT False — so thinking persists across tool calls
        assert profile.openai_chat_send_back_thinking_parts == "field"

    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_api_endpoint_for_host")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_valid_session_token")
    @patch(f"code_puppy.plugins.copilot_auth.register_callbacks.get_token_for_host")
    def test_non_claude_model_has_no_thinking_profile(
        self, mock_get_token, mock_session, mock_endpoint
    ):
        """Non-Claude models (e.g. GPT) should NOT get a thinking profile."""
        mock_get_token.return_value = FakeCopilotToken(
            host="github.com", oauth_token="ghp_real"
        )
        mock_session.return_value = "tok"
        mock_endpoint.return_value = "https://api.githubcopilot.com"

        from code_puppy.plugins.copilot_auth.register_callbacks import (
            _create_copilot_model,
        )

        # GPT model — should NOT get a custom thinking profile
        config = _model_config(name="gpt-4o")
        result = _create_copilot_model("copilot-gpt-4o", config, {})
        assert result is not None

        from pydantic_ai.profiles.openai import OpenAIModelProfile

        profile = OpenAIModelProfile.from_profile(result.profile)
        # No thinking field should be configured for GPT models
        assert profile.openai_chat_thinking_field is None
