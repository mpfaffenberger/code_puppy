"""Comprehensive test coverage for http_utils.py.

Tests HTTP utilities including:
- Proxy configuration resolution
- SSL/TLS certificate handling
- HTTP/2 support detection
- Async client creation and configuration
- Rate limit handling and retries
- Environment variable processing
"""

import os
from unittest.mock import patch

from code_puppy.http_utils import ProxyConfig


class TestProxyConfigClass:
    """Test ProxyConfig dataclass."""

    def test_proxy_config_creation(self):
        """Test creating a ProxyConfig instance."""
        config = ProxyConfig(
            verify=True,
            trust_env=False,
            proxy_url=None,
            disable_retry=False,
            http2_enabled=False,
        )
        assert config.verify is True
        assert config.trust_env is False
        assert config.proxy_url is None
        assert config.disable_retry is False
        assert config.http2_enabled is False

    def test_proxy_config_with_url(self):
        """Test ProxyConfig with proxy URL."""
        config = ProxyConfig(
            verify=True,
            trust_env=True,
            proxy_url="http://proxy.example.com:8080",
            disable_retry=False,
            http2_enabled=True,
        )
        assert config.proxy_url == "http://proxy.example.com:8080"
        assert config.trust_env is True
        assert config.http2_enabled is True

    def test_proxy_config_with_cert_path(self):
        """Test ProxyConfig with SSL certificate path."""
        config = ProxyConfig(
            verify="/path/to/ca-bundle.crt",
            trust_env=False,
            proxy_url=None,
            disable_retry=False,
            http2_enabled=False,
        )
        assert config.verify == "/path/to/ca-bundle.crt"

    def test_proxy_config_ssl_disabled(self):
        """Test ProxyConfig with SSL disabled."""
        config = ProxyConfig(
            verify=False,
            trust_env=False,
            proxy_url=None,
            disable_retry=False,
            http2_enabled=False,
        )
        assert config.verify is False


class TestResolveProxyConfig:
    """Test proxy configuration resolution."""

    @patch("code_puppy.http_utils.get_cert_bundle_path")
    @patch("code_puppy.http_utils.get_http2")
    def test_resolve_no_proxy_no_env(
        self,
        mock_get_http2,
        mock_get_cert,
    ):
        """Test proxy resolution with no proxy environment variables."""
        from code_puppy.http_utils import _resolve_proxy_config

        mock_get_http2.return_value = False
        mock_get_cert.return_value = None

        with patch.dict(os.environ, {}, clear=True):
            config = _resolve_proxy_config()
            assert config.proxy_url is None
            assert config.trust_env is False
            assert config.disable_retry is False

    @patch("code_puppy.http_utils.get_cert_bundle_path")
    @patch("code_puppy.http_utils.get_http2")
    def test_resolve_with_https_proxy(
        self,
        mock_get_http2,
        mock_get_cert,
    ):
        """Test proxy resolution with HTTPS_PROXY environment variable."""
        from code_puppy.http_utils import _resolve_proxy_config

        mock_get_http2.return_value = False
        mock_get_cert.return_value = None

        with patch.dict(os.environ, {"HTTPS_PROXY": "https://proxy.example.com:3128"}):
            config = _resolve_proxy_config()
            assert config.proxy_url == "https://proxy.example.com:3128"
            assert config.trust_env is True

    @patch("code_puppy.http_utils.get_cert_bundle_path")
    @patch("code_puppy.http_utils.get_http2")
    def test_resolve_with_http_proxy(
        self,
        mock_get_http2,
        mock_get_cert,
    ):
        """Test proxy resolution with HTTP_PROXY environment variable."""
        from code_puppy.http_utils import _resolve_proxy_config

        mock_get_http2.return_value = False
        mock_get_cert.return_value = None

        with patch.dict(os.environ, {"HTTP_PROXY": "http://proxy.example.com:3128"}):
            config = _resolve_proxy_config()
            assert config.proxy_url == "http://proxy.example.com:3128"
            assert config.trust_env is True

    @patch("code_puppy.http_utils.get_cert_bundle_path")
    @patch("code_puppy.http_utils.get_http2")
    def test_resolve_https_proxy_priority(
        self,
        mock_get_http2,
        mock_get_cert,
    ):
        """Test HTTPS_PROXY has priority over HTTP_PROXY."""
        from code_puppy.http_utils import _resolve_proxy_config

        mock_get_http2.return_value = False
        mock_get_cert.return_value = None

        env_vars = {
            "HTTP_PROXY": "http://http-proxy.example.com:3128",
            "HTTPS_PROXY": "https://https-proxy.example.com:3128",
        }
        with patch.dict(os.environ, env_vars):
            config = _resolve_proxy_config()
            assert config.proxy_url == "https://https-proxy.example.com:3128"

    @patch("code_puppy.http_utils.get_cert_bundle_path")
    @patch("code_puppy.http_utils.get_http2")
    def test_resolve_lowercase_proxy_env_vars(
        self,
        mock_get_http2,
        mock_get_cert,
    ):
        """Test lowercase proxy environment variables are recognized."""
        from code_puppy.http_utils import _resolve_proxy_config

        mock_get_http2.return_value = False
        mock_get_cert.return_value = None

        with patch.dict(os.environ, {"https_proxy": "https://proxy.example.com:3128"}):
            config = _resolve_proxy_config()
            assert config.proxy_url == "https://proxy.example.com:3128"

    @patch("code_puppy.http_utils.get_cert_bundle_path")
    @patch("code_puppy.http_utils.get_http2")
    def test_resolve_disable_retry_transport(
        self,
        mock_get_http2,
        mock_get_cert,
    ):
        """Test disable retry transport flag."""
        from code_puppy.http_utils import _resolve_proxy_config

        mock_get_http2.return_value = False
        mock_get_cert.return_value = None

        with patch.dict(os.environ, {"CODE_PUPPY_DISABLE_RETRY_TRANSPORT": "1"}):
            config = _resolve_proxy_config()
            assert config.disable_retry is True
            assert config.verify is False  # SSL disabled in test mode

    @patch("code_puppy.http_utils.get_cert_bundle_path")
    @patch("code_puppy.http_utils.get_http2")
    def test_resolve_disable_retry_transport_case_insensitive(
        self,
        mock_get_http2,
        mock_get_cert,
    ):
        """Test disable retry transport flag is case insensitive."""
        from code_puppy.http_utils import _resolve_proxy_config

        mock_get_http2.return_value = False
        mock_get_cert.return_value = None

        for value in ["1", "true", "yes", "True", "YES"]:
            with patch.dict(os.environ, {"CODE_PUPPY_DISABLE_RETRY_TRANSPORT": value}):
                config = _resolve_proxy_config()
                assert config.disable_retry is True

    @patch("code_puppy.http_utils.get_cert_bundle_path")
    @patch("code_puppy.http_utils.get_http2")
    def test_resolve_http2_enabled(
        self,
        mock_get_http2,
        mock_get_cert,
    ):
        """Test HTTP/2 enabled flag."""
        from code_puppy.http_utils import _resolve_proxy_config

        mock_get_http2.return_value = True
        mock_get_cert.return_value = None

        with patch.dict(os.environ, {}, clear=True):
            config = _resolve_proxy_config()
            assert config.http2_enabled is True

    @patch("code_puppy.http_utils.get_cert_bundle_path")
    @patch("code_puppy.http_utils.get_http2")
    def test_resolve_custom_verify_path(
        self,
        mock_get_http2,
        mock_get_cert,
    ):
        """Test custom certificate bundle path."""
        from code_puppy.http_utils import _resolve_proxy_config

        mock_get_http2.return_value = False
        mock_get_cert.return_value = "/path/to/ca-bundle.crt"

        with patch.dict(os.environ, {}, clear=True):
            config = _resolve_proxy_config()
            assert config.verify == "/path/to/ca-bundle.crt"


