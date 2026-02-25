"""Full coverage tests for http_utils.py."""

import os
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestResolveProxyConfig:
    def test_no_proxy_no_retry_disable(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
        ):
            from code_puppy.http_utils import _resolve_proxy_config

            config = _resolve_proxy_config()
            assert config.trust_env is False
            assert config.proxy_url is None
            assert config.disable_retry is False

    def test_with_https_proxy(self):
        env = {"HTTPS_PROXY": "http://proxy:8080"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
        ):
            from code_puppy.http_utils import _resolve_proxy_config

            config = _resolve_proxy_config()
            assert config.trust_env is True
            assert config.proxy_url == "http://proxy:8080"

    def test_with_http_proxy_only(self):
        env = {"HTTP_PROXY": "http://proxy:3128"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
        ):
            from code_puppy.http_utils import _resolve_proxy_config

            config = _resolve_proxy_config()
            assert config.proxy_url == "http://proxy:3128"

    def test_with_lowercase_proxy(self):
        env = {"https_proxy": "http://lower:8080"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
        ):
            from code_puppy.http_utils import _resolve_proxy_config

            config = _resolve_proxy_config()
            assert config.proxy_url == "http://lower:8080"

    def test_disable_retry_transport(self):
        env = {"CODE_PUPPY_DISABLE_RETRY_TRANSPORT": "true"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
        ):
            from code_puppy.http_utils import _resolve_proxy_config

            config = _resolve_proxy_config()
            assert config.disable_retry is True
            assert config.verify is False
            assert config.trust_env is True

    def test_explicit_verify_passed(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("code_puppy.http_utils.get_http2", return_value=True),
        ):
            from code_puppy.http_utils import _resolve_proxy_config

            config = _resolve_proxy_config(verify="/path/to/cert")
            assert config.verify == "/path/to/cert"
            assert config.http2_enabled is True


