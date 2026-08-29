"""``httpx2`` HTTP clients for pydantic-ai providers.

pydantic-ai 2.x hands caller-owned HTTP clients to its providers and warns that legacy
``httpx.AsyncClient`` support "will be removed in v3" (``PydanticAIDeprecationWarning``,
raised from ``pydantic_ai/providers/_openai_compatible.py``). Any client we build and pass
as ``http_client=`` therefore needs to come from ``httpx2``.

Clients that never reach a pydantic-ai provider -- the MCP SDK, ``AsyncAnthropic``, and
Code Puppy's own ``GeminiModel`` -- keep using :mod:`code_puppy.http_utils`, because those
libraries are still typed against legacy ``httpx``.

Proxy/SSL/HTTP2 resolution is shared with the legacy factory via
:func:`~code_puppy.http_utils.resolve_proxy_config`, and retry/backoff is shared via
:class:`~code_puppy.http_retry.RetryingSendMixin`, so behaviour is identical across both
HTTP families.
"""

from __future__ import annotations

from typing import Dict, Optional, Union

import httpx2

from .http_retry import RetryingSendMixin
from .http_utils import resolve_proxy_config


class RetryingAsyncClient(RetryingSendMixin, httpx2.AsyncClient):
    """``httpx2`` AsyncClient with built-in rate limit (429) and retry handling.

    Same backoff rules as :class:`~code_puppy.http_utils.RetryingAsyncClient`; only the
    exception hierarchy differs, since ``httpx2`` exceptions do not subclass ``httpx``'s.
    """

    retryable_exceptions = (httpx2.ConnectError, httpx2.ReadTimeout, httpx2.PoolTimeout)


def create_async_client(
    timeout: int = 180,
    verify: Union[bool, str] = None,
    headers: Optional[Dict[str, str]] = None,
    retry_status_codes: tuple = (429, 502, 503, 504),
    model_name: str = "",
) -> httpx2.AsyncClient:
    """Build an ``httpx2`` AsyncClient for use as a pydantic-ai provider's ``http_client``.

    Drop-in replacement for :func:`code_puppy.http_utils.create_async_client`, returning an
    ``httpx2`` client so pydantic-ai's providers do not emit a deprecation warning.
    """
    config = resolve_proxy_config(verify)

    client_kwargs = {
        "proxy": config.proxy_url,
        "verify": config.verify,
        "headers": headers or {},
        "timeout": timeout,
        "http2": config.http2_enabled,
        "trust_env": config.trust_env,
    }

    if not config.disable_retry:
        return RetryingAsyncClient(
            retry_status_codes=retry_status_codes,
            model_name=model_name,
            **client_kwargs,
        )
    return httpx2.AsyncClient(**client_kwargs)
