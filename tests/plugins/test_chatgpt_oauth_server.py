"""ChatGPT OAuth server and flow tests.

Covers:
- OAuth server initialization
- Authorization URL generation
- Code exchange for tokens
- HTTP callback handling
- Error scenarios
"""

import time
from unittest.mock import Mock, patch

import pytest
import requests

from code_puppy.plugins.chatgpt_oauth.oauth_flow import (
    AuthBundle,
    TokenData,
    _CallbackHandler,
    _OAuthServer,
)
from code_puppy.plugins.chatgpt_oauth.utils import (
    OAuthContext,
    assign_redirect_uri,
    build_authorization_url,
    exchange_code_for_tokens,
    parse_authorization_error,
)

# ============================================================================
# FIXTURES
# ============================================================================


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


# ============================================================================
# OAuth Flow Tests
# ============================================================================


class TestOAuthFlow:
    """Test OAuth flow URL generation and code exchange."""

    def test_assign_redirect_uri(self, mock_oauth_context):
        """Test redirect URI assignment."""
        redirect_uri = assign_redirect_uri(mock_oauth_context, 1455)

        assert redirect_uri == "http://localhost:1455/auth/callback"
        assert mock_oauth_context.redirect_uri == redirect_uri

    def test_assign_redirect_uri_none_context_raises(self):
        """Test assign_redirect_uri with None context raises error."""
        with pytest.raises(RuntimeError):
            assign_redirect_uri(None, 1455)

    def test_assign_redirect_uri_wrong_port_raises(self, mock_oauth_context):
        """Test assign_redirect_uri with wrong port raises error."""
        with pytest.raises(RuntimeError, match="must use port 1455"):
            assign_redirect_uri(mock_oauth_context, 9999)

    def test_build_authorization_url(self, mock_oauth_context):
        """Test authorization URL is built correctly."""
        url = build_authorization_url(mock_oauth_context)

        assert "auth.openai.com" in url
        assert "response_type=code" in url
        assert "client_id=" in url
        assert "scope=openid" in url
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url
        assert "state=" in url

    def test_build_authorization_url_no_redirect_uri(self):
        """Test build_authorization_url fails without redirect URI."""
        context = OAuthContext(
            state="test",
            code_verifier="test",
            code_challenge="test",
            created_at=time.time(),
            redirect_uri=None,  # Missing!
        )

        with pytest.raises(RuntimeError, match="Redirect URI"):
            build_authorization_url(context)

    @patch("requests.post")
    def test_exchange_code_for_tokens_success(
        self, mock_post, mock_oauth_context, sample_token_data
    ):
        """Test successful code exchange."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_token_data
        mock_post.return_value = mock_response

        result = exchange_code_for_tokens("test_code", mock_oauth_context)

        assert result is not None
        assert result["access_token"] == sample_token_data["access_token"]
        assert "last_refresh" in result  # Should add timestamp

    @patch("requests.post")
    def test_exchange_code_for_tokens_expired_context(
        self, mock_post, sample_token_data
    ):
        """Test code exchange fails with expired context."""
        expired_context = OAuthContext(
            state="test",
            code_verifier="test",
            code_challenge="test",
            created_at=time.time() - 600,
            expires_at=time.time() - 300,
            redirect_uri="http://localhost:1455/auth/callback",
        )

        result = exchange_code_for_tokens("test_code", expired_context)

        assert result is None

    @patch("requests.post")
    def test_exchange_code_for_tokens_http_error(self, mock_post, mock_oauth_context):
        """Test code exchange handles HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        result = exchange_code_for_tokens("bad_code", mock_oauth_context)

        assert result is None

    @patch("requests.post")
    def test_exchange_code_for_tokens_network_error(
        self, mock_post, mock_oauth_context
    ):
        """Test code exchange handles network errors."""
        mock_post.side_effect = requests.ConnectionError("Network error")

        result = exchange_code_for_tokens("test_code", mock_oauth_context)

        assert result is None

    @patch("requests.post")
    def test_exchange_code_for_tokens_timeout(self, mock_post, mock_oauth_context):
        """Test code exchange handles timeouts."""
        mock_post.side_effect = requests.Timeout("Request timed out")

        result = exchange_code_for_tokens("test_code", mock_oauth_context)

        assert result is None

    def test_parse_authorization_error(self):
        """Test parsing OAuth error from callback URL."""
        error_url = "http://localhost:1455/auth/callback?error=access_denied&error_description=User%20denied%20access"

        error = parse_authorization_error(error_url)

        assert "access_denied" in error
        assert "User denied access" in error

    def test_parse_authorization_error_no_error(self):
        """Test parsing URL without error returns None."""
        url = "http://localhost:1455/auth/callback?code=test_code"

        error = parse_authorization_error(url)

        assert error is None

    def test_parse_authorization_error_invalid_url(self):
        """Test parsing invalid URL returns None gracefully."""
        error = parse_authorization_error("not a url at all")
        assert error is None


# ============================================================================
# OAuth Server Tests
# ============================================================================