class TestRetryingAsyncClient:
    @pytest.mark.anyio
    async def test_successful_request(self):
        from code_puppy.http_utils import RetryingAsyncClient

        client = RetryingAsyncClient()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await client.send(MagicMock(spec=httpx.Request))
            assert result.status_code == 200

    @pytest.mark.anyio
    async def test_retry_on_429(self):
        from code_puppy.http_utils import RetryingAsyncClient

        client = RetryingAsyncClient(max_retries=1)

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {}
        resp_429.aclose = AsyncMock()

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200

        with (
            patch.object(
                httpx.AsyncClient,
                "send",
                new_callable=AsyncMock,
                side_effect=[resp_429, resp_200],
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.send(MagicMock(spec=httpx.Request))
            assert result.status_code == 200

    @pytest.mark.anyio
    async def test_retry_with_retry_after_header(self):
        from code_puppy.http_utils import RetryingAsyncClient

        client = RetryingAsyncClient(max_retries=1)

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "2"}
        resp_429.aclose = AsyncMock()

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200

        with (
            patch.object(
                httpx.AsyncClient,
                "send",
                new_callable=AsyncMock,
                side_effect=[resp_429, resp_200],
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.send(MagicMock(spec=httpx.Request))
            assert result.status_code == 200

    @pytest.mark.anyio
    async def test_retry_with_http_date_retry_after(self):
        from code_puppy.http_utils import RetryingAsyncClient

        client = RetryingAsyncClient(max_retries=1)

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "Thu, 01 Jan 2099 00:00:00 GMT"}
        resp_429.aclose = AsyncMock()

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200

        with (
            patch.object(
                httpx.AsyncClient,
                "send",
                new_callable=AsyncMock,
                side_effect=[resp_429, resp_200],
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.send(MagicMock(spec=httpx.Request))
            assert result.status_code == 200

    @pytest.mark.anyio
    async def test_retry_with_invalid_retry_after(self):
        from code_puppy.http_utils import RetryingAsyncClient

        client = RetryingAsyncClient(max_retries=1)

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "not-a-number-or-date"}
        resp_429.aclose = AsyncMock()

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200

        with (
            patch.object(
                httpx.AsyncClient,
                "send",
                new_callable=AsyncMock,
                side_effect=[resp_429, resp_200],
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.send(MagicMock(spec=httpx.Request))
            assert result.status_code == 200

    @pytest.mark.anyio
    async def test_cerebras_ignores_retry_headers(self):
        from code_puppy.http_utils import RetryingAsyncClient

        client = RetryingAsyncClient(max_retries=1, model_name="cerebras-fast")
        assert client._ignore_retry_headers is True

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "60"}
        resp_429.aclose = AsyncMock()

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200

        with (
            patch.object(
                httpx.AsyncClient,
                "send",
                new_callable=AsyncMock,
                side_effect=[resp_429, resp_200],
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result = await client.send(MagicMock(spec=httpx.Request))
            assert result.status_code == 200
            # Cerebras uses 3s base, not 60s from header
            mock_sleep.assert_called_once()
            assert mock_sleep.call_args[0][0] == 3.0

    @pytest.mark.anyio
    async def test_exhausted_retries_returns_last_response(self):
        from code_puppy.http_utils import RetryingAsyncClient

        client = RetryingAsyncClient(max_retries=1)

        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {}
        resp_429.aclose = AsyncMock()

        with (
            patch.object(
                httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp_429
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.send(MagicMock(spec=httpx.Request))
            assert result.status_code == 429

    @pytest.mark.anyio
    async def test_connection_error_retries(self):
        from code_puppy.http_utils import RetryingAsyncClient

        client = RetryingAsyncClient(max_retries=1)

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200

        with (
            patch.object(
                httpx.AsyncClient,
                "send",
                new_callable=AsyncMock,
                side_effect=[httpx.ConnectError("fail"), resp_200],
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await client.send(MagicMock(spec=httpx.Request))
            assert result.status_code == 200

    @pytest.mark.anyio
    async def test_connection_error_exhausted(self):
        from code_puppy.http_utils import RetryingAsyncClient

        client = RetryingAsyncClient(max_retries=0)

        with (
            patch.object(
                httpx.AsyncClient,
                "send",
                new_callable=AsyncMock,
                side_effect=httpx.ConnectError("fail"),
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(httpx.ConnectError):
                await client.send(MagicMock(spec=httpx.Request))

    @pytest.mark.anyio
    async def test_non_retryable_exception_raises(self):
        from code_puppy.http_utils import RetryingAsyncClient

        client = RetryingAsyncClient(max_retries=3)

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=ValueError("bad"),
        ):
            with pytest.raises(ValueError):
                await client.send(MagicMock(spec=httpx.Request))


class TestGetCertBundlePath:
    def test_returns_none_when_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            from code_puppy.http_utils import get_cert_bundle_path

            assert get_cert_bundle_path() is None

    def test_returns_path_when_env_exists(self, tmp_path):
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("cert")
        with patch.dict(os.environ, {"SSL_CERT_FILE": str(cert_file)}):
            from code_puppy.http_utils import get_cert_bundle_path

            assert get_cert_bundle_path() == str(cert_file)

    def test_returns_none_when_env_path_missing(self):
        with patch.dict(os.environ, {"SSL_CERT_FILE": "/nonexistent/cert.pem"}):
            from code_puppy.http_utils import get_cert_bundle_path

            assert get_cert_bundle_path() is None


class TestCreateClient:
    def test_create_client_default(self):
        with (
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
        ):
            from code_puppy.http_utils import create_client

            client = create_client()
            assert isinstance(client, httpx.Client)
            client.close()

    def test_create_client_with_headers(self):
        with (
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
        ):
            from code_puppy.http_utils import create_client

            client = create_client(headers={"X-Custom": "val"})
            assert isinstance(client, httpx.Client)
            client.close()


class TestCreateAsyncClient:
    def test_creates_retrying_by_default(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
        ):
            from code_puppy.http_utils import RetryingAsyncClient, create_async_client

            client = create_async_client()
            assert isinstance(client, RetryingAsyncClient)

    def test_creates_plain_when_retry_disabled(self):
        env = {"CODE_PUPPY_DISABLE_RETRY_TRANSPORT": "1"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
        ):
            from code_puppy.http_utils import RetryingAsyncClient, create_async_client

            client = create_async_client()
            assert not isinstance(client, RetryingAsyncClient)


class TestCreateRequestsSession:
    def test_create_session_default(self):
        with patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None):
            from code_puppy.http_utils import create_requests_session

            session = create_requests_session()
            assert session.verify is None

    def test_create_session_with_headers(self):
        with patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None):
            from code_puppy.http_utils import create_requests_session

            session = create_requests_session(headers={"X-Key": "val"})
            assert session.headers.get("X-Key") == "val"

    def test_create_session_with_verify(self):
        from code_puppy.http_utils import create_requests_session

        session = create_requests_session(verify="/path/to/cert")
        assert session.verify == "/path/to/cert"


class TestAuthHeaders:
    def test_create_auth_headers(self):
        from code_puppy.http_utils import create_auth_headers

        headers = create_auth_headers("my-key")
        assert headers == {"Authorization": "Bearer my-key"}

    def test_create_auth_headers_custom_name(self):
        from code_puppy.http_utils import create_auth_headers

        headers = create_auth_headers("key", "X-Api-Key")
        assert headers == {"X-Api-Key": "Bearer key"}


class TestResolveEnvVarInHeader:
    def test_resolves_env_vars(self):
        with patch.dict(os.environ, {"MY_KEY": "secret"}):
            from code_puppy.http_utils import resolve_env_var_in_header

            result = resolve_env_var_in_header({"Authorization": "Bearer $MY_KEY"})
            assert result["Authorization"] == "Bearer secret"

    def test_passthrough_non_string(self):
        from code_puppy.http_utils import resolve_env_var_in_header

        result = resolve_env_var_in_header({"key": 123})
        assert result["key"] == 123


class TestCreateReopenableAsyncClient:
    def test_with_reopenable_available(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
            patch("code_puppy.http_utils.ReopenableAsyncClient") as mock_reopen,
        ):
            mock_reopen.return_value = MagicMock()
            from code_puppy.http_utils import create_reopenable_async_client

            create_reopenable_async_client()
            mock_reopen.assert_called_once()

    def test_with_reopenable_none_falls_back(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
            patch("code_puppy.http_utils.ReopenableAsyncClient", None),
        ):
            from code_puppy.http_utils import (
                RetryingAsyncClient,
                create_reopenable_async_client,
            )

            client = create_reopenable_async_client()
            assert isinstance(client, RetryingAsyncClient)

    def test_with_reopenable_none_retry_disabled(self):
        env = {"CODE_PUPPY_DISABLE_RETRY_TRANSPORT": "1"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
            patch("code_puppy.http_utils.ReopenableAsyncClient", None),
        ):
            from code_puppy.http_utils import (
                RetryingAsyncClient,
                create_reopenable_async_client,
            )

            client = create_reopenable_async_client()
            assert isinstance(client, httpx.AsyncClient)
            assert not isinstance(client, RetryingAsyncClient)

    def test_with_reopenable_retry_disabled(self):
        env = {"CODE_PUPPY_DISABLE_RETRY_TRANSPORT": "1"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None),
            patch("code_puppy.http_utils.get_http2", return_value=False),
            patch("code_puppy.http_utils.ReopenableAsyncClient") as mock_reopen,
        ):
            mock_reopen.return_value = MagicMock()
            from code_puppy.http_utils import create_reopenable_async_client

            create_reopenable_async_client()
            # Should not pass retry_status_codes/model_name
            call_kwargs = mock_reopen.call_args[1]
            assert "retry_status_codes" not in call_kwargs


class TestIsCertBundleAvailable:
    def test_returns_false_no_cert(self):
        with patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None):
            from code_puppy.http_utils import is_cert_bundle_available

            assert is_cert_bundle_available() is False

    def test_returns_true_with_valid_cert(self, tmp_path):
        cert = tmp_path / "cert.pem"
        cert.write_text("cert")
        with patch(
            "code_puppy.http_utils.get_cert_bundle_path", return_value=str(cert)
        ):
            from code_puppy.http_utils import is_cert_bundle_available

            assert is_cert_bundle_available() is True

    def test_returns_false_with_directory(self, tmp_path):
        with patch(
            "code_puppy.http_utils.get_cert_bundle_path", return_value=str(tmp_path)
        ):
            from code_puppy.http_utils import is_cert_bundle_available

            assert is_cert_bundle_available() is False


class TestFindAvailablePort:
    def test_finds_port(self):
        from code_puppy.http_utils import find_available_port

        port = find_available_port(start_port=49000, end_port=49010)
        assert port is not None
        assert 49000 <= port <= 49010

    def test_returns_none_when_all_busy(self):
        from code_puppy.http_utils import find_available_port

        # Use a very narrow range and bind to all ports
        socks = []
        try:
            for p in range(49900, 49903):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", p))
                socks.append(s)
            result = find_available_port(start_port=49900, end_port=49902)
            assert result is None
        finally:
            for s in socks:
                s.close()
