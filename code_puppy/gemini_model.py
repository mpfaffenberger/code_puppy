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
from pydantic_ai._run_context import RunContext
from pydantic_ai.messages import (
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
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import RequestUsage

logger = logging.getLogger(__name__)

# Bypass thought signature for Gemini when no pending signature is available.
# This allows function calls to work with thinking models.
BYPASS_THOUGHT_SIGNATURE = "context_engineering_is_the_way_to_go"


def generate_tool_call_id() -> str:
    """Generate a unique tool call ID."""
    return str(uuid.uuid4())


def _flatten_union_to_object_gemini(union_items: list, defs: dict, resolve_fn) -> dict:
    """Flatten a union of object types into a single object with all properties.

    For discriminated unions like EditFilePayload, we merge all object types
    into one with all properties (Gemini doesn't support anyOf/oneOf).
    """
    import copy as copy_module

    merged_properties = {}
    has_string_type = False

    for item in union_items:
        if not isinstance(item, dict):
            continue

        # Resolve $ref first
        if "$ref" in item:
            ref_path = item["$ref"]
            ref_name = None
            if ref_path.startswith("#/$defs/"):
                ref_name = ref_path[8:]
            elif ref_path.startswith("#/definitions/"):
                ref_name = ref_path[14:]
            if ref_name and ref_name in defs:
                item = copy_module.deepcopy(defs[ref_name])
            else:
                continue

        if item.get("type") == "string":
            has_string_type = True
            continue

        if item.get("type") == "null":
            continue

        if item.get("type") == "object" or "properties" in item:
            props = item.get("properties", {})
            for prop_name, prop_schema in props.items():
                if prop_name not in merged_properties:
                    merged_properties[prop_name] = resolve_fn(
                        copy_module.deepcopy(prop_schema)
                    )

    if not merged_properties:
        return {"type": "string"} if has_string_type else {"type": "object"}

    return {
        "type": "object",
        "properties": merged_properties,
    }


def _sanitize_schema_for_gemini(schema: dict) -> dict:
    """Sanitize JSON schema for Gemini API compatibility.

    Removes/transforms fields that Gemini doesn't support:
    - $defs, definitions, $schema, $id
    - additionalProperties
    - $ref (inlined)
    - anyOf/oneOf/allOf (flattened - Gemini doesn't support unions!)
      - For unions of objects: merges into single object with all properties
      - For simple unions (string | null): picks first non-null type
    """
    import copy

    if not isinstance(schema, dict):
        return schema

    # Make a deep copy to avoid modifying original
    schema = copy.deepcopy(schema)

    # Extract $defs for reference resolution
    defs = schema.pop("$defs", schema.pop("definitions", {}))

    def resolve_refs(obj):
        """Recursively resolve $ref references and clean schema."""
        if isinstance(obj, dict):
            # Handle anyOf/oneOf unions
            for union_key in ["anyOf", "oneOf"]:
                if union_key in obj:
                    union = obj[union_key]
                    if isinstance(union, list):
                        # Check if this is a complex union of objects
                        object_count = 0
                        has_refs = False
                        for item in union:
                            if isinstance(item, dict):
                                if "$ref" in item:
                                    has_refs = True
                                    object_count += 1
                                elif (
                                    item.get("type") == "object" or "properties" in item
                                ):
                                    object_count += 1

                        # If multiple objects or has refs, flatten to single object
                        if object_count > 1 or has_refs:
                            flattened = _flatten_union_to_object_gemini(
                                union, defs, resolve_refs
                            )
                            if "description" in obj:
                                flattened["description"] = obj["description"]
                            return flattened

                        # Simple union - pick first non-null type
                        for item in union:
                            if isinstance(item, dict) and item.get("type") != "null":
                                result = dict(item)
                                if "description" in obj:
                                    result["description"] = obj["description"]
                                return resolve_refs(result)

            # Handle allOf by merging all schemas
            if "allOf" in obj:
                all_of = obj["allOf"]
                if isinstance(all_of, list):
                    merged = {}
                    merged_properties = {}
                    for item in all_of:
                        if isinstance(item, dict):
                            resolved_item = resolve_refs(item)
                            if "properties" in resolved_item:
                                merged_properties.update(
                                    resolved_item.pop("properties")
                                )
                            merged.update(resolved_item)
                    if merged_properties:
                        merged["properties"] = merged_properties
                    for k, v in obj.items():
                        if k != "allOf":
                            merged[k] = v
                    return resolve_refs(merged)

            # Check for $ref
            if "$ref" in obj:
                ref_path = obj["$ref"]
                ref_name = None

                # Parse ref like "#/$defs/SomeType" or "#/definitions/SomeType"
                if ref_path.startswith("#/$defs/"):
                    ref_name = ref_path[8:]
                elif ref_path.startswith("#/definitions/"):
                    ref_name = ref_path[14:]

                if ref_name and ref_name in defs:
                    resolved = resolve_refs(copy.deepcopy(defs[ref_name]))
                    other_props = {k: v for k, v in obj.items() if k != "$ref"}
                    if other_props:
                        resolved.update(resolve_refs(other_props))
                    return resolved
                else:
                    return {"type": "object"}

            # Recursively process and transform
            result = {}
            for key, value in obj.items():
                # Skip unsupported fields
                if key in (
                    "$defs",
                    "definitions",
                    "$schema",
                    "$id",
                    "additionalProperties",
                    "default",
                    "examples",
                    "const",
                    "anyOf",  # Skip any remaining union types
                    "oneOf",
                    "allOf",
                ):
                    continue

                result[key] = resolve_refs(value)
            return result
        elif isinstance(obj, list):
            return [resolve_refs(item) for item in obj]
        else:
            return obj

    return resolve_refs(schema)


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

    def prepare_request(
        self,
        model_settings: ModelSettings | None,
        model_request_parameters,
    ) -> tuple:
        """Prepare request by normalizing settings.

        This is a compatibility method for pydantic-ai interface.
        """
        return model_settings, model_request_parameters

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

        for m in messages:
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
                    if contents and contents[-1].get("role") == "user":
                        contents[-1]["parts"].extend(message_parts)
                    else:
                        contents.append({"role": "user", "parts": message_parts})

            elif isinstance(m, ModelResponse):
                model_parts = self._map_model_response(m)
                if model_parts:
                    # Merge with previous model message if exists
                    if contents and contents[-1].get("role") == "model":
                        contents[-1]["parts"].extend(model_parts["parts"])
                    else:
                        contents.append(model_parts)

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

    def _build_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """Build tool definitions for the API."""
        function_declarations = []

        for tool in tools:
            func_decl: dict[str, Any] = {
                "name": tool.name,
                "description": tool.description or "",
            }
            if tool.parameters_json_schema:
                # Sanitize schema for Gemini compatibility
                func_decl["parameters"] = _sanitize_schema_for_gemini(
                    tool.parameters_json_schema
                )
            function_declarations.append(func_decl)

        return [{"functionDeclarations": function_declarations}]

    def _build_generation_config(
        self, model_settings: ModelSettings | None
    ) -> dict[str, Any]:
        """Build generation config from model settings."""
        config: dict[str, Any] = {}

        if model_settings:
            # ModelSettings is a TypedDict, so use .get() for all access
            temperature = model_settings.get("temperature")
            if temperature is not None:
                config["temperature"] = temperature

            top_p = model_settings.get("top_p")
            if top_p is not None:
                config["topP"] = top_p

            max_tokens = model_settings.get("max_tokens")
            if max_tokens is not None:
                config["maxOutputTokens"] = max_tokens

            # Handle Gemini 3 Pro thinking settings
            thinking_enabled = model_settings.get("thinking_enabled")
            thinking_level = model_settings.get("thinking_level")

            # Build thinkingConfig if thinking settings are present
            if thinking_enabled is False:
                # Disable thinking by not including thinkingConfig
                pass
            elif thinking_level is not None:
                # Gemini 3 Pro uses thinkingLevel with values "low" or "high"
                # includeThoughts=True is required to surface the thinking in the response
                config["thinkingConfig"] = {
                    "thinkingLevel": thinking_level,
                    "includeThoughts": True,
                }

        return config

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

        # Build request body
        body: dict[str, Any] = {"contents": contents}

        gen_config = self._build_generation_config(model_settings)
        if gen_config:
            body["generationConfig"] = gen_config
        if system_instruction:
            body["systemInstruction"] = system_instruction

        # Add tools
        if model_request_parameters.function_tools:
            body["tools"] = self._build_tools(model_request_parameters.function_tools)

        # Make request
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

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        response_parts: list[ModelResponsePart] = []

        for part in parts:
            if part.get("thought") and part.get("text") is not None:
                # Thinking part
                signature = part.get("thoughtSignature")
                response_parts.append(
                    ThinkingPart(content=part["text"], signature=signature)
                )
            elif "text" in part:
                response_parts.append(TextPart(content=part["text"]))
            elif "functionCall" in part:
                fc = part["functionCall"]
                response_parts.append(
                    ToolCallPart(
                        tool_name=fc["name"],
                        args=fc.get("args", {}),
                        tool_call_id=fc.get("id") or generate_tool_call_id(),
                    )
                )

        # Extract usage
        usage_meta = data.get("usageMetadata", {})
        usage = RequestUsage(
            input_tokens=usage_meta.get("promptTokenCount", 0),
            output_tokens=usage_meta.get("candidatesTokenCount", 0),
        )

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

        # Build request body
        body: dict[str, Any] = {"contents": contents}

        gen_config = self._build_generation_config(model_settings)
        if gen_config:
            body["generationConfig"] = gen_config
        if system_instruction:
            body["systemInstruction"] = system_instruction

        # Add tools
        if model_request_parameters.function_tools:
            body["tools"] = self._build_tools(model_request_parameters.function_tools)

        # Make streaming request
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


@dataclass
class GeminiStreamingResponse(StreamedResponse):
    """Streaming response handler for Gemini API."""

    _chunks: AsyncIterator[dict[str, Any]]
    _model_name_str: str
    _provider_name_str: str = "google"
    _provider_url_str: str | None = None
    _timestamp_val: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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
                    event = self._parts_manager.handle_tool_call_delta(
                        vendor_part_id=uuid.uuid4(),
                        tool_name=fc.get("name"),
                        args=fc.get("args"),
                        tool_call_id=fc.get("id") or generate_tool_call_id(),
                    )
                    if event is not None:
                        yield event

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
