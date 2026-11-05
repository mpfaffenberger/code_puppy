"""
HTTP utilities module for code-puppy.

This module provides functions for creating properly configured HTTP clients.
"""

import os
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Optional, Union

import httpx

if TYPE_CHECKING:
    import requests
from code_puppy.ca_bundle import write_public_and_corporate_bundle
from code_puppy.config import DATA_DIR, get_http2
from code_puppy.i18n import t

from .http_retry import RetryingSendMixin


@dataclass
class ProxyConfig:
    """Configuration for proxy and SSL settings."""

    verify: Union[bool, str, None]
    trust_env: bool
    disable_retry: bool
    http2_enabled: bool


#: The insecure-TLS warning fires once per process: the client factory runs on
#: every model construction, and a warning per request would drown the UI.
_INSECURE_SKIP_VERIFY_WARNED = False


def _warn_insecure_skip_verify() -> None:
    """Tell the user, loudly and once, that TLS verification is off."""
    global _INSECURE_SKIP_VERIFY_WARNED
    if _INSECURE_SKIP_VERIFY_WARNED:
        return
    _INSECURE_SKIP_VERIFY_WARNED = True
    emit_warning(t("http_utils.insecure_skip_verify"))


#: The missing-CA-bundle warning fires once per process, like the insecure
#: one: the bundle is read per client build, and a warning per build would
#: repeat the same line on every model switch.
_MISSING_CERT_BUNDLE_WARNED: set[str] = set()


def _warn_missing_cert_bundle(name: str, path: str) -> None:
    """Warn when a CA-bundle environment variable points at a missing file."""
    if name in _MISSING_CERT_BUNDLE_WARNED:
        return
    _MISSING_CERT_BUNDLE_WARNED.add(name)
    emit_warning(t("http_utils.cert_bundle_missing", name=name, path=path))


def resolve_proxy_config(verify: Union[bool, str, None] = None) -> ProxyConfig:
    """Resolve client TLS, retry, and environment-proxy settings.

    Proxy selection is left to httpx so scheme-specific proxies and ``NO_PROXY``
    are honored per destination. This centralizes TLS and retry settings shared by
    the legacy ``httpx`` and ``httpx2`` client factories so proxy handling
    cannot drift between the two.

    Certificate verification is **never** disabled implicitly. Turning it off
    requires the explicit ``CODE_PUPPY_INSECURE_SKIP_VERIFY=1`` opt-in, which
    also emits a loud warning: unverified TLS means every API key and every
    prompt travels over a connection anyone on the path can rewrite.
    ``CODE_PUPPY_DISABLE_RETRY_TRANSPORT`` only swaps the retrying transport
    for the plain one -- it says nothing about TLS and must not change it.
    """
    if verify is None:
        verify = get_cert_bundle_path()

    http2_enabled = get_http2()

    disable_retry = os.environ.get(
        "CODE_PUPPY_DISABLE_RETRY_TRANSPORT", ""
    ).lower() in ("1", "true", "yes")

    insecure_skip_verify = os.environ.get(
        "CODE_PUPPY_INSECURE_SKIP_VERIFY", ""
    ).lower() in ("1", "true", "yes")

    has_proxy = bool(
        os.environ.get("HTTP_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("https_proxy")
    )

    # Determine trust_env and verify based on proxy/retry settings
    if insecure_skip_verify:
        # Explicit opt-in only: certificate checking off for every request.
        verify = False
        trust_env = True
        _warn_insecure_skip_verify()
    elif disable_retry:
        # Plain transport, but TLS verification stays exactly as configured.
        trust_env = True
    elif has_proxy:
        # Production proxy: keep SSL verification enabled
        trust_env = True
    else:
        trust_env = False

    return ProxyConfig(
        verify=verify,
        trust_env=trust_env,
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
    # Fallback if messaging system is not available
    def emit_info(content: str, **metadata):
        pass  # No-op if messaging system is not available

    def emit_warning(content: str, **metadata):
        pass


class RetryingAsyncClient(RetryingSendMixin, httpx.AsyncClient):
    """AsyncClient with built-in rate limit handling (429) and retries.

    Retry behaviour lives in :class:`~code_puppy.http_retry.RetryingSendMixin` so the
    ``httpx2`` client in :mod:`code_puppy.httpx2_utils` shares the exact same backoff
    rules; only the exception hierarchy differs per HTTP family.
    """

    retryable_exceptions = (httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout)


def get_cert_bundle_path() -> str | None:
    """Return public + configured corporate trust as an exportable CA file.

    ``SSL_CERT_FILE`` may contain only a corporate interception root. Passing
    that file through unchanged makes public HTTPS fail in clients and child
    processes that treat it as their complete file-based trust source. Combine
    it with certifi roots in an immutable per-user file before propagation.
    Sources are checked in SSL_CERT_FILE, REQUESTS_CA_BUNDLE, CURL_CA_BUNDLE
    order. Set CODE_PUPPY_COMBINE_CA_BUNDLE=false to retain restricted file trust.
    """
    ssl_cert_file = next(
        (
            value
            for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
            if (value := os.environ.get(name)) and os.path.isfile(value)
        ),
        None,
    )
    if not ssl_cert_file:
        # A configured-but-missing bundle is a misconfiguration: it used to be
        # ignored silently, so the user had no idea their trust store was not
        # the one they asked for.
        for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
            value = os.environ.get(name)
            if value and not os.path.isfile(value):
                _warn_missing_cert_bundle(name, value)
        return None
    # Preserve deliberately restricted/pinned file trust when requested.
    if os.environ.get("CODE_PUPPY_COMBINE_CA_BUNDLE", "true").lower() in (
        "0",
        "false",
        "no",
    ):
        return ssl_cert_file

    destination = os.path.join(
        DATA_DIR,
        "certs",
        "public-and-corporate-ca-bundle.pem",
    )
    try:
        return write_public_and_corporate_bundle(ssl_cert_file, destination)
    except OSError as exc:
        emit_warning(
            f"Could not combine public roots with {ssl_cert_file}; "
            f"using the configured CA file unchanged: {exc}"
        )
        return ssl_cert_file


# Back-compat alias; the name was private before the httpx2 factory started sharing it.
_resolve_proxy_config = resolve_proxy_config


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

    # NOTE: TenacityTransport removed — return a plain client for now.
    # TODO: RetryingClient(httpx.Client) if retries are ever needed again.
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
    model_name: str = "",
) -> httpx.AsyncClient:
    config = resolve_proxy_config(verify)

    if not config.disable_retry:
        return RetryingAsyncClient(
            retry_status_codes=retry_status_codes,
            model_name=model_name,
            verify=config.verify,
            headers=headers or {},
            timeout=timeout,
            http2=config.http2_enabled,
            trust_env=config.trust_env,
        )
    else:
        return httpx.AsyncClient(
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
    config = resolve_proxy_config(verify)

    base_kwargs = {
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
    else:
        # Fallback to RetryingAsyncClient or plain AsyncClient
        if not config.disable_retry:
            return RetryingAsyncClient(
                retry_status_codes=retry_status_codes,
                model_name=model_name,
                **base_kwargs,
            )
        else:
            return httpx.AsyncClient(**base_kwargs)


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
