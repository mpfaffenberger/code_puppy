"""
Tests for code_puppy.plugins.walmart_specific.devcontainer_detection

Covers detection of VS Code devcontainers and manual override via AUTH_CALLBACK_URL.
"""

import os
from unittest.mock import patch

import pytest

from code_puppy.plugins.walmart_specific.devcontainer_detection import (
    _ensure_save_token_endpoint,
    _replace_port_placeholder,
    get_devcontainer_callback_url,
    is_remote_environment,
)


# ---------------------------------------------------------------------------
# _replace_port_placeholder
# ---------------------------------------------------------------------------


class TestReplacePortPlaceholder:
    """Test port placeholder replacement in URLs."""

    def test_vscode_style_double_braces(self):
        """VS Code uses {{port}} style placeholders."""
        url = "https://example.com/proxy/{{port}}/"
        assert _replace_port_placeholder(url, 8091) == "https://example.com/proxy/8091/"

    def test_python_style_single_braces(self):
        """Python f-string style {port} placeholders."""
        url = "https://example.com/proxy/{port}/"
        assert _replace_port_placeholder(url, 8091) == "https://example.com/proxy/8091/"

    def test_no_placeholder(self):
        """URL without placeholder is returned unchanged."""
        url = "https://example.com/callback"
        assert _replace_port_placeholder(url, 8091) == "https://example.com/callback"

    def test_multiple_placeholders(self):
        """Multiple placeholders should all be replaced."""
        url = "https://{{port}}.example.com/proxy/{{port}}/"
        assert _replace_port_placeholder(url, 9000) == "https://9000.example.com/proxy/9000/"

    def test_port_as_int(self):
        """Port should be converted to string."""
        url = "https://example.com/{{port}}/"
        result = _replace_port_placeholder(url, 8091)
        assert "8091" in result
        assert "{{port}}" not in result


# ---------------------------------------------------------------------------
# _ensure_save_token_endpoint
# ---------------------------------------------------------------------------


class TestEnsureSaveTokenEndpoint:
    """Test save_token endpoint appending."""

    def test_appends_save_token(self):
        """Should append /save_token to URLs without it."""
        url = "https://example.com/proxy/8091"
        assert _ensure_save_token_endpoint(url) == "https://example.com/proxy/8091/save_token"

    def test_strips_trailing_slash_then_appends(self):
        """Should strip trailing slash before appending."""
        url = "https://example.com/proxy/8091/"
        assert _ensure_save_token_endpoint(url) == "https://example.com/proxy/8091/save_token"

    def test_already_has_save_token(self):
        """Should not double-append if already present."""
        url = "https://example.com/save_token"
        assert _ensure_save_token_endpoint(url) == "https://example.com/save_token"

    def test_save_token_with_trailing_slash(self):
        """Should handle /save_token/ edge case."""
        url = "https://example.com/save_token/"
        # After rstrip("/"), becomes /save_token, which ends with /save_token
        result = _ensure_save_token_endpoint(url)
        assert result.endswith("/save_token")


# ---------------------------------------------------------------------------
# get_devcontainer_callback_url - No remote environment
# ---------------------------------------------------------------------------


class TestGetDevcontainerCallbackUrlNoRemote:
    """Test that None is returned when not in a remote environment."""

    @pytest.fixture(autouse=True)
    def clear_env_vars(self):
        """Clear all remote environment variables before each test."""
        env_vars = [
            "VSCODE_PROXY_URI",
            "AUTH_CALLBACK_URL",
        ]
        with patch.dict(os.environ, {}, clear=True):
            # Restore only non-remote env vars
            for var in env_vars:
                os.environ.pop(var, None)
            yield

    def test_returns_none_when_no_remote_env(self):
        """Should return None when not in any remote environment."""
        # Ensure all remote env vars are cleared
        for var in ["VSCODE_PROXY_URI", "AUTH_CALLBACK_URL"]:
            os.environ.pop(var, None)
        result = get_devcontainer_callback_url(8091)
        assert result is None


