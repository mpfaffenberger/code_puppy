"""
HTTP utilities module for code-puppy.

This module provides functions for creating properly configured HTTP clients.
"""

import os
import socket
from typing import Dict, Optional, Union

import httpx
import requests
from tenacity import stop_after_attempt, wait_exponential

from code_puppy.config import get_http2

try:
    from pydantic_ai.retries import (
        AsyncTenacityTransport,
        RetryConfig,
        TenacityTransport,
        wait_retry_after,
    )
except ImportError:
    # Fallback if pydantic_ai.retries is not available
    AsyncTenacityTransport = None
    RetryConfig = None
    TenacityTransport = None
    wait_retry_after = None

try:
    from .reopenable_async_client import ReopenableAsyncClient
except ImportError:
    ReopenableAsyncClient = None

try:
    from .messaging import emit_info
except ImportError:
    # Fallback if messaging system is not available
    def emit_info(content: str, **metadata):
        pass  # No-op if messaging system is not available


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

    # Check if custom retry transport should be disabled (e.g., for integration tests with proxies)
    disable_retry_transport = os.environ.get(
        "CODE_PUPPY_DISABLE_RETRY_TRANSPORT", ""
    ).lower() in ("1", "true", "yes")

    # If retry components are available, create a client with retry transport
    if (
        TenacityTransport
        and RetryConfig
        and wait_retry_after
        and not disable_retry_transport
    ):

        def should_retry_status(response):
            """Raise exceptions for retryable HTTP status codes."""
            if response.status_code in retry_status_codes:
                emit_info(
                    f"HTTP retry: Retrying request due to status code {response.status_code}"
                )
                return True

        transport = TenacityTransport(
            config=RetryConfig(
                retry=lambda e: isinstance(e, httpx.HTTPStatusError)
                and e.response.status_code in retry_status_codes,
                wait=wait_retry_after(
                    fallback_strategy=wait_exponential(multiplier=1, max=60),
                    max_wait=300,
                ),
                stop=stop_after_attempt(10),
                reraise=True,
            ),
            validate_response=should_retry_status,
        )

        return httpx.Client(
            transport=transport,
            verify=verify,
            headers=headers or {},
            timeout=timeout,
            http2=http2_enabled,
        )
    else:
        # Fallback to regular client if retry components are not available
        return httpx.Client(
            verify=verify, headers=headers or {}, timeout=timeout, http2=http2_enabled
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

    # If retry components are available, create a client with retry transport
    # BUT: disable retry transport when proxies are detected because custom transports
    # don't play nicely with proxy configuration
    if (
        AsyncTenacityTransport
        and RetryConfig
        and wait_retry_after
        and not disable_retry_transport
        and not has_proxy
    ):

        def should_retry_status(response):
            """Raise exceptions for retryable HTTP status codes."""
            if response.status_code in retry_status_codes:
                emit_info(
                    f"HTTP retry: Retrying request due to status code {response.status_code}"
                )
                return True

        # Create transport (with or without proxy base)
        if has_proxy:
            # Extract proxy URL from environment
            proxy_url = (
                os.environ.get("HTTPS_PROXY")
                or os.environ.get("https_proxy")
                or os.environ.get("HTTP_PROXY")
                or os.environ.get("http_proxy")
            )
        else:
            proxy_url = None

        # Create retry transport wrapper
        transport = AsyncTenacityTransport(
            config=RetryConfig(
                retry=lambda e: isinstance(e, httpx.HTTPStatusError)
                and e.response.status_code in retry_status_codes,
                wait=wait_retry_after(10),
                stop=stop_after_attempt(10),
                reraise=True,
            ),
            validate_response=should_retry_status,
        )

        return httpx.AsyncClient(
            transport=transport,
            proxy=proxy_url,  # Pass proxy to client, not transport
            verify=verify,
            headers=headers or {},
            timeout=timeout,
            http2=http2_enabled,
            trust_env=trust_env,
        )
    else:
        # Fallback to regular client if retry components are not available,
        # when retry transport is explicitly disabled, or when proxies are detected
        # Extract proxy URL if needed
        if has_proxy:
            proxy_url = (
                os.environ.get("HTTPS_PROXY")
                or os.environ.get("https_proxy")
                or os.environ.get("HTTP_PROXY")
                or os.environ.get("http_proxy")
            )
        else:
            proxy_url = None

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

    # If retry components are available, create a client with retry transport
    # BUT: disable retry transport when proxies are detected because custom transports
    # don't play nicely with proxy configuration
    if (
        AsyncTenacityTransport
        and RetryConfig
        and wait_retry_after
        and not disable_retry_transport
        and not has_proxy
    ):

        def should_retry_status(response):
            """Raise exceptions for retryable HTTP status codes."""
            if response.status_code in retry_status_codes:
                emit_info(
                    f"HTTP retry: Retrying request due to status code {response.status_code}"
                )
                return True

        transport = AsyncTenacityTransport(
            config=RetryConfig(
                retry=lambda e: isinstance(e, httpx.HTTPStatusError)
                and e.response.status_code in retry_status_codes,
                wait=wait_retry_after(
                    fallback_strategy=wait_exponential(multiplier=1, max=60),
                    max_wait=300,
                ),
                stop=stop_after_attempt(10),
                reraise=True,
            ),
            validate_response=should_retry_status,
        )

        # Extract proxy URL if needed
        if has_proxy:
            proxy_url = (
                os.environ.get("HTTPS_PROXY")
                or os.environ.get("https_proxy")
                or os.environ.get("HTTP_PROXY")
                or os.environ.get("http_proxy")
            )
        else:
            proxy_url = None

        if ReopenableAsyncClient is not None:
            return ReopenableAsyncClient(
                transport=transport,
                proxy=proxy_url,
                verify=verify,
                headers=headers or {},
                timeout=timeout,
                http2=http2_enabled,
                trust_env=trust_env,
            )
        else:
            # Fallback to regular AsyncClient if ReopenableAsyncClient is not available
            return httpx.AsyncClient(
                transport=transport,
                proxy=proxy_url,
                verify=verify,
                headers=headers or {},
                timeout=timeout,
                http2=http2_enabled,
                trust_env=trust_env,
            )
    else:
        # Fallback to regular clients if retry components are not available
        # or when proxies are detected
        # Extract proxy URL if needed
        if has_proxy:
            proxy_url = (
                os.environ.get("HTTPS_PROXY")
                or os.environ.get("https_proxy")
                or os.environ.get("HTTP_PROXY")
                or os.environ.get("http_proxy")
            )
        else:
            proxy_url = None

        if ReopenableAsyncClient is not None:
            return ReopenableAsyncClient(
                proxy=proxy_url,
                verify=verify,
                headers=headers or {},
                timeout=timeout,
                http2=http2_enabled,
                trust_env=trust_env,
            )
        else:
            # Fallback to regular AsyncClient if ReopenableAsyncClient is not available
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
