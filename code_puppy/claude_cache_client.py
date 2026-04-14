"""Cache helpers for Claude Code / Anthropic.

ClaudeCacheAsyncClient: httpx client that tries to patch /v1/messages bodies.

We now also expose `patch_anthropic_client_messages` which monkey-patches
AsyncAnthropic.messages.create() so we can inject cache_control BEFORE
serialization, avoiding httpx/Pydantic internals.
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
                if body_bytes:
                    updated = self._inject_cache_control(body_bytes)
                    if updated is not None:
                        # Rebuild a request with the updated body and transplant internals
                        try:
                            rebuilt = self.build_request(
                                method=request.method,
                                url=request.url,
                                headers=request.headers,
                                content=updated,
                            )

                            # Copy core internals so httpx uses the modified body/stream
                            if hasattr(rebuilt, "_content"):
                                setattr(request, "_content", rebuilt._content)  # type: ignore[attr-defined]
                            if hasattr(rebuilt, "stream"):
                                request.stream = rebuilt.stream
                            if hasattr(rebuilt, "extensions"):
                                request.extensions = rebuilt.extensions

                            # Ensure Content-Length matches the new body
                            request.headers["Content-Length"] = str(len(updated))

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

        # Anthropic supports up to 4 cache breakpoints.  We place them on
        # the three most impactful, stable prefixes so that content which
        # doesn't change between turns is independently cached:
        #   1. System prompt  – static across the whole session
        #   2. Tool definitions – static across the whole session
        #   3. Last message    – caches the growing conversation prefix

        # 1. System prompt
        system = data.get("system")
        if isinstance(system, list) and system:
            last_sys = system[-1]
            if isinstance(last_sys, dict) and "cache_control" not in last_sys:
                last_sys["cache_control"] = {"type": "ephemeral"}
                modified = True
        elif isinstance(system, str) and system:
            # Convert bare string to content-block list so we can attach
            # cache_control (the Anthropic API accepts both formats).
            data["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
            modified = True

        # 2. Tool definitions
        tools = data.get("tools")
        if isinstance(tools, list) and tools:
            last_tool = tools[-1]
            if isinstance(last_tool, dict) and "cache_control" not in last_tool:
                last_tool["cache_control"] = {"type": "ephemeral"}
                modified = True

        # 3. Last message content block
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
    """In-place cache_control injection on Anthropic messages.create payload.

    Places up to three cache breakpoints (Anthropic allows 4) on the most
    valuable, stable prefixes:
      1. System prompt  – never changes between turns
      2. Tool defs      – never changes between turns
      3. Last message   – caches the growing conversation prefix
    """

    # 1. System prompt
    system = payload.get("system")
    if isinstance(system, list) and system:
        last_sys = system[-1]
        if isinstance(last_sys, dict) and "cache_control" not in last_sys:
            last_sys["cache_control"] = {"type": "ephemeral"}
    elif isinstance(system, str) and system:
        payload["system"] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]

    # 2. Tool definitions
    tools = payload.get("tools")
    if isinstance(tools, list) and tools:
        last_tool = tools[-1]
        if isinstance(last_tool, dict) and "cache_control" not in last_tool:
            last_tool["cache_control"] = {"type": "ephemeral"}

    # 3. Last message content block
    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            content = last.get("content")
            if isinstance(content, list) and content:
                last_block = content[-1]
                if isinstance(last_block, dict) and "cache_control" not in last_block:
                    last_block["cache_control"] = {"type": "ephemeral"}


def _make_cache_wrapper(original_create: Callable[..., Any]) -> Callable[..., Any]:
    """Create a wrapped version of messages.create that injects cache_control."""

    async def wrapped_create(*args: Any, **kwargs: Any):
        if kwargs:
            _inject_cache_control_in_payload(kwargs)
        elif args:
            maybe_payload = args[-1]
            if isinstance(maybe_payload, dict):
                _inject_cache_control_in_payload(maybe_payload)

        return await original_create(*args, **kwargs)

    return wrapped_create


def patch_anthropic_client_messages(client: Any) -> None:
    """Monkey-patch AsyncAnthropic messages.create to inject cache_control.

    Patches both client.messages.create AND client.beta.messages.create
    since pydantic-ai uses the beta endpoint.
    """

    if AsyncAnthropic is None or not isinstance(client, AsyncAnthropic):  # type: ignore[arg-type]
        return

    # Patch client.messages.create
    try:
        messages_obj = getattr(client, "messages", None)
        if messages_obj is not None:
            messages_obj.create = _make_cache_wrapper(messages_obj.create)  # type: ignore[assignment]
    except Exception:  # pragma: no cover - defensive
        pass

    # Patch client.beta.messages.create (used by pydantic-ai)
    try:
        beta_obj = getattr(client, "beta", None)
        if beta_obj is not None:
            beta_messages_obj = getattr(beta_obj, "messages", None)
            if beta_messages_obj is not None:
                beta_messages_obj.create = _make_cache_wrapper(beta_messages_obj.create)  # type: ignore[assignment]
    except Exception:  # pragma: no cover - defensive
        pass
