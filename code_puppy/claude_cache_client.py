"""Cache helpers for Claude Code / Anthropic.

ClaudeCacheAsyncClient: httpx client that tries to patch /v1/messages bodies.

We now also expose `patch_anthropic_client_messages` which monkey-patches
AsyncAnthropic.messages.create() so we can inject cache_control BEFORE
serialization, avoiding httpx/Pydantic internals.

This module also handles:
- Tool name prefixing/unprefixing for Claude Code OAuth compatibility
- Header transformations (anthropic-beta, user-agent)
- URL modifications (adding ?beta=true query param)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

try:
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover - optional dep
    AsyncAnthropic = None  # type: ignore


class ClaudeCacheAsyncClient(httpx.AsyncClient):
    async def send(
        self, request: httpx.Request, *args: Any, **kwargs: Any
    ) -> httpx.Response:  # type: ignore[override]
        try:
            if request.url.path.endswith("/v1/messages"):
                body_bytes = self._extract_body_bytes(request)
                headers = dict(request.headers)
                url = request.url
                body_modified = False
                headers_modified = False

                # 1. Transform headers for Claude Code OAuth
                self._transform_headers_for_claude_code(headers)
                headers_modified = True

                # 2. Add ?beta=true query param
                url = self._add_beta_query_param(url)

                # 3. Prefix tool names in request body
                if body_bytes:
                    prefixed_body = self._prefix_tool_names(body_bytes)
                    if prefixed_body is not None:
                        body_bytes = prefixed_body
                        body_modified = True

                    # 4. Inject cache_control
                    cached_body = self._inject_cache_control(body_bytes)
                    if cached_body is not None:
                        body_bytes = cached_body
                        body_modified = True

                # Rebuild request if anything changed
                if body_modified or headers_modified or url != request.url:
                    try:
                        rebuilt = self.build_request(
                            method=request.method,
                            url=url,
                            headers=headers,
                            content=body_bytes,
                        )

                        except Exception:
                            # Swallow instrumentation errors; do not break real calls.
                            pass
        except Exception:
            # Swallow wrapper errors; do not break real calls.
            pass
        return await super().send(request, *args, **kwargs)

    @staticmethod
    def _extract_body_bytes(request: httpx.Request) -> bytes | None:
        # Try public content first
        try:
            content = request.content
            if content:
                return content
        except Exception:
            pass

        # Fallback to private attr if necessary
        try:
            content = getattr(request, "_content", None)
            if content:
                return content
        except Exception:
            pass

        return None

    @staticmethod
    def _inject_cache_control(body: bytes) -> bytes | None:
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        modified = False

        # Remove unsupported parameters that pydantic-ai might add
        # but Walmart's Anthropic proxy doesn't support
        unsupported_params = ["output_format"]
        for param in unsupported_params:
            if param in data:
                del data[param]
                modified = True

        # Minimal, deterministic strategy:
        # Add cache_control only on the single most recent block:
        # the last dict content block of the last message (if any).
        messages = data.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                content = last.get("content")
                if isinstance(content, list) and content:
                    last_block = content[-1]
                    if (
                        isinstance(last_block, dict)
                        and "cache_control" not in last_block
                    ):
                        last_block["cache_control"] = {"type": "ephemeral"}
                        modified = True

        if not modified:
            return None

        return json.dumps(data).encode("utf-8")


def _inject_cache_control_in_payload(payload: dict[str, Any]) -> None:
    """In-place cache_control injection and cleanup on Anthropic messages.create payload.

    Also removes unsupported parameters that pydantic-ai might add but
    Walmart's Anthropic proxy doesn't support (e.g., output_format).
    """
    # Remove unsupported parameters that pydantic-ai might add
    unsupported_params = ["output_format"]
    for param in unsupported_params:
        payload.pop(param, None)

    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            content = last.get("content")
            if isinstance(content, list) and content:
                last_block = content[-1]
                if isinstance(last_block, dict) and "cache_control" not in last_block:
                    last_block["cache_control"] = {"type": "ephemeral"}

    return


def patch_anthropic_client_messages(client: Any) -> None:
    """Monkey-patch AsyncAnthropic.messages.create to inject cache_control.

    This operates at the highest level: just before Anthropic SDK serializes
    the request into HTTP. That means no httpx / Pydantic shenanigans can
    undo it.
    """

    if AsyncAnthropic is None or not isinstance(client, AsyncAnthropic):  # type: ignore[arg-type]
        return

    try:
        messages_obj = getattr(client, "messages", None)
        if messages_obj is None:
            return
        original_create: Callable[..., Any] = messages_obj.create
    except Exception:  # pragma: no cover - defensive
        return

    async def wrapped_create(*args: Any, **kwargs: Any):
        # Anthropic messages.create takes a mix of positional/kw args.
        # The payload is usually in kwargs for the Python SDK.
        if kwargs:
            _inject_cache_control_in_payload(kwargs)
        elif args:
            maybe_payload = args[-1]
            if isinstance(maybe_payload, dict):
                _inject_cache_control_in_payload(maybe_payload)

        return await original_create(*args, **kwargs)

    messages_obj.create = wrapped_create  # type: ignore[assignment]
