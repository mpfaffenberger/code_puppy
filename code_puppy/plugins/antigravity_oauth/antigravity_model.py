"""AntigravityModel - extends GeminiModel with thinking signature handling.

This model handles the special Antigravity envelope format and preserves
Claude thinking signatures for Gemini 3 models.
"""

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
    ModelResponseStreamEvent,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters, StreamedResponse
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage
from typing_extensions import assert_never

from code_puppy.gemini_model import (
    GeminiModel,
    generate_tool_call_id,
)
from code_puppy.model_utils import _load_antigravity_prompt
from code_puppy.plugins.antigravity_oauth.transport import _inline_refs

logger = logging.getLogger(__name__)

# Type aliases for clarity
ContentDict = dict[str, Any]
PartDict = dict[str, Any]
FunctionCallDict = dict[str, Any]
BlobDict = dict[str, Any]

# Bypass signature for when no real thought signature is available.
BYPASS_THOUGHT_SIGNATURE = "context_engineering_is_the_way_to_go"


def _is_signature_error(error_text: str) -> bool:
    """Check if the error is a thought signature error that can be retried.

    Detects both:
    - Gemini: "Corrupted thought signature"
    - Claude: "thinking.signature: Field required" or similar
    """
    return (
        "Corrupted thought signature" in error_text
        or "thinking.signature" in error_text
    )


