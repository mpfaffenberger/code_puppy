"""
HTTP utilities module for code-puppy.

This module provides functions for creating properly configured HTTP clients.
"""

import asyncio
import logging
import os
import socket
import time
from typing import Any, Dict, Optional, Union

import httpx
import requests

from code_puppy.config import get_http2

logger = logging.getLogger(__name__)

try:
    from .reopenable_async_client import ReopenableAsyncClient
except ImportError:
    ReopenableAsyncClient = None

try:
    from .messaging import emit_info, emit_warning
except ImportError:
    # Fallback if messaging system is not available
    def emit_info(content: str, **metadata):
        pass  # No-op if messaging system is not available

    def emit_warning(content: str, **metadata):
        pass


class RetryingAsyncClient(httpx.AsyncClient):
    """AsyncClient with built-in rate limit handling (429) and retries.

    This replaces the Tenacity transport with a more direct subclass implementation,
    which plays nicer with proxies and custom transports (like Antigravity).
    """

    def __init__(
        self,
        retry_status_codes: tuple = (429, 502, 503, 504),
        max_retries: int = 5,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.retry_status_codes = retry_status_codes
        self.max_retries = max_retries

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        """Send request with automatic retries for rate limits and server errors."""
        last_response = None
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                # Clone request for retry (streams might be consumed)
                # But only if it's not the first attempt
                req_to_send = request
                if attempt > 0:
                    # httpx requests are reusable, but we need to be careful with streams
                    pass

                response = await super().send(req_to_send, **kwargs)
                last_response = response

                # Check for retryable status
                if response.status_code not in self.retry_status_codes:
                    return response

                # Close response if we're going to retry
                await response.aclose()

                # Determine wait time
                wait_time = 1.0 * (
                    2**attempt
                )  # Default exponential backoff: 1s, 2s, 4s...

                # Check Retry-After header
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait_time = float(retry_after)
                    except ValueError:
                        # Try parsing http-date
                        from email.utils import parsedate_to_datetime

                        try:
                            date = parsedate_to_datetime(retry_after)
                            wait_time = date.timestamp() - time.time()
                        except Exception:
                            pass

                # Cap wait time
                wait_time = max(0.5, min(wait_time, 60.0))

                if attempt < self.max_retries:
                    emit_info(
                        f"HTTP retry: {response.status_code} received. Waiting {wait_time:.1f}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(wait_time)

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout) as e:
                last_exception = e
                wait_time = 1.0 * (2**attempt)
                if attempt < self.max_retries:
                    emit_warning(
                        f"HTTP connection error: {e}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise
            except Exception:
                raise

        # Return last response (even if it's an error status)
        if last_response:
            return last_response

        # Should catch this in loop, but just in case
        if last_exception:
            raise last_exception

        return last_response


def get_cert_bundle_path() -> str:
    # First check if SSL_CERT_FILE environment variable is set
    ssl_cert_file = os.environ.get("SSL_CERT_FILE")
    if ssl_cert_file and os.path.exists(ssl_cert_file):
        return ssl_cert_file


def create_client(
    timeout: int = 180,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
    retry_status_codes: tuple = (429, 502, 503, 504),
) -> httpx.Client:
    if verify is None:
        verify = get_cert_bundle_path()

    # Check if HTTP/2 is enabled in config
    http2_enabled = get_http2()

    # If retry components are available, create a client with retry transport
    # Note: TenacityTransport was removed. For now we just return a standard client.
    # Future TODO: Implement RetryingClient(httpx.Client) if needed.
    return httpx.Client(
        verify=verify,
        headers=headers or {},
        timeout=timeout,
        http2=http2_enabled,
    )


def create_async_client(
    timeout: int = 180,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
    retry_status_codes: tuple = (429, 502, 503, 504),
) -> httpx.AsyncClient:
    if verify is None:
        verify = get_cert_bundle_path()

    # Check if HTTP/2 is enabled in config
    http2_enabled = get_http2()

    # Check if custom retry transport should be disabled (e.g., for integration tests with proxies)
    disable_retry_transport = os.environ.get(
        "CODE_PUPPY_DISABLE_RETRY_TRANSPORT", ""
    ).lower() in ("1", "true", "yes")

    # Check if proxy environment variables are set
    has_proxy = bool(
        os.environ.get("HTTP_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("https_proxy")
    )

    # When retry transport is disabled (test mode), disable SSL verification
    # for proxy testing. For production proxies, SSL should still be verified!
    if disable_retry_transport:
        verify = False
        trust_env = True
    elif has_proxy:
        # Production proxy detected - keep SSL verification enabled for security
        trust_env = True
    else:
        trust_env = False

    # Extract proxy URL if needed
    proxy_url = None
    if has_proxy:
        proxy_url = (
            os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("http_proxy")
        )

    # Use RetryingAsyncClient if retries are enabled
    if not disable_retry_transport:
        return RetryingAsyncClient(
            retry_status_codes=retry_status_codes,
            proxy=proxy_url,
            verify=verify,
            headers=headers or {},
            timeout=timeout,
            http2=http2_enabled,
            trust_env=trust_env,
        )
    else:
        # Regular client for testing
        return httpx.AsyncClient(
            proxy=proxy_url,
            verify=verify,
            headers=headers or {},
            timeout=timeout,
            http2=http2_enabled,
            trust_env=trust_env,
        )


def create_requests_session(
    timeout: float = 5.0,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> requests.Session:
    session = requests.Session()

    if verify is None:
        verify = get_cert_bundle_path()

    session.verify = verify

    if headers:
        session.headers.update(headers or {})

    return session


def create_auth_headers(
    api_key: str, header_name: str = "Authorization"
) -> Dict[str, str]:
    return {header_name: f"Bearer {api_key}"}


def resolve_env_var_in_header(headers: Dict[str, str]) -> Dict[str, str]:
    resolved_headers = {}

    for key, value in headers.items():
        if isinstance(value, str):
            try:
                expanded = os.path.expandvars(value)
                resolved_headers[key] = expanded
            except Exception:
                resolved_headers[key] = value
        else:
            resolved_headers[key] = value

    return resolved_headers


def create_reopenable_async_client(
    timeout: int = 180,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
    retry_status_codes: tuple = (429, 502, 503, 504),
) -> Union[ReopenableAsyncClient, httpx.AsyncClient]:
    if verify is None:
        verify = get_cert_bundle_path()

    # Check if HTTP/2 is enabled in config
    http2_enabled = get_http2()

    # Check if custom retry transport should be disabled (e.g., for integration tests with proxies)
    disable_retry_transport = os.environ.get(
        "CODE_PUPPY_DISABLE_RETRY_TRANSPORT", ""
    ).lower() in ("1", "true", "yes")

    # Check if proxy environment variables are set
    has_proxy = bool(
        os.environ.get("HTTP_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("https_proxy")
    )

    # When retry transport is disabled (test mode), disable SSL verification
    if disable_retry_transport:
        verify = False
        trust_env = True
    elif has_proxy:
        trust_env = True
    else:
        trust_env = False

    # Extract proxy URL if needed
    proxy_url = None
    if has_proxy:
        proxy_url = (
            os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("http_proxy")
        )

    if ReopenableAsyncClient is not None:
        # Use RetryingAsyncClient if retries are enabled
        client_class = (
            RetryingAsyncClient if not disable_retry_transport else httpx.AsyncClient
        )

        # Pass retry config only if using RetryingAsyncClient
        kwargs = {
            "proxy": proxy_url,
            "verify": verify,
            "headers": headers or {},
            "timeout": timeout,
            "http2": http2_enabled,
            "trust_env": trust_env,
        }

        if not disable_retry_transport:
            kwargs["retry_status_codes"] = retry_status_codes

        return ReopenableAsyncClient(client_class=client_class, **kwargs)
    else:
        # Fallback to RetryingAsyncClient
        if not disable_retry_transport:
            return RetryingAsyncClient(
                retry_status_codes=retry_status_codes,
                proxy=proxy_url,
                verify=verify,
                headers=headers or {},
                timeout=timeout,
                http2=http2_enabled,
                trust_env=trust_env,
            )
        else:
            return httpx.AsyncClient(
                proxy=proxy_url,
                verify=verify,
                headers=headers or {},
                timeout=timeout,
                http2=http2_enabled,
                trust_env=trust_env,
            )


def is_cert_bundle_available() -> bool:
    cert_path = get_cert_bundle_path()
    if cert_path is None:
        return False
    return os.path.exists(cert_path) and os.path.isfile(cert_path)


def find_available_port(start_port=8090, end_port=9010, host="127.0.0.1"):
    for port in range(start_port, end_port + 1):
        try:
            # Try to bind to the port to check if it's available
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
                return port
        except OSError:
            # Port is in use, try the next one
            continue
    return None