class TestOAuthServer:
    """Test OAuth server initialization and operations."""

    def test_oauth_server_init(self):
        """Test OAuth server initializes correctly."""
        server = _OAuthServer(client_id="test_client_id")

        assert server.client_id == "test_client_id"
        assert server.exit_code == 1  # Initial failure state
        assert server.context is not None
        assert server.redirect_uri is not None

        server.server_close()

    def test_oauth_server_auth_url(self):
        """Test auth URL is generated with all parameters."""
        server = _OAuthServer(client_id="test_client_id")

        url = server.auth_url()

        assert "auth.openai.com" in url
        assert "response_type=code" in url
        assert "client_id=test_client_id" in url
        assert "code_challenge_method=S256" in url

        server.server_close()

    @patch("requests.post")
    def test_exchange_code_success(self, mock_post):
        """Test successful code exchange."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "id_token": "id_token_value",
            "access_token": "access_token_value",
            "refresh_token": "refresh_token_value",
        }
        mock_post.return_value = mock_response

        server = _OAuthServer(client_id="test_client_id")

        with patch(
            "code_puppy.plugins.chatgpt_oauth.oauth_flow.parse_jwt_claims"
        ) as mock_parse:
            mock_parse.return_value = {
                "https://api.openai.com/auth": {"chatgpt_account_id": "acc_123"},
                "organization_id": "org_123",
            }

            bundle, success_url = server.exchange_code("test_code")

            assert isinstance(bundle, AuthBundle)
            assert bundle.token_data.access_token == "access_token_value"
            assert "success" in success_url

        server.server_close()

    @patch("requests.post")
    def test_exchange_code_network_error(self, mock_post):
        """Test exchange code handles network errors."""
        mock_post.side_effect = requests.ConnectionError("Network error")

        server = _OAuthServer(client_id="test_client_id")

        with pytest.raises(requests.ConnectionError):
            server.exchange_code("test_code")

        server.server_close()

    def test_token_data_creation(self):
        """Test TokenData dataclass creation and attributes."""
        token_data = TokenData(
            id_token="test_id_token",
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            account_id="test_account_id",
        )

        assert token_data.id_token == "test_id_token"
        assert token_data.access_token == "test_access_token"
        assert token_data.refresh_token == "test_refresh_token"
        assert token_data.account_id == "test_account_id"

    def test_auth_bundle_creation(self):
        """Test AuthBundle dataclass creation and attributes."""
        token_data = TokenData(
            id_token="test_id_token",
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            account_id="test_account_id",
        )

        bundle = AuthBundle(
            api_key="test_api_key",
            token_data=token_data,
            last_refresh="2023-01-01T00:00:00Z",
        )

        assert bundle.api_key == "test_api_key"
        assert bundle.token_data == token_data
        assert bundle.last_refresh == "2023-01-01T00:00:00Z"


# ============================================================================
# Callback Handler Tests
# ============================================================================


class TestCallbackHandler:
    """Test OAuth callback HTTP handling."""

    @pytest.fixture
    def mock_server(self):
        """Mock OAuth server for testing."""
        server = Mock(spec=_OAuthServer)
        server.exit_code = 1
        server.verbose = False
        return server

    def test_callback_handler_success_endpoint(self, mock_server):
        """Test success endpoint returns HTML."""
        mock_request = Mock()
        with patch(
            "code_puppy.plugins.chatgpt_oauth.oauth_flow._CallbackHandler.handle_one_request"
        ):
            handler = _CallbackHandler(mock_request, ("localhost", 1455), mock_server)
            handler.server = mock_server
            handler.requestline = "GET / HTTP/1.1"

            with patch.object(handler, "_send_html") as mock_send:
                with patch.object(handler, "_shutdown_after_delay"):
                    handler.path = "/success"
                    handler.do_GET()

                    mock_send.assert_called_once()
                    html = mock_send.call_args[0][0]
                    assert "ChatGPT" in html

    def test_callback_handler_invalid_path(self, mock_server):
        """Test invalid path returns 404."""
        mock_request = Mock()
        with patch(
            "code_puppy.plugins.chatgpt_oauth.oauth_flow._CallbackHandler.handle_one_request"
        ):
            handler = _CallbackHandler(mock_request, ("localhost", 1455), mock_server)
            handler.server = mock_server
            handler.requestline = "GET / HTTP/1.1"

            with patch.object(handler, "_send_failure") as mock_failure:
                with patch.object(handler, "_shutdown"):
                    handler.path = "/invalid"
                    handler.do_GET()

                    mock_failure.assert_called_once()
                    assert mock_failure.call_args[0][0] == 404

    def test_callback_handler_post_not_supported(self, mock_server):
        """Test POST requests return 404."""
        mock_request = Mock()
        with patch(
            "code_puppy.plugins.chatgpt_oauth.oauth_flow._CallbackHandler.handle_one_request"
        ):
            handler = _CallbackHandler(mock_request, ("localhost", 1455), mock_server)
            handler.server = mock_server
            handler.requestline = "POST / HTTP/1.1"

            with patch.object(handler, "_send_failure") as mock_failure:
                with patch.object(handler, "_shutdown"):
                    handler.do_POST()

                    mock_failure.assert_called_once()
                    assert "pups only fetch GET" in mock_failure.call_args[0][1]