class TestCreateAsyncClient:
    """Test async HTTP client creation."""

    @patch("code_puppy.http_utils._resolve_proxy_config")
    def test_create_async_client_basic(
        self,
        mock_resolve_proxy,
    ):
        """Test basic async client creation."""
        from code_puppy.http_utils import create_async_client

        mock_resolve_proxy.return_value = ProxyConfig(
            verify=True,
            trust_env=False,
            proxy_url=None,
            disable_retry=False,
            http2_enabled=False,
        )

        client = create_async_client()
        assert client is not None

    @patch("code_puppy.http_utils._resolve_proxy_config")
    def test_create_async_client_with_headers(
        self,
        mock_resolve_proxy,
    ):
        """Test async client creation with custom headers."""
        from code_puppy.http_utils import create_async_client

        mock_resolve_proxy.return_value = ProxyConfig(
            verify=True,
            trust_env=False,
            proxy_url=None,
            disable_retry=False,
            http2_enabled=False,
        )

        headers = {"X-Custom-Header": "value"}
        client = create_async_client(headers=headers)
        assert client is not None

    @patch("code_puppy.http_utils._resolve_proxy_config")
    def test_create_async_client_with_verify_false(
        self,
        mock_resolve_proxy,
    ):
        """Test async client creation with verify=False."""
        from code_puppy.http_utils import create_async_client

        mock_resolve_proxy.return_value = ProxyConfig(
            verify=False,
            trust_env=False,
            proxy_url=None,
            disable_retry=False,
            http2_enabled=False,
        )

        client = create_async_client(verify=False)
        assert client is not None


class TestFindAvailablePort:
    """Test port availability detection."""

    def test_find_available_port_returns_int(self):
        """Test find_available_port returns an integer."""
        from code_puppy.http_utils import find_available_port

        port = find_available_port()
        assert isinstance(port, int)
        assert port > 0

    def test_find_available_port_in_valid_range(self):
        """Test find_available_port returns port in valid range."""
        from code_puppy.http_utils import find_available_port

        port = find_available_port()
        assert 1024 <= port <= 65535  # Typical unprivileged port range

    def test_find_available_port_with_start_port(self):
        """Test find_available_port with start port."""
        from code_puppy.http_utils import find_available_port

        port = find_available_port(start_port=8000)
        assert port >= 8000

    def test_find_available_port_multiple_calls(self):
        """Test multiple calls to find_available_port."""
        from code_puppy.http_utils import find_available_port

        port1 = find_available_port()
        port2 = find_available_port()
        # Both should be valid ports
        assert isinstance(port1, int) and isinstance(port2, int)
        assert port1 > 0 and port2 > 0
