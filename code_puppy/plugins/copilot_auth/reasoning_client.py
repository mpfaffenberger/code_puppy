"""Reasoning-opaque round-trip interceptor for Copilot Claude models.

The Copilot API returns two fields on Claude assistant messages:

- ``reasoning_text``: the model's chain-of-thought (human-readable)
- ``reasoning_opaque``: encrypted round-trip blob (**must** be echoed back)

pydantic-ai's ``openai_chat_send_back_thinking_parts="field"`` mode preserves
``reasoning_text`` across tool calls, but it doesn't know about
``reasoning_opaque``.  The Copilot API returns **400 Bad Request** if
``reasoning_text`` is sent without the accompanying ``reasoning_opaque``.

This module monkey-patches the httpx client to transparently:

1. Capture ``reasoning_opaque`` (keyed by ``reasoning_text``) from responses
2. Inject the matching ``reasoning_opaque`` into outgoing request messages

The approach mirrors the ``ChatGPTCodexAsyncClient`` pattern already in the codebase.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict

import httpx
from httpx import AsyncByteStream

logger = logging.getLogger(__name__)

# Cap the cache so it can't grow forever across long sessions.
_MAX_CACHE_ENTRIES = 256


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_key(text: str) -> str:
    """Short SHA-256 prefix — enough to avoid collisions in practice."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Stream wrapper — captures opaque data as SSE events flow through
# ---------------------------------------------------------------------------


class _OpaqueCapturingStream(AsyncByteStream):
    """Async byte-stream wrapper that taps ``reasoning_opaque`` from SSE.

    Yields every byte unchanged so downstream consumers (the OpenAI SDK)
    see the exact same data.  Internally it buffers bytes, splits SSE
    lines, parses JSON, and pairs ``reasoning_text`` chunks with
    ``reasoning_opaque`` chunks for storage in *opaque_cache*.

    Inherits from ``httpx.AsyncByteStream`` so that
    ``httpx.Response.aclose()`` recognises us as an async stream and
    doesn't blow up with *"Attempted to call an async close on an sync
    stream"*.  Ask me how I know.
    """

    def __init__(
        self,
        inner_stream: Any,
        opaque_cache: Dict[str, str],
        thinking_field: str,
    ):
        self._inner = inner_stream
        self._opaque_cache = opaque_cache
        self._thinking_field = thinking_field
        self._buffer = ""
        self._text_parts: list[str] = []
        self._opaque_parts: list[str] = []

    # -- async-iterator protocol ------------------------------------------

    def __aiter__(self):
        return self._iter_impl()

    async def _iter_impl(self):
        try:
            async for chunk in self._inner:
                self._feed(chunk)
                yield chunk
        finally:
            self._flush()

    async def aclose(self):
        self._flush()
        if hasattr(self._inner, "aclose"):
            await self._inner.aclose()

    # Fallback for any attributes we don't explicitly handle.
    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    # -- SSE parsing -------------------------------------------------------

    def _feed(self, chunk: bytes) -> None:
        self._buffer += chunk.decode("utf-8", errors="replace")
        self._process_buffer()

    def _process_buffer(self) -> None:
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                self._flush()
                continue
            try:
                event = json.loads(data_str)
                self._extract_from_event(event)
            except (json.JSONDecodeError, TypeError):
                pass

    def _extract_from_event(self, event: dict) -> None:
        for choice in event.get("choices", []):
            # Streaming deltas
            delta = choice.get("delta") or {}
            self._collect(delta)
            # Non-streaming message (fallback)
            message = choice.get("message") or {}
            self._collect(message)
            # Flush when the model signals it's done with this turn
            if choice.get("finish_reason"):
                self._flush()

    def _collect(self, obj: dict) -> None:
        text_chunk = obj.get(self._thinking_field)
        if text_chunk:
            self._text_parts.append(text_chunk)
        opaque_chunk = obj.get("reasoning_opaque")
        if opaque_chunk:
            self._opaque_parts.append(opaque_chunk)

    def _flush(self) -> None:
        if self._opaque_parts and self._text_parts:
            text = "".join(self._text_parts)
            opaque = "".join(self._opaque_parts)
            key = _text_key(text)
            self._opaque_cache[key] = opaque
            logger.debug(
                "Captured reasoning_opaque (%d chars) for key %.8s…",
                len(opaque),
                key,
            )
            # Evict oldest entry if we exceed the cap.
            while len(self._opaque_cache) > _MAX_CACHE_ENTRIES:
                first_key = next(iter(self._opaque_cache))
                del self._opaque_cache[first_key]
        self._text_parts = []
        self._opaque_parts = []


# ---------------------------------------------------------------------------
# Non-streaming capture (safety net)
# ---------------------------------------------------------------------------


def _capture_from_content(
    content: bytes,
    opaque_cache: Dict[str, str],
    thinking_field: str,
) -> None:
    """Extract ``reasoning_opaque`` from an already-read response body."""
    try:
        data = json.loads(content)
        for choice in data.get("choices", []):
            msg = choice.get("message") or {}
            text = msg.get(thinking_field)
            opaque = msg.get("reasoning_opaque")
            if text and opaque:
                opaque_cache[_text_key(text)] = opaque
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass


# ---------------------------------------------------------------------------
# Request-side injection
# ---------------------------------------------------------------------------


def _rebuild_request_body(
    request: httpx.Request,
    body: dict,
    client: httpx.AsyncClient,
) -> None:
    """Replace the request body in-place (mirrors ChatGPTCodexAsyncClient)."""
    new_body = json.dumps(body).encode("utf-8")
    rebuilt = client.build_request(
        method=request.method,
        url=request.url,
        headers=request.headers,
        content=new_body,
    )
    if hasattr(rebuilt, "_content"):
        request._content = rebuilt._content  # type: ignore[attr-defined]
    if hasattr(rebuilt, "stream"):
        request.stream = rebuilt.stream
    if hasattr(rebuilt, "extensions"):
        request.extensions = rebuilt.extensions
    request.headers["Content-Length"] = str(len(new_body))


