"""
HTTP utilities module for code-puppy.

This module provides functions for creating properly configured HTTP clients.
"""

import os
import socket
from typing import TYPE_CHECKING, Dict, Optional, Union

import httpx

if TYPE_CHECKING:
    import requests
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
    ssl_cert_file = os.environ.get("_SSL_CERT_FILE")
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

    http2_enabled = get_http2()
    # Simple client without retry logic
    return httpx.Client(
        verify=verify, headers=headers or {}, timeout=timeout, http2=http2_enabled
    )


def create_async_client(
    timeout: int = 180,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
    retry_status_codes: tuple = (429, 502, 503, 504),
    debug_responses: bool = False,
) -> httpx.AsyncClient:
    if verify is None:
        verify = get_cert_bundle_path()

    # Simple client without retry logic
    http2_enabled = get_http2()

    # Debug hooks for troubleshooting
    event_hooks = {}
    if debug_responses:
        import logging

        logger = logging.getLogger("code_puppy.http_debug")

        async def log_request(request: httpx.Request):
            try:
                emit_info(f"[dim]HTTP Request: {request.method} {request.url}[/dim]")
                logger.warning(f"HTTP Request: {request.method} {request.url}")
            except Exception:
                pass

        async def log_response(response: httpx.Response):
            try:
                content_type = response.headers.get("content-type", "")
                logger.warning(
                    f"HTTP Response: {response.status_code} {response.url} ({content_type})"
                )
                emit_info(
                    f"[dim]HTTP Response: {response.status_code} ({content_type})[/dim]"
                )
            except Exception:
                pass

        event_hooks["request"] = [log_request]
        event_hooks["response"] = [log_response]

    return httpx.AsyncClient(
        verify=verify,
        headers=headers or {},
        timeout=timeout,
        http2=http2_enabled,
        event_hooks=event_hooks if event_hooks else None,
    )


def create_requests_session(
    timeout: float = 10.0,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> "requests.Session":
    import requests

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
    model_name: str = "",
) -> Union[ReopenableAsyncClient, httpx.AsyncClient]:
    if verify is None:
        verify = get_cert_bundle_path()

    http2_enabled = get_http2()
    # Simple client without retry logic
    if ReopenableAsyncClient is not None:
        return ReopenableAsyncClient(
            verify=verify, headers=headers or {}, timeout=timeout, http2=http2_enabled
        )
    else:
        # Fallback to regular AsyncClient if ReopenableAsyncClient is not available
        return httpx.AsyncClient(
            verify=verify, headers=headers or {}, timeout=timeout, http2=http2_enabled
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
