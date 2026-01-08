from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic_ai._run_context import RunContext
from pydantic_ai.messages import (
    BuiltinToolCallPart,
    BuiltinToolReturnPart,
    FilePart,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelResponsePart,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from typing_extensions import assert_never

# Define types locally if needed to avoid import errors
try:
    from pydantic_ai.messages import BlobDict, ContentDict, FunctionCallDict, PartDict
except ImportError:
    ContentDict = dict[str, Any]
    PartDict = dict[str, Any]
    FunctionCallDict = dict[str, Any]
    BlobDict = dict[str, Any]

from pydantic_ai.messages import ModelResponseStreamEvent
from pydantic_ai.models import ModelRequestParameters, StreamedResponse
from pydantic_ai.models.google import GoogleModel, GoogleModelName, _utils
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

logger = logging.getLogger(__name__)


class AntigravityModel(GoogleModel):
    """Custom GoogleModel that correctly handles Claude thinking signatures via Antigravity."""

    async def _map_messages(
        self,
        messages: list[ModelMessage],
        model_request_parameters: ModelRequestParameters,
    ) -> tuple[ContentDict | None, list[dict]]:
        """Map messages to Google GenAI format, preserving thinking signatures.

        IMPORTANT: For Gemini with parallel function calls, the API expects:
        - Model message: [FC1 + signature, FC2, ...] (all function calls together)
        - User message: [FR1, FR2, ...] (all function responses together)

        If messages are interleaved (FC1, FR1, FC2, FR2), the API returns 400.
        This method merges consecutive same-role messages to fix this.
        """
        contents: list[dict] = []
        system_parts: list[PartDict] = []

        for m in messages:
            if isinstance(m, ModelRequest):
                message_parts: list[PartDict] = []

                for part in m.parts:
                    if isinstance(part, SystemPromptPart):
                        system_parts.append({"text": part.content})
                    elif isinstance(part, UserPromptPart):
                        # Use parent's _map_user_prompt
                        mapped_parts = await self._map_user_prompt(part)
                        # Sanitize bytes to base64 for JSON serialization
                        for mp in mapped_parts:
                            if "inline_data" in mp and "data" in mp["inline_data"]:
                                data = mp["inline_data"]["data"]
                                if isinstance(data, bytes):
                                    mp["inline_data"]["data"] = base64.b64encode(
                                        data
                                    ).decode("utf-8")
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
                    else:
                        assert_never(part)

                if message_parts:
                    # Merge with previous user message if exists (for parallel function responses)
                    if contents and contents[-1].get("role") == "user":
                        contents[-1]["parts"].extend(message_parts)
                    else:
                        contents.append({"role": "user", "parts": message_parts})

            elif isinstance(m, ModelResponse):
                # USE CUSTOM HELPER HERE
                # Pass model name so we can handle Claude vs Gemini signature placement
                maybe_content = _antigravity_content_model_response(
                    m, self.system, self._model_name
                )
                if maybe_content:
                    # Merge with previous model message if exists (for parallel function calls)
                    if contents and contents[-1].get("role") == "model":
                        contents[-1]["parts"].extend(maybe_content["parts"])
                    else:
                        contents.append(maybe_content)
            else:
                assert_never(m)

        # Google GenAI requires at least one part in the message.
        if not contents:
            contents = [{"role": "user", "parts": [{"text": ""}]}]

        if instructions := self._get_instructions(messages, model_request_parameters):
            system_parts.insert(0, {"text": instructions})
        system_instruction = (
            ContentDict(role="user", parts=system_parts) if system_parts else None
        )

        return system_instruction, contents

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Override request to use direct HTTP calls, bypassing google-genai validation."""
        # Prepare request (normalizes settings)
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )

        system_instruction, contents = await self._map_messages(
            messages, model_request_parameters
        )

        # Build generation config from model settings
        gen_config: dict[str, Any] = {}
        if model_settings:
            if (
                hasattr(model_settings, "temperature")
                and model_settings.temperature is not None
            ):
                gen_config["temperature"] = model_settings.temperature
            if hasattr(model_settings, "top_p") and model_settings.top_p is not None:
                gen_config["topP"] = model_settings.top_p
            if (
                hasattr(model_settings, "max_tokens")
                and model_settings.max_tokens is not None
            ):
                gen_config["maxOutputTokens"] = model_settings.max_tokens

        # Build JSON body manually to ensure thoughtSignature is preserved
        body: dict[str, Any] = {
            "contents": contents,
        }
        if gen_config:
            body["generationConfig"] = gen_config
        if system_instruction:
            body["systemInstruction"] = system_instruction

        # Serialize tools manually
        if model_request_parameters.function_tools:
            funcs = []
            for t in model_request_parameters.function_tools:
                funcs.append(
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters_json_schema,
                    }
                )
            body["tools"] = [{"functionDeclarations": funcs}]

        # Use the http_client from the google-genai client directly
        # This bypasses google-genai library's strict validation/serialization
        # Path: self.client._api_client._async_httpx_client
        try:
            client = self.client._api_client._async_httpx_client
        except AttributeError:
            raise RuntimeError(
                "AntigravityModel requires access to the underlying httpx client"
            )
        url = f"/models/{self._model_name}:generateContent"

        # Send request
        response = await client.post(url, json=body)

        if response.status_code != 200:
            # Check for corrupted thought signature error and retry
            # Error 400: { error: { code: 400, message: Corrupted thought signature., status: INVALID_ARGUMENT } }
            error_text = response.text
            if (
                response.status_code == 400
                and "Corrupted thought signature" in error_text
            ):
                logger.warning(
                    "Received 400 Corrupted thought signature. Backfilling signatures and retrying."
                )
                _backfill_thought_signatures(messages)

                # Re-map messages
                system_instruction, contents = await self._map_messages(
                    messages, model_request_parameters
                )

                # Update body
                body["contents"] = contents
                if system_instruction:
                    body["systemInstruction"] = system_instruction

                # Retry request
                response = await client.post(url, json=body)
                # Check error again after retry
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Antigravity API Error {response.status_code}: {response.text}"
                    )
            else:
                raise RuntimeError(
                    f"Antigravity API Error {response.status_code}: {error_text}"
                )

        data = response.json()

        # Extract candidates
        candidates = data.get("candidates", [])
        if not candidates:
            # Handle empty response or safety block?
            return ModelResponse(
                parts=[TextPart(content="")],
                model_name=self._model_name,
                usage=RequestUsage(),
            )

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        # Extract usage
        usage_meta = data.get("usageMetadata", {})
        usage = RequestUsage(
            input_tokens=usage_meta.get("promptTokenCount", 0),
            output_tokens=usage_meta.get("candidatesTokenCount", 0),
        )

        return _antigravity_process_response_from_parts(
            parts,
            candidate.get("groundingMetadata"),
            self._model_name,
            self.system,
            usage,
            vendor_id=data.get("requestId"),
        )

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncIterator[StreamedResponse]:
        """Override request_stream to use streaming with proper signature handling."""
        # Prepare request
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )

        system_instruction, contents = await self._map_messages(
            messages, model_request_parameters
        )

        # Build generation config
        gen_config: dict[str, Any] = {}
        if model_settings:
            if (
                hasattr(model_settings, "temperature")
                and model_settings.temperature is not None
            ):
                gen_config["temperature"] = model_settings.temperature
            if hasattr(model_settings, "top_p") and model_settings.top_p is not None:
                gen_config["topP"] = model_settings.top_p
            if (
                hasattr(model_settings, "max_tokens")
                and model_settings.max_tokens is not None
            ):
                gen_config["maxOutputTokens"] = model_settings.max_tokens

        # Build request body
        body: dict[str, Any] = {"contents": contents}
        if gen_config:
            body["generationConfig"] = gen_config
        if system_instruction:
            body["systemInstruction"] = system_instruction

        # Add tools
        if model_request_parameters.function_tools:
            funcs = []
            for t in model_request_parameters.function_tools:
                funcs.append(
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters_json_schema,
                    }
                )
            body["tools"] = [{"functionDeclarations": funcs}]

        # Get httpx client
        try:
            client = self.client._api_client._async_httpx_client
        except AttributeError:
            raise RuntimeError(
                "AntigravityModel requires access to the underlying httpx client"
            )

        # Use streaming endpoint
        url = f"/models/{self._model_name}:streamGenerateContent?alt=sse"

        # Create async generator for SSE events
        async def stream_chunks() -> AsyncIterator[dict[str, Any]]:
            retry_count = 0
            while retry_count < 2:
                should_retry = False
                async with client.stream("POST", url, json=body) as response:
                    if response.status_code != 200:
                        text = await response.aread()
                        error_msg = text.decode()
                        if (
                            response.status_code == 400
                            and "Corrupted thought signature" in error_msg
                            and retry_count == 0
                        ):
                            should_retry = True
                        else:
                            raise RuntimeError(
                                f"Antigravity API Error {response.status_code}: {error_msg}"
                            )

                    if not should_retry:
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line:
                                continue
                            if line.startswith("data: "):
                                json_str = line[6:]  # Remove 'data: ' prefix
                                if json_str:
                                    try:
                                        yield json.loads(json_str)
                                    except json.JSONDecodeError:
                                        continue
                        return

                # Handle retry outside the context manager
                if should_retry:
                    logger.warning(
                        "Received 400 Corrupted thought signature in stream. Backfilling and retrying."
                    )
                    _backfill_thought_signatures(messages)

                    # Re-map messages
                    system_instruction, contents = await self._map_messages(
                        messages, model_request_parameters
                    )

                    # Update body in place
                    body["contents"] = contents
                    if system_instruction:
                        body["systemInstruction"] = system_instruction

                    retry_count += 1

        # Create streaming response
        streamed = AntigravityStreamingResponse(
            model_request_parameters=model_request_parameters,
            _chunks=stream_chunks(),
            _model_name_str=self._model_name,
            _provider_name_str=self.system,
        )
        yield streamed


@dataclass
class AntigravityStreamingResponse(StreamedResponse):
    """Real streaming response that processes SSE chunks as they arrive."""

    _chunks: AsyncIterator[dict[str, Any]]
    _model_name_str: str
    _provider_name_str: str = "google"
    _timestamp_val: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    async def _get_event_iterator(self) -> AsyncIterator[ModelResponseStreamEvent]:
        """Process streaming chunks and yield events."""
        is_gemini = "gemini" in self._model_name_str.lower()
        pending_signature: str | None = None

        async for chunk in self._chunks:
            # Extract usage from chunk
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
                # Extract signature (for Gemini, it's on the functionCall part)
                thought_signature = part.get("thoughtSignature")
                if thought_signature:
                    # For Gemini: if this is a function call with signature,
                    # the signature belongs to the previous thinking block
                    if is_gemini and pending_signature is None:
                        pending_signature = thought_signature

                # Handle thought/thinking part
                if part.get("thought") and part.get("text") is not None:
                    text = part["text"]

                    event = self._parts_manager.handle_thinking_delta(
                        vendor_part_id=None,
                        content=text,
                    )
                    if event:
                        yield event

                    # For Claude: signature is ON the thinking block itself
                    # We need to explicitly set it after the part is created
                    if thought_signature and not is_gemini:
                        for existing_part in reversed(self._parts_manager._parts):
                            if isinstance(existing_part, ThinkingPart):
                                object.__setattr__(
                                    existing_part, "signature", thought_signature
                                )
                                break

                # Handle regular text
                elif part.get("text") is not None and not part.get("thought"):
                    text = part["text"]
                    if len(text) == 0:
                        continue
                    event = self._parts_manager.handle_text_delta(
                        vendor_part_id=None,
                        content=text,
                    )
                    if event:
                        yield event

                # Handle function call
                elif part.get("functionCall"):
                    fc = part["functionCall"]

                    # For Gemini: the signature on a function call belongs to the
                    # PREVIOUS thinking block. We need to retroactively set it.
                    if is_gemini and thought_signature:
                        # Find the most recent ThinkingPart and set its signature
                        for existing_part in reversed(self._parts_manager._parts):
                            if isinstance(existing_part, ThinkingPart):
                                # Directly set the signature attribute
                                object.__setattr__(
                                    existing_part, "signature", thought_signature
                                )
                                break

                    event = self._parts_manager.handle_tool_call_delta(
                        vendor_part_id=uuid4(),
                        tool_name=fc.get("name"),
                        args=fc.get("args"),
                        tool_call_id=fc.get("id") or _utils.generate_tool_call_id(),
                    )
                    if event:
                        yield event

    @property
    def model_name(self) -> str:
        return self._model_name_str

    @property
    def provider_name(self) -> str | None:
        return self._provider_name_str

    @property
    def timestamp(self) -> datetime:
        return self._timestamp_val


# Bypass signature for when no real thought signature is available.
# Gemini API requires EVERY function call to have a thoughtSignature field.
# When there's no thinking block or no signature was captured, we use this bypass.
# This specific key is the official bypass token for Gemini 3 Pro.
BYPASS_THOUGHT_SIGNATURE = "context_engineering_is_the_way_to_go"


def _antigravity_content_model_response(
    m: ModelResponse, provider_name: str, model_name: str = ""
) -> ContentDict | None:
    """Custom serializer for Antigravity that preserves ThinkingPart signatures.

    Handles different signature protocols:
    - Claude models: signature goes ON the thinking block itself
    - Gemini models: signature goes on the NEXT part (function_call or text) after thinking

    IMPORTANT: For Gemini, EVERY function call MUST have a thoughtSignature field.
    If no real signature is available (no preceding ThinkingPart, or ThinkingPart
    had no signature), we use BYPASS_THOUGHT_SIGNATURE as a fallback.
    """
    parts: list[PartDict] = []

    # Determine which protocol to use based on model name
    is_claude = "claude" in model_name.lower()
    is_gemini = "gemini" in model_name.lower()

    # For Gemini: save signature from ThinkingPart to attach to next part
    # Initialize to None - we'll use BYPASS_THOUGHT_SIGNATURE if still None when needed
    pending_signature: str | None = None

    for item in m.parts:
        part: PartDict = {}

        if isinstance(item, ToolCallPart):
            function_call = FunctionCallDict(
                name=item.tool_name, args=item.args_as_dict(), id=item.tool_call_id
            )
            part["function_call"] = function_call

            # For Gemini: ALWAYS attach a thoughtSignature to function calls.
            # Use the real signature if available, otherwise use bypass.
            # NOTE: Do NOT clear pending_signature here! Multiple tool calls
            # in a row (e.g., parallel function calls) all need the same
            # signature from the preceding ThinkingPart.
            if is_gemini:
                part["thoughtSignature"] = (
                    pending_signature
                    if pending_signature is not None
                    else BYPASS_THOUGHT_SIGNATURE
                )

        elif isinstance(item, TextPart):
            part["text"] = item.content

            # For Gemini: attach pending signature to text part if available
            # Clear signature after text since text typically ends a response
            if is_gemini and pending_signature is not None:
                part["thoughtSignature"] = pending_signature
                pending_signature = None

        elif isinstance(item, ThinkingPart):
            if item.content:
                part["text"] = item.content
                part["thought"] = True

                if item.signature:
                    if is_claude:
                        # Claude: signature goes ON the thinking block
                        part["thoughtSignature"] = item.signature
                    elif is_gemini:
                        # Gemini: save signature for NEXT part
                        pending_signature = item.signature
                    else:
                        # Default: try both (put on thinking block)
                        part["thoughtSignature"] = item.signature
                elif is_gemini:
                    # ThinkingPart exists but has no signature - use bypass
                    # This ensures subsequent tool calls still get a signature
                    pending_signature = BYPASS_THOUGHT_SIGNATURE

        elif isinstance(item, BuiltinToolCallPart):
            # Skip code execution for now
            pass

        elif isinstance(item, BuiltinToolReturnPart):
            # Skip code execution result
            pass

        elif isinstance(item, FilePart):
            content = item.content
            # Ensure data is base64 string, not bytes
            data_val = content.data
            if isinstance(data_val, bytes):
                data_val = base64.b64encode(data_val).decode("utf-8")

            inline_data_dict: BlobDict = {
                "data": data_val,
                "mime_type": content.media_type,
            }
            part["inline_data"] = inline_data_dict
        else:
            assert_never(item)

        if part:
            parts.append(part)

    if not parts:
        return None
    return ContentDict(role="model", parts=parts)


def _antigravity_process_response_from_parts(
    parts: list[Any],  # dicts or objects
    grounding_metadata: Any | None,
    model_name: GoogleModelName,
    provider_name: str,
    usage: RequestUsage,
    vendor_id: str | None,
    vendor_details: dict[str, Any] | None = None,
) -> ModelResponse:
    """Custom response parser that extracts signatures from ThinkingParts.

    Handles different signature protocols:
    - Claude: signature is ON the thinking block
    - Gemini: signature is on the NEXT part after thinking (we associate it back)
    """
    items: list[ModelResponsePart] = []

    is_gemini = "gemini" in str(model_name).lower()

    # Helper to get attribute from dict or object
    def get_attr(obj, attr):
        if isinstance(obj, dict):
            return obj.get(attr)
        return getattr(obj, attr, None)

    # First pass: collect all parts and their signatures
    parsed_parts = []
    for part in parts:
        thought_signature = get_attr(part, "thoughtSignature") or get_attr(
            part, "thought_signature"
        )

        # Also check provider details
        pd = get_attr(part, "provider_details")
        if not thought_signature and pd:
            thought_signature = pd.get("thought_signature") or pd.get(
                "thoughtSignature"
            )

        text = get_attr(part, "text")
        thought = get_attr(part, "thought")
        # API returns camelCase 'functionCall'
        function_call = get_attr(part, "functionCall") or get_attr(
            part, "function_call"
        )

        parsed_parts.append(
            {
                "text": text,
                "thought": thought,
                "function_call": function_call,
                "signature": thought_signature,
            }
        )

    # Second pass: for Gemini, associate signatures from next parts with thinking blocks
    if is_gemini:
        for i, pp in enumerate(parsed_parts):
            if pp["thought"] and not pp["signature"]:
                # Look at next part for signature
                if i + 1 < len(parsed_parts):
                    next_sig = parsed_parts[i + 1].get("signature")
                    if next_sig:
                        pp["signature"] = next_sig

    # Third pass: create ModelResponsePart objects
    for pp in parsed_parts:
        if pp["text"] is not None:
            if pp["thought"]:
                items.append(
                    ThinkingPart(content=pp["text"], signature=pp["signature"])
                )
            else:
                items.append(TextPart(content=pp["text"]))

        elif pp["function_call"]:
            fc = pp["function_call"]
            fc_name = get_attr(fc, "name")
            fc_args = get_attr(fc, "args")
            fc_id = get_attr(fc, "id") or _utils.generate_tool_call_id()

            items.append(
                ToolCallPart(tool_name=fc_name, args=fc_args, tool_call_id=fc_id)
            )

    return ModelResponse(
        parts=items,
        model_name=model_name,
        usage=usage,
        provider_response_id=vendor_id,
        provider_details=vendor_details,
        provider_name=provider_name,
    )


def _backfill_thought_signatures(messages: list[ModelMessage]) -> None:
    """Backfill all thinking parts with the bypass signature."""
    for m in messages:
        if isinstance(m, ModelResponse):
            for part in m.parts:
                if isinstance(part, ThinkingPart):
                    object.__setattr__(part, "signature", BYPASS_THOUGHT_SIGNATURE)