# ---------------------------------------------------------------------------
# get_devcontainer_callback_url - VS Code devcontainers
# ---------------------------------------------------------------------------


class TestGetDevcontainerCallbackUrlVSCode:
    """Test VS Code devcontainer detection via VSCODE_PROXY_URI."""

    def test_vscode_proxy_uri_with_port_placeholder(self):
        """Should build callback URL from VSCODE_PROXY_URI."""
        with patch.dict(
            os.environ,
            {"VSCODE_PROXY_URI": "https://agent-sandbox.stage.walmart.com/proxy/ws/test-app/proxy/{{port}}/"},
        ):
            result = get_devcontainer_callback_url(8091)
            assert result == "https://agent-sandbox.stage.walmart.com/proxy/ws/test-app/proxy/8091/save_token"

    def test_vscode_proxy_uri_without_trailing_slash(self):
        """Should handle VSCODE_PROXY_URI without trailing slash."""
        with patch.dict(
            os.environ,
            {"VSCODE_PROXY_URI": "https://example.com/proxy/{{port}}"},
        ):
            result = get_devcontainer_callback_url(9000)
            assert result == "https://example.com/proxy/9000/save_token"

    def test_vscode_proxy_uri_real_world_example(self):
        """Test with a real-world agent-sandbox URL."""
        with patch.dict(
            os.environ,
            {"VSCODE_PROXY_URI": "https://agent-sandbox.stage.walmart.com/proxy/ws/test-app-22135501/proxy/{{port}}/"},
        ):
            result = get_devcontainer_callback_url(8091)
            expected = "https://agent-sandbox.stage.walmart.com/proxy/ws/test-app-22135501/proxy/8091/save_token"
            assert result == expected


# ---------------------------------------------------------------------------
# get_devcontainer_callback_url - AUTH_CALLBACK_URL override
# ---------------------------------------------------------------------------


class TestGetDevcontainerCallbackUrlOverride:
    """Test AUTH_CALLBACK_URL manual override."""

    def test_auth_callback_url_takes_precedence(self):
        """AUTH_CALLBACK_URL should override VSCODE_PROXY_URI."""
        with patch.dict(
            os.environ,
            {
                "VSCODE_PROXY_URI": "https://should-be-ignored.com/{{port}}/",
                "AUTH_CALLBACK_URL": "https://custom-override.com/proxy/{{port}}/callback",
            },
        ):
            result = get_devcontainer_callback_url(9000)
            assert "custom-override.com" in result
            assert "should-be-ignored" not in result

    def test_auth_callback_url_without_port_placeholder(self):
        """AUTH_CALLBACK_URL without port placeholder should work."""
        with patch.dict(
            os.environ,
            {"AUTH_CALLBACK_URL": "https://fixed-callback.com/auth"},
        ):
            result = get_devcontainer_callback_url(8091)
            # Port isn't in the URL but save_token should be appended
            assert result == "https://fixed-callback.com/auth/save_token"


# ---------------------------------------------------------------------------
# is_remote_environment
# ---------------------------------------------------------------------------


class TestIsRemoteEnvironment:
    """Test remote environment detection."""

    def test_not_remote_when_no_env_vars(self):
        """Should return False when no remote env vars are set."""
        with patch.dict(os.environ, {}, clear=True):
            assert is_remote_environment() is False

    def test_remote_with_vscode_proxy_uri(self):
        """Should return True when VSCODE_PROXY_URI is set."""
        with patch.dict(os.environ, {"VSCODE_PROXY_URI": "https://example.com"}):
            assert is_remote_environment() is True

    def test_remote_with_auth_callback_url(self):
        """Should return True when AUTH_CALLBACK_URL is set."""
        with patch.dict(os.environ, {"AUTH_CALLBACK_URL": "https://example.com"}):
            assert is_remote_environment() is True

    def test_remote_with_remote_containers(self):
        """Should return True when REMOTE_CONTAINERS is set."""
        with patch.dict(os.environ, {"REMOTE_CONTAINERS": "true"}):
            assert is_remote_environment() is True