class AntigravityModel(GeminiModel):
    """Custom GeminiModel that correctly handles Claude thinking signatures via Antigravity.

    This model extends GeminiModel and adds:
    - Proper thoughtSignature handling for both Gemini and Claude models
    - Backfill logic for corrupted thought signatures
    - Special message merging for parallel function calls
    """

    def _get_instructions(
        self,
        messages: list,
        model_request_parameters,
    ) -> str | None:
        """Return the Antigravity system prompt.

        The Antigravity endpoint expects requests to include the special
        Antigravity identity prompt in the systemInstruction field.
        """
        return _load_antigravity_prompt()

    def _is_claude_model(self) -> bool:
        """Check if this is a Claude model (vs Gemini)."""
        return "claude" in self.model_name.lower()

    def _build_tools(self, tools: list) -> list[dict]:
        """Build tool definitions with model-appropriate schema handling.

        Both Gemini and Claude require simplified union types in function schemas:
        - Neither supports anyOf/oneOf/allOf in function parameter schemas
        - We simplify by picking the first non-null type from unions
        """

        function_declarations = []

        for tool in tools:
            func_decl = {
                "name": tool.name,
                "description": tool.description or "",
            }
            if tool.parameters_json_schema:
                # Simplify union types for all models (Gemini and Claude both need this)
                func_decl["parameters"] = _inline_refs(
                    tool.parameters_json_schema,
                    simplify_unions=True,  # Both Gemini and Claude need simplified unions
                )
            function_declarations.append(func_decl)

        return [{"functionDeclarations": function_declarations}]

    async def _map_messages(
        self,
        messages: list[ModelMessage],
        model_request_parameters: ModelRequestParameters,
    ) -> tuple[ContentDict | None, list[dict]]:
        """Map messages to Gemini API format, preserving thinking signatures.

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
                # Use custom helper for thinking signature handling
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

        # Get any injected instructions
        instructions = self._get_instructions(messages, model_request_parameters)
        if instructions:
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
        """Override request to handle Antigravity envelope and thinking signatures."""
        system_instruction, contents = await self._map_messages(
            messages, model_request_parameters
        )

        # Build generation config from model settings
        gen_config = self._build_generation_config(model_settings)

        # Build JSON body
        body: dict[str, Any] = {
            "contents": contents,
        }
        if gen_config:
            body["generationConfig"] = gen_config
        if system_instruction:
            body["systemInstruction"] = system_instruction

        # Serialize tools
        if model_request_parameters.function_tools:
            body["tools"] = self._build_tools(model_request_parameters.function_tools)

        # Get httpx client
        client = await self._get_client()
        url = f"/models/{self._model_name}:generateContent"

        # Send request
        response = await client.post(url, json=body)

        if response.status_code != 200:
            error_text = response.text
            if response.status_code == 400 and _is_signature_error(error_text):
                logger.warning(
                    "Received 400 signature error. Backfilling with bypass signatures and retrying. Error: %s",
                    error_text[:200],
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
        """Override request_stream for streaming with signature handling."""
        system_instruction, contents = await self._map_messages(
            messages, model_request_parameters
        )

        # Build generation config
        gen_config = self._build_generation_config(model_settings)

        # Build request body
        body: dict[str, Any] = {"contents": contents}
        if gen_config:
            body["generationConfig"] = gen_config
        if system_instruction:
            body["systemInstruction"] = system_instruction

        # Add tools
        if model_request_parameters.function_tools:
            body["tools"] = self._build_tools(model_request_parameters.function_tools)

        # Get httpx client
        client = await self._get_client()
        url = f"/models/{self._model_name}:streamGenerateContent?alt=sse"

        # Create async generator for SSE events
        async def stream_chunks() -> AsyncIterator[dict[str, Any]]:
            retry_count = 0
            nonlocal body  # Allow modification for retry

            while retry_count < 2:
                should_retry = False
                async with client.stream("POST", url, json=body) as response:
                    if response.status_code != 200:
                        text = await response.aread()
                        error_msg = text.decode()
                        if (
                            response.status_code == 400
                            and _is_signature_error(error_msg)
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
                                json_str = line[6:]
                                if json_str:
                                    try:
                                        yield json.loads(json_str)
                                    except json.JSONDecodeError:
                                        continue
                        return

                # Handle retry outside the context manager
                if should_retry:
                    logger.warning(
                        "Received 400 signature error in stream. Backfilling with bypass signatures and retrying."
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
                # Extract signature
                thought_signature = part.get("thoughtSignature")
                if thought_signature:
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

                    # For Gemini: signature on function call belongs to previous thinking
                    if is_gemini and thought_signature:
                        for existing_part in reversed(self._parts_manager._parts):
                            if isinstance(existing_part, ThinkingPart):
                                object.__setattr__(
                                    existing_part, "signature", thought_signature
                                )
                                break

                    event = self._parts_manager.handle_tool_call_delta(
                        vendor_part_id=uuid4(),
                        tool_name=fc.get("name"),
                        args=fc.get("args"),
                        tool_call_id=fc.get("id") or generate_tool_call_id(),
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


def _antigravity_content_model_response(
    m: ModelResponse, provider_name: str, model_name: str = ""
) -> ContentDict | None:
    """Custom serializer for Antigravity that preserves ThinkingPart signatures.

    Handles different signature protocols:
    - Claude models: signature goes ON the thinking block itself
    - Gemini models: signature goes on the NEXT part after thinking
    """
    parts: list[PartDict] = []

    is_claude = "claude" in model_name.lower()
    is_gemini = "gemini" in model_name.lower()

    pending_signature: str | None = None

    for item in m.parts:
        part: PartDict = {}

        if isinstance(item, ToolCallPart):
            function_call = FunctionCallDict(
                name=item.tool_name, args=item.args_as_dict(), id=item.tool_call_id
            )
            part["function_call"] = function_call

            # For Gemini: ALWAYS attach a thoughtSignature to function calls
            if is_gemini:
                part["thoughtSignature"] = (
                    pending_signature
                    if pending_signature is not None
                    else BYPASS_THOUGHT_SIGNATURE
                )

        elif isinstance(item, TextPart):
            part["text"] = item.content

            if is_gemini and pending_signature is not None:
                part["thoughtSignature"] = pending_signature
                pending_signature = None

        elif isinstance(item, ThinkingPart):
            if item.content:
                part["text"] = item.content
                part["thought"] = True

                # Try to use original signature first. If the API rejects it
                # (Gemini: "Corrupted thought signature", Claude: "thinking.signature: Field required"),
                # we'll backfill with bypass signatures and retry.
                if item.signature:
                    if is_claude:
                        # Claude expects signature ON the thinking block
                        part["thoughtSignature"] = item.signature
                    elif is_gemini:
                        # Gemini expects signature on the NEXT part
                        pending_signature = item.signature
                    else:
                        part["thoughtSignature"] = item.signature
                elif is_gemini:
                    pending_signature = BYPASS_THOUGHT_SIGNATURE

        elif isinstance(item, BuiltinToolCallPart):
            pass

        elif isinstance(item, BuiltinToolReturnPart):
            pass

        elif isinstance(item, FilePart):
            content = item.content
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
    parts: list[Any],
    grounding_metadata: Any | None,
    model_name: str,
    provider_name: str,
    usage: RequestUsage,
    vendor_id: str | None,
    vendor_details: dict[str, Any] | None = None,
) -> ModelResponse:
    """Custom response parser that extracts signatures from ThinkingParts."""
    items: list[ModelResponsePart] = []

    is_gemini = "gemini" in str(model_name).lower()

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

        pd = get_attr(part, "provider_details")
        if not thought_signature and pd:
            thought_signature = pd.get("thought_signature") or pd.get(
                "thoughtSignature"
            )

        text = get_attr(part, "text")
        thought = get_attr(part, "thought")
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
            fc_id = get_attr(fc, "id") or generate_tool_call_id()

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
