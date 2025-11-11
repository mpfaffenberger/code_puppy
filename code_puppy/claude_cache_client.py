"""Cache helpers for Claude Code / Anthropic.

ClaudeCacheAsyncClient: httpx client that tries to patch /v1/messages bodies.

We now also expose `patch_anthropic_client_messages` which monkey-patches
AsyncAnthropic.messages.create() so we can inject cache_control BEFORE
serialization, avoiding httpx/Pydantic internals.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx

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
    """In-place cache_control injection on Anthropic messages.create payload."""

    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            content = last.get("content")
            if isinstance(content, list) and content:
                last_block = content[-1]
                if isinstance(last_block, dict) and "cache_control" not in last_block:
                    last_block["cache_control"] = {"type": "ephemeral"}

    # No extra markers in production mode; keep payload clean.
    # (Function kept for potential future use.)
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