def _inject_opaque_into_request(
    request: httpx.Request,
    opaque_cache: Dict[str, str],
    client: httpx.AsyncClient,
    thinking_field: str,
) -> None:
    """Add stored ``reasoning_opaque`` to assistant messages that need it.

    **Prevention layer**: if we can't find a matching opaque for a
    ``reasoning_text``, we strip that field entirely rather than sending
    it bare (which would trigger a 400).
    """
    try:
        body_bytes = request.content
        if not body_bytes:
            return

        body = json.loads(body_bytes)
        if not isinstance(body, dict):
            return

        messages = body.get("messages")
        if not messages:
            return

        modified = False
        injected = 0
        stripped = 0

        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "assistant":
                continue
            if thinking_field not in msg:
                continue
            if "reasoning_opaque" in msg:
                # Already has opaque — don't touch.
                continue

            key = _text_key(msg[thinking_field])
            opaque = opaque_cache.get(key)
            if opaque:
                msg["reasoning_opaque"] = opaque
                modified = True
                injected += 1
            else:
                # SAFETY: No matching opaque → strip reasoning_text to
                # prevent the 400.  Losing thinking context is better
                # than crashing the conversation.
                del msg[thinking_field]
                modified = True
                stripped += 1
                logger.debug(
                    "Stripped orphaned %s (no opaque in cache)",
                    thinking_field,
                )

        if not modified:
            return

        _rebuild_request_body(request, body, client)

        if injected:
            logger.debug(
                "Injected reasoning_opaque into %d assistant message(s)",
                injected,
            )
        if stripped:
            logger.debug(
                "Stripped %d orphaned %s field(s) (cache miss)",
                stripped,
                thinking_field,
            )
    except Exception as exc:
        # Never crash the real request.
        logger.debug("Failed to inject reasoning_opaque: %s", exc)


def _strip_all_reasoning_fields(
    request: httpx.Request,
    client: httpx.AsyncClient,
    thinking_field: str,
) -> bool:
    """Remove ALL reasoning fields from the request body.

    **Recovery layer**: called after a 400 to retry without any reasoning
    context.  Degrades gracefully to the old ``send_back_thinking_parts=False``
    behaviour — thinking disappears after tool calls, but the conversation
    keeps working.

    Returns True if the body was modified.
    """
    try:
        body_bytes = request.content
        if not body_bytes:
            return False

        body = json.loads(body_bytes)
        if not isinstance(body, dict):
            return False

        messages = body.get("messages")
        if not messages:
            return False

        modified = False
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "assistant":
                continue
            for field in (thinking_field, "reasoning_opaque"):
                if field in msg:
                    del msg[field]
                    modified = True

        if modified:
            _rebuild_request_body(request, body, client)

        return modified
    except Exception as exc:
        logger.debug("Failed to strip reasoning fields: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public API — single entry-point
# ---------------------------------------------------------------------------


def patch_client_for_reasoning_opaque(
    client: httpx.AsyncClient,
    thinking_field: str = "reasoning_text",
) -> None:
    """Monkey-patch *client* to round-trip ``reasoning_opaque`` transparently.

    Call **after** creating the client but **before** handing it to
    ``OpenAIProvider``.  Works with plain ``httpx.AsyncClient`` and the
    ``RetryingAsyncClient`` subclass returned by ``create_async_client``.

    Args:
        client: The httpx async client to patch.
        thinking_field: JSON field name that carries the thinking content
            (default ``"reasoning_text"`` — the Copilot Claude convention).
    """
    opaque_cache: Dict[str, str] = {}
    original_send = client.send

    async def _patched_send(
        request: httpx.Request, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        # 1) Inject reasoning_opaque into outgoing POST bodies.
        #    Also strips orphaned reasoning_text with no cached opaque.
        if request.method == "POST":
            _inject_opaque_into_request(request, opaque_cache, client, thinking_field)

        # 2) Let the real send (incl. auth + retries) run.
        response = await original_send(request, *args, **kwargs)

        # 3) RECOVERY: If the API still returns 400, it's likely because
        #    our reasoning fields are wrong/stale.  Strip them all and
        #    retry once.  This degrades to "no thinking after tool calls"
        #    but keeps the conversation alive.
        if response.status_code == 400 and request.method == "POST":
            # Read the error body for diagnostics before retrying.
            try:
                err_body = response.content.decode("utf-8", errors="replace")
            except Exception:
                err_body = "<unreadable>"
            logger.warning(
                "Copilot 400 — attempting recovery by stripping reasoning "
                "fields and retrying.  Error: %.300s",
                err_body,
            )
            if _strip_all_reasoning_fields(request, client, thinking_field):
                response = await original_send(request, *args, **kwargs)
                if response.status_code == 200:
                    logger.info(
                        "Recovery succeeded — reasoning stripped, "
                        "conversation continues without thinking context."
                    )
                else:
                    logger.warning(
                        "Recovery retry also failed (%d) — returning retry response.",
                        response.status_code,
                    )

        # 4) Capture reasoning_opaque from successful responses.
        if response.status_code == 200:
            if response.is_stream_consumed:
                _capture_from_content(response.content, opaque_cache, thinking_field)
            elif hasattr(response, "stream") and response.stream is not None:
                response.stream = _OpaqueCapturingStream(
                    response.stream, opaque_cache, thinking_field
                )

        return response

    client.send = _patched_send  # type: ignore[method-assign]
