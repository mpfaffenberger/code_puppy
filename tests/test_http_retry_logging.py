"""Tests for HTTP retry exception formatting and logging."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import httpx2
import pytest

from code_puppy.claude_cache_client import ClaudeCacheAsyncClient
from code_puppy.http_retry import describe_exception
from code_puppy.http_utils import RetryingAsyncClient


class TestDescribeException:
    """Unit tests for describe_exception formatting and fallbacks."""

    def test_normal_exception_message(self):
        exc = ValueError("something failed")
        assert describe_exception(exc) == "something failed"

    def test_empty_exception_message_falls_back_to_repr(self):
        exc = httpx.ConnectError("")
        assert describe_exception(exc) == repr(exc)

    def test_whitespace_exception_message_falls_back_to_repr(self):
        exc = httpx.ConnectError("   ")
        assert describe_exception(exc) == repr(exc)

    def test_empty_exception_with_cause(self):
        exc = httpx.ConnectError("")
        exc.__cause__ = ConnectionResetError("Connection reset by peer")
        assert describe_exception(exc) == "ConnectError: Connection reset by peer"

    def test_empty_exception_with_context(self):
        exc = httpx.ConnectError("")
        exc.__context__ = OSError("Network is unreachable")
        assert describe_exception(exc) == "ConnectError: Network is unreachable"

    def test_empty_exception_with_empty_cause_falls_back_to_repr(self):
        exc = httpx.ConnectError("")
        exc.__cause__ = ConnectionResetError("")
        assert describe_exception(exc) == repr(exc)

    def test_empty_exception_with_none_cause(self):
        exc = httpx.ConnectError("")
        exc.__cause__ = None
        exc.__context__ = None
        assert describe_exception(exc) == repr(exc)


class TestRetryingSendMixinLogging:
    """Tests for RetryingSendMixin retry warning message emission."""

    @pytest.mark.anyio
    async def test_empty_connection_error_emits_repr(self):
        client = RetryingAsyncClient(max_retries=1)
        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200

        exc = httpx.ConnectError("")

        with (
            patch.object(
                httpx.AsyncClient,
                "send",
                new_callable=AsyncMock,
                side_effect=[exc, resp_200],
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("code_puppy.http_retry.emit_warning") as mock_emit_warning,
        ):
            result = await client.send(MagicMock(spec=httpx.Request))
            assert result.status_code == 200

            mock_emit_warning.assert_called_once()
            warning_msg = mock_emit_warning.call_args[0][0]
            assert (
                "HTTP connection error: ConnectError(''). Retrying in 1.0s..."
                == warning_msg
            )
            assert "HTTP connection error: . " not in warning_msg

    @pytest.mark.anyio
    async def test_connection_error_with_cause_emits_chained_details(self):
        client = RetryingAsyncClient(max_retries=1)
        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200

        exc = httpx.ConnectError("")
        exc.__cause__ = ConnectionResetError("Connection reset by peer")

        with (
            patch.object(
                httpx.AsyncClient,
                "send",
                new_callable=AsyncMock,
                side_effect=[exc, resp_200],
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("code_puppy.http_retry.emit_warning") as mock_emit_warning,
        ):
            result = await client.send(MagicMock(spec=httpx.Request))
            assert result.status_code == 200

            mock_emit_warning.assert_called_once()
            warning_msg = mock_emit_warning.call_args[0][0]
            assert (
                "HTTP connection error: ConnectError: Connection reset by peer. Retrying in 1.0s..."
                == warning_msg
            )


class TestClaudeCacheClientLogging:
    """Tests for ClaudeCacheAsyncClient retry warning logging."""

    @pytest.mark.asyncio
    async def test_empty_connection_error_logs_descriptive_warning(self, caplog):
        client = ClaudeCacheAsyncClient()
        req = httpx2.Request("GET", "https://api.anthropic.com/v1/messages")
        resp_200 = httpx2.Response(200, request=req)

        exc = httpx2.ConnectError("")
        exc.__cause__ = ConnectionResetError("peer closed connection")

        with (
            patch.object(
                httpx2.AsyncClient,
                "send",
                new_callable=AsyncMock,
                side_effect=[exc, resp_200],
            ),
            patch(
                "code_puppy.claude_cache_client.asyncio.sleep", new_callable=AsyncMock
            ),
        ):
            with caplog.at_level("WARNING", logger="code_puppy.claude_cache_client"):
                result = await client._send_with_retries(req)
                assert result.status_code == 200

        assert any(
            "HTTP connection error: ConnectError: peer closed connection. Retrying"
            in record.message
            for record in caplog.records
        )
