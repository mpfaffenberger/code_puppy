"""Gemini Code Assist Model for pydantic_ai.

This module provides a custom Model implementation that uses Google's
Code Assist API (cloudcode-pa.googleapis.com) instead of the standard
Generative Language API. The Code Assist API supports OAuth authentication
and has a different request/response format.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelResponsePart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import RequestUsage

logger = logging.getLogger(__name__)


class GeminiCodeAssistModel(Model):
    """Model implementation for Google's Code Assist API.

    This uses the cloudcode-pa.googleapis.com endpoint which accepts OAuth
    tokens and has a wrapped request/response format.
    """

    def __init__(
        self,
        model_name: str,
        access_token: str,
        project_id: str,
        api_base_url: str = "https://cloudcode-pa.googleapis.com",
        api_version: str = "v1internal",
    ):
        self._model_name = model_name
        self.access_token = access_token
        self.project_id = project_id
        self.api_base_url = api_base_url
        self.api_version = api_version

    def model_name(self) -> str:
        """Return the model name."""
        return self._model_name

    @property
    def system(self) -> str:
        return "google"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Make a non-streaming request to the Code Assist API."""
        request_body = self._build_request(
            messages, model_settings, model_request_parameters
        )

        url = f"{self.api_base_url}/{self.api_version}:generateContent"
        headers = self._get_headers()

        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, json=request_body, headers=headers)

            if response.status_code != 200:
                error_text = response.text
                raise RuntimeError(
                    f"Code Assist API error {response.status_code}: {error_text}"
                )

            data = response.json()

        return self._parse_response(data)

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> AsyncIterator[StreamedResponse]:
        """Make a streaming request to the Code Assist API."""
        request_body = self._build_request(
            messages, model_settings, model_request_parameters
        )

        url = f"{self.api_base_url}/{self.api_version}:streamGenerateContent?alt=sse"
        headers = self._get_headers()

        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST", url, json=request_body, headers=headers
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise RuntimeError(
                        f"Code Assist API error {response.status_code}: {error_text.decode()}"
                    )

                yield StreamedResponse(response, self._model_name)

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for the request."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _build_request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> Dict[str, Any]:
        """Build the Code Assist API request body."""
        contents = []
        system_instruction = None

        for msg in messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, SystemPromptPart):
                        # Collect system prompt
                        if system_instruction is None:
                            system_instruction = {
                                "role": "user",
                                "parts": [{"text": part.content}],
                            }
                        else:
                            system_instruction["parts"].append({"text": part.content})
                    elif isinstance(part, UserPromptPart):
                        contents.append(
                            {
                                "role": "user",
                                "parts": [{"text": part.content}],
                            }
                        )
                    elif isinstance(part, ToolReturnPart):
                        # Serialize content to string if it's not already
                        content = part.content
                        if not isinstance(content, (str, int, float, bool, type(None))):
                            try:
                                content = json.dumps(content, default=str)
                            except (TypeError, ValueError):
                                content = str(content)
                        contents.append(
                            {
                                "role": "user",
                                "parts": [
                                    {
                                        "functionResponse": {
                                            "name": part.tool_name,
                                            "response": {"result": content},
                                        }
                                    }
                                ],
                            }
                        )
            elif isinstance(msg, ModelResponse):
                parts = []
                first_func_call = True
                for part in msg.parts:
                    if isinstance(part, TextPart):
                        parts.append({"text": part.content})
                    elif isinstance(part, ToolCallPart):
                        func_call_part = {
                            "functionCall": {
                                "name": part.tool_name,
                                "args": part.args_as_dict(),
                            }
                        }
                        # Code Assist API requires thoughtSignature on function calls
                        # Use synthetic signature to skip validation
                        if first_func_call:
                            func_call_part["thoughtSignature"] = (
                                "skip_thought_signature_validator"
                            )
                            first_func_call = False
                        parts.append(func_call_part)
                if parts:
                    contents.append({"role": "model", "parts": parts})

        # Build the inner request (Vertex-style format)
        inner_request: Dict[str, Any] = {
            "contents": contents,
        }

        if system_instruction:
            inner_request["systemInstruction"] = system_instruction

        # Add tools if available
        if model_request_parameters.function_tools:
            inner_request["tools"] = [
                self._build_tools(model_request_parameters.function_tools)
            ]

        # Add generation config
        generation_config = self._build_generation_config(model_settings)
        if generation_config:
            inner_request["generationConfig"] = generation_config

        # Wrap in Code Assist format
        return {
            "model": self._model_name,
            "project": self.project_id,
            "user_prompt_id": str(uuid.uuid4()),
            "request": inner_request,
        }

    def _build_tools(self, tools: list[ToolDefinition]) -> Dict[str, Any]:
        """Build tool definitions for the API."""
        function_declarations = []

        for tool in tools:
            func_decl: Dict[str, Any] = {
                "name": tool.name,
                "description": tool.description or "",
            }

            if tool.parameters_json_schema:
                func_decl["parametersJsonSchema"] = tool.parameters_json_schema

            function_declarations.append(func_decl)

        return {"functionDeclarations": function_declarations}

    def _build_generation_config(
        self, model_settings: ModelSettings | None
    ) -> Optional[Dict[str, Any]]:
        """Build generation config from model settings."""
        if not model_settings:
            return None

        config: Dict[str, Any] = {}

        if (
            hasattr(model_settings, "temperature")
            and model_settings.temperature is not None
        ):
            config["temperature"] = model_settings.temperature

        if hasattr(model_settings, "top_p") and model_settings.top_p is not None:
            config["topP"] = model_settings.top_p

        if (
            hasattr(model_settings, "max_tokens")
            and model_settings.max_tokens is not None
        ):
            config["maxOutputTokens"] = model_settings.max_tokens

        return config if config else None

    def _parse_response(self, data: Dict[str, Any]) -> ModelResponse:
        """Parse the Code Assist API response."""
        # Unwrap the Code Assist response format
        inner_response = data.get("response", data)

        candidates = inner_response.get("candidates", [])
        if not candidates:
            raise RuntimeError("No candidates in response")

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        response_parts: list[ModelResponsePart] = []

        for part in parts:
            if "text" in part:
                response_parts.append(TextPart(content=part["text"]))
            elif "functionCall" in part:
                func_call = part["functionCall"]
                response_parts.append(
                    ToolCallPart(
                        tool_name=func_call["name"],
                        args=func_call.get("args", {}),
                        tool_call_id=str(uuid.uuid4()),
                    )
                )

        # Extract usage metadata
        usage_meta = inner_response.get("usageMetadata", {})
        usage = RequestUsage(
            input_tokens=usage_meta.get("promptTokenCount", 0),
            output_tokens=usage_meta.get("candidatesTokenCount", 0),
        )

        return ModelResponse(
            parts=response_parts, model_name=self._model_name, usage=usage
        )


