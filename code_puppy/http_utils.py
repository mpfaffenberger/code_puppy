"""
HTTP utilities module for code-puppy.

This module provides functions for creating properly configured HTTP clients.
"""

import asyncio
import os
import socket
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

import httpx

if TYPE_CHECKING:
    import requests
from code_puppy.config import get_http2


@dataclass
class ProxyConfig:
    """Configuration for proxy and SSL settings."""

    verify: Union[bool, str, None]
    trust_env: bool
    proxy_url: str | None
    disable_retry: bool
    http2_enabled: bool


def _pick_proxy_url() -> str | None:
    candidates = [
        os.environ.get("HTTPS_PROXY"),
        os.environ.get("https_proxy"),
        os.environ.get("HTTP_PROXY"),
        os.environ.get("http_proxy"),
    ]
    non_local = [
        value
        for value in candidates
        if value and "localhost" not in value.lower() and "127.0.0.1" not in value
    ]
    if non_local:
        return non_local[0]
    for value in candidates:
        if value:
            return value
    return None


def _resolve_proxy_config(verify: Union[bool, str, None] = None) -> ProxyConfig:
    if verify is None:
        verify = get_cert_bundle_path()

    http2_enabled = get_http2()

    disable_retry = os.environ.get(
        "CODE_PUPPY_DISABLE_RETRY_TRANSPORT", ""
    ).lower() in ("1", "true", "yes")

    proxy_url = _pick_proxy_url()
    has_proxy = bool(proxy_url)

    if disable_retry:
        verify = False
        trust_env = True
    elif has_proxy:
        trust_env = True
    else:
        trust_env = False

    return ProxyConfig(
        verify=verify,
        trust_env=trust_env,
        proxy_url=proxy_url,
        disable_retry=disable_retry,
        http2_enabled=http2_enabled,
    )


try:
    from .reopenable_async_client import ReopenableAsyncClient
except ImportError:
    ReopenableAsyncClient = None

try:
    from .messaging import emit_info, emit_warning
except ImportError:

    def emit_info(content: str, **metadata):
        pass

    def emit_warning(content: str, **metadata):
        pass


class RetryingAsyncClient(httpx.AsyncClient):
    def __init__(
        self,
        retry_status_codes: tuple = (429, 502, 503, 504),
        max_retries: int = 5,
        model_name: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.retry_status_codes = retry_status_codes
        self.max_retries = max_retries
        self.model_name = model_name.lower() if model_name else ""
        self._ignore_retry_headers = "cerebras" in self.model_name

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        last_response = None
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await super().send(request, **kwargs)
                last_response = response

                if response.status_code not in self.retry_status_codes:
                    return response

                await response.aclose()

                if self._ignore_retry_headers:
                    wait_time = 3.0 * (2**attempt)
                else:
                    wait_time = 1.0 * (2**attempt)
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                        except ValueError:
                            from email.utils import parsedate_to_datetime

                            try:
                                date = parsedate_to_datetime(retry_after)
                                wait_time = date.timestamp() - time.time()
                            except Exception:
                                pass

                wait_time = max(0.5, min(wait_time, 60.0))

                if attempt < self.max_retries:
                    provider_note = (
                        " (ignoring header)" if self._ignore_retry_headers else ""
                    )
                    emit_info(
                        f"HTTP retry: {response.status_code} received{provider_note}. Waiting {wait_time:.1f}s (attempt {attempt + 1}/{self.max_retries})"
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

        if last_response:
            return last_response
        if last_exception:
            raise last_exception
        return last_response


def get_cert_bundle_path() -> str | None:
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
    http2_enabled = get_http2()
    return httpx.Client(
        verify=verify, headers=headers or {}, timeout=timeout, http2=http2_enabled
    )


def create_async_client(
    timeout: int = 180,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
    retry_status_codes: tuple = (429, 502, 503, 504),
    model_name: str = "",
) -> httpx.AsyncClient:
    config = _resolve_proxy_config(verify)
    if not config.disable_retry:
        return RetryingAsyncClient(
            retry_status_codes=retry_status_codes,
            model_name=model_name,
            proxy=config.proxy_url,
            verify=config.verify,
            headers=headers or {},
            timeout=timeout,
            http2=config.http2_enabled,
            trust_env=config.trust_env,
        )
    return httpx.AsyncClient(
        proxy=config.proxy_url,
        verify=config.verify,
        headers=headers or {},
        timeout=timeout,
        http2=config.http2_enabled,
        trust_env=config.trust_env,
    )


def create_requests_session(
    timeout: float = 5.0,
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
                resolved_headers[key] = os.path.expandvars(value)
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
    config = _resolve_proxy_config(verify)
    base_kwargs = {
        "proxy": config.proxy_url,
        "verify": config.verify,
        "headers": headers or {},
        "timeout": timeout,
        "http2": config.http2_enabled,
        "trust_env": config.trust_env,
    }
    if ReopenableAsyncClient is not None:
        client_class = (
            RetryingAsyncClient if not config.disable_retry else httpx.AsyncClient
        )
        kwargs = {**base_kwargs, "client_class": client_class}
        if not config.disable_retry:
            kwargs["retry_status_codes"] = retry_status_codes
            kwargs["model_name"] = model_name
        return ReopenableAsyncClient(**kwargs)
    if not config.disable_retry:
        return RetryingAsyncClient(
            retry_status_codes=retry_status_codes,
            model_name=model_name,
            **base_kwargs,
        )
    return httpx.AsyncClient(**base_kwargs)


def is_cert_bundle_available() -> bool:
    cert_path = get_cert_bundle_path()
    if cert_path is None:
        return False
    return os.path.exists(cert_path) and os.path.isfile(cert_path)


def find_available_port(start_port=8090, end_port=9010, host="127.0.0.1"):
    for port in range(start_port, end_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
                return port
        except OSError:
            continue
    return None
