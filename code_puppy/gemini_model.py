"""Standalone Gemini Model for pydantic_ai - no google-genai dependency.

This module provides a custom Model implementation that uses Google's
Generative Language API directly via httpx, without the bloated google-genai
SDK dependency.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic_ai import RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelResponseStreamEvent,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from code_puppy.gemini_common import (
    _build_tools,
    _build_generation_config,
    generate_tool_call_id,
    _parse_candidate_parts,
)
from code_puppy.steer_metadata import is_steer_request

logger = logging.getLogger(__name__)

# Bypass thought signature for Gemini when no pending signature is available.
# This allows function calls to work with thinking models.
BYPASS_THOUGHT_SIGNATURE = "context_engineering_is_the_way_to_go"

# Frames an in-flight /steer as guidance for the running task rather than a
# new turn. Model-facing prompt text, so deliberately not translated.
STEER_PREAMBLE = (
    "Additional guidance for the current task; continue the existing workflow:"
)


def _split_mixed_user_contents(contents: list[dict[str, Any]]) -> None:
    """Split user turns carrying both function responses and other parts.

    Gemini rejects a user content that mixes ``function_response`` with text.
    The consecutive-user merge in ``_map_messages`` produces exactly that
    whenever a tool return is followed by a user prompt with no model turn
    between them, which ``/steer`` and Ctrl+C-interrupted runs both do.
    """
    split: list[dict[str, Any]] = []
    for content in contents:
        parts = content.get("parts", [])
        if content.get("role") != "user":
            split.append(content)
            continue
        response_parts = [part for part in parts if "function_response" in part]
        other_parts = [part for part in parts if "function_response" not in part]
        if not response_parts or not other_parts:
            split.append(content)
            continue
        # Tool results first: they answer the model's preceding call.
        split.append({"role": "user", "parts": response_parts})
        split.append({"role": "user", "parts": other_parts})
    contents[:] = split


class GeminiModel(Model):
    """Standalone Model implementation for Google's Generative Language API.

    Uses httpx directly instead of google-genai SDK.
    """

    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        http_client: httpx.AsyncClient | None = None,
    ):
        # v2 Model.__init__ wires settings/profile state and pricing preload.
        super().__init__()
        self._model_name = model_name
        self.api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client
        self._owns_client = http_client is None

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model_name

    @property
    def base_url(self) -> str:
        """Return the base URL for the API."""
        return self._base_url

    @property
    def system(self) -> str:
        """Return the provider system identifier."""
        return "google"

    def _get_instructions(
        self,
        messages: list,
        model_request_parameters,
    ) -> str | None:
        """Get additional instructions to prepend to system prompt.

        This is a compatibility method for pydantic-ai interface.
        Override in subclasses to inject custom instructions.
        """
        return None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=180)
        return self._http_client

    async def _close_client(self) -> None:
        """Close HTTP client if we own it."""
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for the request."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-goog-api-key": self.api_key,
        }

    async def _map_user_prompt(self, part: UserPromptPart) -> list[dict[str, Any]]:
        """Map a user prompt part to Gemini format."""
        parts = []

        if isinstance(part.content, str):
            parts.append({"text": part.content})
        elif isinstance(part.content, list):
            for item in part.content:
                if isinstance(item, str):
                    parts.append({"text": item})
                elif hasattr(item, "media_type") and hasattr(item, "data"):
                    # Handle file/image content
                    data = item.data
                    if isinstance(data, bytes):
                        data = base64.b64encode(data).decode("utf-8")
                    parts.append(
                        {
                            "inline_data": {
                                "mime_type": item.media_type,
                                "data": data,
                            }
                        }
                    )
                else:
                    parts.append({"text": str(item)})
        else:
            parts.append({"text": str(part.content)})

        return parts

    async def _map_messages(
        self,
        messages: list[ModelMessage],
        model_request_parameters: ModelRequestParameters,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Map pydantic-ai messages to Gemini API format."""
        contents: list[dict[str, Any]] = []
        system_parts: list[dict[str, Any]] = []
        # A normal user prompt starts the next turn and retires older steers.
        # A retired steer keeps the user's words (parity with every other
        # provider, which never drop the message) and loses only the
        # current-task framing.
        last_prompt_index = max(
            (
                i
                for i, message in enumerate(messages)
                if isinstance(message, ModelRequest)
                and not is_steer_request(message)
                and any(isinstance(part, UserPromptPart) for part in message.parts)
            ),
            default=-1,
        )
        # Gemini 400s on a block mixing function_response with text, so a steer
        # block stays closed to later merges: a tool result outstanding across
        # the steer starts its own block instead of being absorbed.
        steer_block_open = False
        steer_blocks: set[int] = set()

        def _is_steer_block(block: dict[str, Any] | None) -> bool:
            return block is not None and id(block) in steer_blocks

        for i, m in enumerate(messages):
            if is_steer_request(m):
                tool_parts: list[dict[str, Any]] = []
                steer_parts: list[dict[str, Any]] = []
                for part in m.parts:
                    if isinstance(part, SystemPromptPart):
                        system_parts.append({"text": part.content})
                    elif isinstance(part, UserPromptPart):
                        steer_parts.extend(await self._map_user_prompt(part))
                    elif isinstance(part, ToolReturnPart):
                        tool_parts.append(
                            {
                                "function_response": {
                                    "name": part.tool_name,
                                    "response": part.model_response_object(),
                                    "id": part.tool_call_id,
                                }
                            }
                        )
                    elif isinstance(part, RetryPromptPart):
                        if part.tool_name is None:
                            steer_parts.append({"text": part.model_response()})
                        else:
                            tool_parts.append(
                                {
                                    "function_response": {
                                        "name": part.tool_name,
                                        "response": {"error": part.model_response()},
                                        "id": part.tool_call_id,
                                    }
                                }
                            )

                if tool_parts:
                    # Tool returns (e.g. spliced by prune_interrupted_tool_calls)
                    # must precede steer guidance and never mix into a steer block.
                    if (
                        contents
                        and contents[-1].get("role") == "user"
                        and not _is_steer_block(contents[-1])
                    ):
                        contents[-1]["parts"].extend(tool_parts)
                    else:
                        contents.append({"role": "user", "parts": tool_parts})
                    steer_block_open = False

                if steer_parts:
                    if steer_block_open and contents and _is_steer_block(contents[-1]):
                        # Consecutive steers share one block and one preamble.
                        # A kind change (retired -> active) can only happen
                        # across the normal prompt that closes the block.
                        contents[-1]["parts"].extend(steer_parts)
                    else:
                        if i > last_prompt_index:
                            steer_parts.insert(0, {"text": STEER_PREAMBLE})
                        contents.append({"role": "user", "parts": steer_parts})
                        steer_blocks.add(id(contents[-1]))
                        steer_block_open = True
                continue
            if isinstance(m, ModelRequest):
                message_parts: list[dict[str, Any]] = []

                for part in m.parts:
                    if isinstance(part, SystemPromptPart):
                        system_parts.append({"text": part.content})
                    elif isinstance(part, UserPromptPart):
                        mapped_parts = await self._map_user_prompt(part)
                        message_parts.extend(mapped_parts)
                    elif isinstance(part, ToolReturnPart):
                        message_parts.append(
                            {
                                "function_response": {
                                    "name": part.tool_name,
                                    "response": part.model_response_object(),
                                    "id": part.tool_call_id,
                                }
                            }
                        )
                    elif isinstance(part, RetryPromptPart):
                        if part.tool_name is None:
                            message_parts.append({"text": part.model_response()})
                        else:
                            message_parts.append(
                                {
                                    "function_response": {
                                        "name": part.tool_name,
                                        "response": {"error": part.model_response()},
                                        "id": part.tool_call_id,
                                    }
                                }
                            )

                if message_parts:
                    # Merge with previous user message if exists
                    if (
                        contents
                        and contents[-1].get("role") == "user"
                        and not _is_steer_block(contents[-1])
                    ):
                        contents[-1]["parts"].extend(message_parts)
                    else:
                        contents.append({"role": "user", "parts": message_parts})
                steer_block_open = False

            elif isinstance(m, ModelResponse):
                model_parts = self._map_model_response(m)
                if model_parts:
                    # Merge with previous model message if exists
                    if contents and contents[-1].get("role") == "model":
                        contents[-1]["parts"].extend(model_parts["parts"])
                    else:
                        contents.append(model_parts)
                steer_block_open = False

        # Gemini 3.x 400s on a history ending in a model turn, which /steer
        # injection and interrupted tool calls both produce. Same trim
        # _compaction.py :: history_processor() does for Anthropic prefill.
        while contents and contents[-1].get("role") == "model":
            contents.pop()

        _split_mixed_user_contents(contents)

        # Ensure at least one content
        if not contents:
            contents = [{"role": "user", "parts": [{"text": ""}]}]

        # Get any injected instructions
        instructions = self._get_instructions(messages, model_request_parameters)
        if instructions:
            system_parts.insert(0, {"text": instructions})

        # Build system instruction
        system_instruction = None
        if system_parts:
            system_instruction = {"role": "user", "parts": system_parts}

        return system_instruction, contents

    def _map_model_response(self, m: ModelResponse) -> dict[str, Any] | None:
        """Map a ModelResponse to Gemini content format.

        For Gemini thinking models, we need to track thought signatures from
        ThinkingParts and apply them to subsequent function_call parts.
        """
        parts: list[dict[str, Any]] = []
        pending_signature: str | None = None

        for item in m.parts:
            if isinstance(item, ToolCallPart):
                part_dict: dict[str, Any] = {
                    "function_call": {
                        "name": item.tool_name,
                        "args": item.args_as_dict(),
                        "id": item.tool_call_id,
                    }
                }
                # Gemini thinking models REQUIRE thoughtSignature on function calls
                # Use pending signature from thinking or bypass signature
                part_dict["thoughtSignature"] = (
                    pending_signature
                    if pending_signature is not None
                    else BYPASS_THOUGHT_SIGNATURE
                )
                parts.append(part_dict)
            elif isinstance(item, TextPart):
                part_dict = {"text": item.content}
                # Apply pending signature to text parts too if present
                if pending_signature is not None:
                    part_dict["thoughtSignature"] = pending_signature
                    pending_signature = None
                parts.append(part_dict)
            elif isinstance(item, ThinkingPart):
                if item.content:
                    part_dict = {"text": item.content, "thought": True}
                    if item.signature:
                        part_dict["thoughtSignature"] = item.signature
                        # Store signature for subsequent parts
                        pending_signature = item.signature
                    else:
                        # No signature on thinking part, use bypass
                        pending_signature = BYPASS_THOUGHT_SIGNATURE
                    parts.append(part_dict)

        if not parts:
            return None
        return {"role": "model", "parts": parts}

    def _build_request_body(
        self,
        system_instruction,
        contents,
        model_settings,
        model_request_parameters,
        *,
        streaming: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"contents": contents}

        gen_config = _build_generation_config(model_settings)
        if gen_config:
            body["generationConfig"] = gen_config

        if system_instruction:
            body["systemInstruction"] = system_instruction

        # Add tools.
        if model_request_parameters.function_tools:
            body["tools"] = _build_tools(model_request_parameters.function_tools)

            if streaming:
                body["toolConfig"] = {
                    "functionCallingConfig": {
                        "mode": "AUTO",
                        "streamFunctionCallArguments": True,
                    }
                }

        return body

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Make a non-streaming request to the Gemini API."""
        system_instruction, contents = await self._map_messages(
            messages, model_request_parameters
        )

        body = self._build_request_body(
            system_instruction=system_instruction,
            contents=contents,
            model_settings=model_settings,
            model_request_parameters=model_request_parameters,
            streaming=False,
        )

        # Make request.
        client = await self._get_client()
        url = f"{self._base_url}/models/{self._model_name}:generateContent"
        headers = self._get_headers()

        response = await client.post(url, json=body, headers=headers)
        if response.status_code != 200:
            raise RuntimeError(
                f"Gemini API error {response.status_code}: {response.text}"
            )

        data = response.json()
        return self._parse_response(data)

    def _parse_response(self, data: dict[str, Any]) -> ModelResponse:
        """Parse the Gemini API response."""
        candidates = data.get("candidates", [])
        if not candidates:
            return ModelResponse(
                parts=[TextPart(content="")],
                model_name=self._model_name,
                usage=RequestUsage(),
            )

        usage, response_parts = _parse_candidate_parts(data, candidates)

        return ModelResponse(
            parts=response_parts,
            model_name=self._model_name,
            usage=usage,
            provider_response_id=data.get("requestId"),
            provider_name=self.system,
        )

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncIterator[StreamedResponse]:
        """Make a streaming request to the Gemini API."""
        system_instruction, contents = await self._map_messages(
            messages, model_request_parameters
        )

        body = self._build_request_body(
            system_instruction=system_instruction,
            contents=contents,
            model_settings=model_settings,
            model_request_parameters=model_request_parameters,
            streaming=True,
        )

        # Make streaming request.
        client = await self._get_client()
        url = (
            f"{self._base_url}/models/{self._model_name}:streamGenerateContent?alt=sse"
        )
        headers = self._get_headers()

        async def stream_chunks() -> AsyncIterator[dict[str, Any]]:
            async with client.stream(
                "POST", url, json=body, headers=headers
            ) as response:
                if response.status_code != 200:
                    text = await response.aread()
                    raise RuntimeError(
                        f"Gemini API error {response.status_code}: {text.decode()}"
                    )

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith("data: "):
                        json_str = line[6:]
                        if json_str:
                            try:
                                yield json.loads(json_str)

                            except json.JSONDecodeError:
                                continue

        yield GeminiStreamingResponse(
            model_request_parameters=model_request_parameters,
            _chunks=stream_chunks(),
            _model_name_str=self._model_name,
            _provider_name_str=self.system,
            _provider_url_str=self._base_url,
        )


_MISSING = object()


def _extract_partial_value(p_arg: dict) -> Any:
    for key in [
        "stringValue",
        "numberValue",
        "boolValue",
        "nullValue",
        "structValue",
        "listValue",
    ]:
        if key in p_arg:
            val = p_arg[key]
            if key == "nullValue":
                return None
            return val
    return _MISSING


def _apply_json_path(target: dict, path: str, value: Any):
    parts = path.split(".")
    curr = target
    for i, part in enumerate(parts):
        if "[" in part and part.endswith("]"):
            key, idx_str = part.split("[")
            idx = int(idx_str[:-1])
            if key not in curr:
                curr[key] = []
            while len(curr[key]) <= idx:
                curr[key].append(None)

            if i == len(parts) - 1:
                curr[key][idx] = value
            else:
                if curr[key][idx] is None:
                    curr[key][idx] = {}
                curr = curr[key][idx]
        else:
            if i == len(parts) - 1:
                curr[part] = value
            else:
                if part not in curr or curr[part] is None:
                    curr[part] = {}
                curr = curr[part]


@dataclass
class GeminiStreamingResponse(StreamedResponse):
    """Streaming response handler for Gemini API."""

    _chunks: AsyncIterator[dict[str, Any]]
    _model_name_str: str
    _provider_name_str: str = "google"
    _provider_url_str: str | None = None
    _timestamp_val: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _current_tool_call_id: str | None = None
    _current_tool_name: str | None = None
    _current_vendor_part_id: uuid.UUID | None = None
    _current_args: dict[str, Any] = field(default_factory=dict)

    async def _get_event_iterator(self) -> AsyncIterator[ModelResponseStreamEvent]:
        """Process streaming chunks and yield events."""
        async for chunk in self._chunks:
            # Extract usage
            usage_meta = chunk.get("usageMetadata", {})
            if usage_meta:
                self._usage = RequestUsage(
                    input_tokens=usage_meta.get("promptTokenCount", 0),
                    output_tokens=usage_meta.get("candidatesTokenCount", 0),
                )

            # Extract response ID
            if chunk.get("responseId"):
                self.provider_response_id = chunk["responseId"]

            candidates = chunk.get("candidates", [])
            if not candidates:
                continue

            candidate = candidates[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            for part in parts:
                # Handle thinking part
                if part.get("thought") and part.get("text") is not None:
                    for event in self._parts_manager.handle_thinking_delta(
                        vendor_part_id=None,
                        content=part["text"],
                    ):
                        yield event

                # Handle regular text
                elif part.get("text") is not None and not part.get("thought"):
                    text = part["text"]
                    if len(text) == 0:
                        continue
                    for event in self._parts_manager.handle_text_delta(
                        vendor_part_id=None,
                        content=text,
                    ):
                        yield event

                # Handle function call
                elif part.get("functionCall"):
                    fc = part["functionCall"]

                    # Check if it's a new function call
                    if fc.get("name"):
                        self._current_tool_name = fc["name"]
                        self._current_tool_call_id = (
                            fc.get("id") or generate_tool_call_id()
                        )
                        self._current_vendor_part_id = uuid.uuid4()
                        self._current_args = {}

                    delta_args = {}
                    # Handle partial arguments if present
                    if "partialArgs" in fc:
                        for p_arg in fc["partialArgs"]:
                            json_path = p_arg.get("jsonPath")
                            if json_path and json_path.startswith("$."):
                                value = _extract_partial_value(p_arg)
                                if value is not _MISSING:
                                    _apply_json_path(
                                        self._current_args, json_path[2:], value
                                    )
                                    _apply_json_path(delta_args, json_path[2:], value)

                    elif "args" in fc:
                        delta_args = fc["args"]
                        self._current_args.update(fc["args"])

                    # Yield delta event if we have a current part ID
                    if self._current_vendor_part_id:
                        event = self._parts_manager.handle_tool_call_delta(
                            vendor_part_id=self._current_vendor_part_id,
                            tool_name=self._current_tool_name,
                            args=delta_args,
                            tool_call_id=self._current_tool_call_id,
                        )
                        if event is not None:
                            yield event

    async def close_stream(self) -> None:
        """Close the SSE chunk generator (v2 cancellation contract).

        ``_chunks`` is an async generator holding the ``client.stream``
        context; ``aclose()`` unwinds it and tears down the HTTP stream.
        """
        aclose = getattr(self._chunks, "aclose", None)
        if aclose is not None:
            await aclose()

    @property
    def model_name(self) -> str:
        return self._model_name_str

    @property
    def provider_name(self) -> str | None:
        return self._provider_name_str

    @property
    def provider_url(self) -> str | None:
        return self._provider_url_str

    @property
    def timestamp(self) -> datetime:
        return self._timestamp_val
