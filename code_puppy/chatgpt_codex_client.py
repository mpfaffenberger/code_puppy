"""HTTP client interceptor for ChatGPT Codex API.

ChatGPTCodexAsyncClient: httpx client that injects required fields into
request bodies for the ChatGPT Codex API and handles stream-to-non-stream
conversion.

The Codex API requires:
- "store": false - Disables conversation storage
- "stream": true - Streaming is mandatory

Removes unsupported parameters:
- "max_output_tokens" - Not supported by Codex API
- "max_tokens" - Not supported by Codex API
- "verbosity" - Not supported by Codex API
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _is_reasoning_model(model_name: str) -> bool:
    """Check if a model supports reasoning parameters."""
    reasoning_models = [
        "gpt-5",  # All GPT-5 variants
        "o1",  # o1 series
        "o3",  # o3 series
        "o4",  # o4 series
    ]
    model_lower = model_name.lower()
    return any(model_lower.startswith(prefix) for prefix in reasoning_models)


class ChatGPTCodexAsyncClient(httpx.AsyncClient):
    """Async HTTP client that handles ChatGPT Codex API requirements.

    This client:
    1. Injects required fields (store=false, stream=true)
    2. Strips unsupported parameters
    3. Converts streaming responses to non-streaming format
    """

    async def send(
        self, request: httpx.Request, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        """Intercept requests and inject required Codex fields."""
        force_stream_conversion = False

        try:
            # Only modify POST requests to the Codex API
            if request.method == "POST":
                body_bytes = self._extract_body_bytes(request)
                if body_bytes:
                    updated, force_stream_conversion = self._inject_codex_fields(
                        body_bytes
                    )
                    if updated is not None:
                        try:
                            rebuilt = self.build_request(
                                method=request.method,
                                url=request.url,
                                headers=request.headers,
                                content=updated,
                            )

                            # Copy core internals so httpx uses the modified body/stream
                            if hasattr(rebuilt, "_content"):
                                setattr(request, "_content", rebuilt._content)
                            if hasattr(rebuilt, "stream"):
                                request.stream = rebuilt.stream
                            if hasattr(rebuilt, "extensions"):
                                request.extensions = rebuilt.extensions

                            # Ensure Content-Length matches the new body
                            request.headers["Content-Length"] = str(len(updated))

                        except Exception:
                            pass
        except Exception:
            pass

        # Make the actual request
        response = await super().send(request, *args, **kwargs)

        # If we forced streaming, convert the SSE stream to a regular response
        if force_stream_conversion and response.status_code == 200:
            try:
                response = await self._convert_stream_to_response(response)
            except Exception as e:
                logger.warning(f"Failed to convert stream response: {e}")

        return response

    @staticmethod
    def _extract_body_bytes(request: httpx.Request) -> bytes | None:
        """Extract the request body as bytes."""
        try:
            content = request.content
            if content:
                return content
        except Exception:
            pass

        try:
            content = getattr(request, "_content", None)
            if content:
                return content
        except Exception:
            pass

        return None

    @staticmethod
    def _inject_codex_fields(body: bytes) -> tuple[bytes | None, bool]:
        """Inject required Codex fields and remove unsupported ones.

        Returns:
            Tuple of (modified body bytes or None, whether stream was forced)
        """
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return None, False

        if not isinstance(data, dict):
            return None, False

        modified = False
        forced_stream = False

        # CRITICAL: ChatGPT Codex backend requires store=false
        if "store" not in data or data.get("store") is not False:
            data["store"] = False
            modified = True

        # CRITICAL: ChatGPT Codex backend requires stream=true
        # If stream is already true (e.g., pydantic-ai with event_stream_handler),
        # don't force conversion - let streaming events flow through naturally
        if data.get("stream") is not True:
            data["stream"] = True
            forced_stream = True  # Only convert if WE forced streaming
            modified = True

        # Add reasoning settings for reasoning models (gpt-5.2, o-series, etc.)
        model = data.get("model", "")
        if "reasoning" not in data and _is_reasoning_model(model):
            data["reasoning"] = {
                "effort": "medium",
                "summary": "auto",
            }
            modified = True

        # Remove unsupported parameters
        # Note: verbosity should be under "text" object, not top-level
        unsupported_params = ["max_output_tokens", "max_tokens", "verbosity"]
        for param in unsupported_params:
            if param in data:
                del data[param]
                modified = True

        if not modified:
            return None, False

        return json.dumps(data).encode("utf-8"), forced_stream

    async def _convert_stream_to_response(
        self, response: httpx.Response
    ) -> httpx.Response:
        """Convert an SSE streaming response to a complete response.

        Consumes the SSE stream and reconstructs the final response object.
        """
        logger.debug("Converting SSE stream to non-streaming response")
        final_response_data = None
        collected_text = []
        collected_tool_calls = []

        # Read the entire stream
        async for line in response.aiter_lines():
            if not line or not line.startswith("data:"):
                continue

            data_str = line[5:].strip()  # Remove "data:" prefix
            if data_str == "[DONE]":
                break

            try:
                event = json.loads(data_str)
                event_type = event.get("type", "")

                if event_type == "response.output_text.delta":
                    # Collect text deltas
                    delta = event.get("delta", "")
                    if delta:
                        collected_text.append(delta)

                elif event_type == "response.completed":
                    # This contains the final response object
                    final_response_data = event.get("response", {})

                elif event_type == "response.function_call_arguments.done":
                    # Collect tool calls
                    tool_call = {
                        "name": event.get("name", ""),
                        "arguments": event.get("arguments", ""),
                        "call_id": event.get("call_id", ""),
                    }
                    collected_tool_calls.append(tool_call)

            except json.JSONDecodeError:
                continue

        logger.debug(
            f"Collected {len(collected_text)} text chunks, {len(collected_tool_calls)} tool calls"
        )
        if final_response_data:
            logger.debug(
                f"Got final response data with keys: {list(final_response_data.keys())}"
            )

        # Build the final response body
        if final_response_data:
            response_body = final_response_data
        else:
            # Fallback: construct a minimal response from collected data
            response_body = {
                "id": "reconstructed",
                "object": "response",
                "output": [],
            }

            if collected_text:
                response_body["output"].append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "".join(collected_text)}
                        ],
                    }
                )

            for tool_call in collected_tool_calls:
                response_body["output"].append(
                    {
                        "type": "function_call",
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments"],
                        "call_id": tool_call["call_id"],
                    }
                )

        # Create a new response with the complete body
        body_bytes = json.dumps(response_body).encode("utf-8")
        logger.debug(f"Reconstructed response body: {len(body_bytes)} bytes")

        new_response = httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=body_bytes,
            request=response.request,
        )
        return new_response


def create_codex_async_client(
    headers: dict[str, str] | None = None,
    verify: str | bool = True,
    **kwargs: Any,
) -> ChatGPTCodexAsyncClient:
    """Create a ChatGPT Codex async client with proper configuration."""
    return ChatGPTCodexAsyncClient(
        headers=headers,
        verify=verify,
        timeout=httpx.Timeout(300.0, connect=30.0),
        **kwargs,
    )