class StreamedResponse:
    """Handler for streaming responses from Code Assist API."""

    def __init__(self, response: httpx.Response, model_name: str):
        self._response = response
        self._model_name = model_name
        self._usage: Optional[RequestUsage] = None
        self._timestamp = datetime.now(timezone.utc)

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iter_chunks()

    async def _iter_chunks(self) -> AsyncIterator[str]:
        """Iterate over SSE chunks from the response."""
        async for line in self._response.aiter_lines():
            line = line.strip()

            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                    # Unwrap Code Assist format
                    inner = data.get("response", data)

                    # Extract usage if available
                    if "usageMetadata" in inner:
                        meta = inner["usageMetadata"]
                        self._usage = RequestUsage(
                            input_tokens=meta.get("promptTokenCount", 0),
                            output_tokens=meta.get("candidatesTokenCount", 0),
                        )

                    # Extract text from candidates
                    for candidate in inner.get("candidates", []):
                        content = candidate.get("content", {})
                        for part in content.get("parts", []):
                            if "text" in part:
                                yield part["text"]

                except json.JSONDecodeError:
                    logger.warning("Failed to parse SSE data: %s", data_str)
                    continue

    async def get_response_parts(self) -> list[ModelResponsePart]:
        """Get all response parts after streaming is complete."""
        text_content = ""
        tool_calls = []

        async for chunk in self:
            text_content += chunk

        parts: list[ModelResponsePart] = []
        if text_content:
            parts.append(TextPart(content=text_content))
        parts.extend(tool_calls)

        return parts

    def usage(self) -> RequestUsage:
        """Get usage statistics."""
        return self._usage or RequestUsage()

    def model_name(self) -> str:
        """Get the model name."""
        return self._model_name

    def timestamp(self) -> datetime:
        """Get the response timestamp."""
        return self._timestamp
