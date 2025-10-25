"""Unit tests for code_puppy.http_utils - HTTP client creation utilities."""
import os
from unittest.mock import MagicMock, patch
import pytest
import httpx
import requests
from code_puppy.http_utils import (
    create_async_client, create_auth_headers, create_client,
    create_requests_session, find_available_port, get_cert_bundle_path,
    is_cert_bundle_available, resolve_env_var_in_header,
)

class TestGetCertBundlePath:
    def test_returns_ssl_cert_file_when_set(self, tmp_path):
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("fake cert")
        with patch.dict(os.environ, {"SSL_CERT_FILE": str(cert_file)}):
            result = get_cert_bundle_path()
        assert result == str(cert_file)

    def test_returns_none_when_ssl_cert_file_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            result = get_cert_bundle_path()
        assert result is None

class TestIsCertBundleAvailable:
    def test_returns_true_when_cert_exists(self, tmp_path):
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("fake cert")
        with patch("code_puppy.http_utils.get_cert_bundle_path", return_value=str(cert_file)):
            result = is_cert_bundle_available()
        assert result is True

    def test_returns_false_when_cert_path_is_none(self):
        with patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None):
            result = is_cert_bundle_available()
        assert result is False

class TestCreateAuthHeaders:
    def test_creates_bearer_token_header(self):
        headers = create_auth_headers("my-secret-token")
        assert headers == {"Authorization": "Bearer my-secret-token"}

    def test_custom_header_name(self):
        headers = create_auth_headers("token123", header_name="X-API-Key")
        assert headers == {"X-API-Key": "Bearer token123"}

class TestResolveEnvVarInHeader:
    def test_resolves_environment_variables(self):
        with patch.dict(os.environ, {"API_TOKEN": "secret123"}):
            headers = {"Authorization": "Bearer $API_TOKEN"}
            resolved = resolve_env_var_in_header(headers)
        assert resolved["Authorization"] == "Bearer secret123"

    def test_preserves_non_env_var_values(self):
        headers = {"Content-Type": "application/json"}
        resolved = resolve_env_var_in_header(headers)
        assert resolved == headers

class TestFindAvailablePort:
    def test_finds_available_port(self):
        port = find_available_port(start_port=8090, end_port=8100)
        assert port is not None
        assert 8090 <= port <= 8100
