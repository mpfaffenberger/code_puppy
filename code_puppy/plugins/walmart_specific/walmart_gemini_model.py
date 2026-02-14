"""Walmart-specific Gemini Model implementation.

This module provides the WalmartGeminiModel class that uses Walmart's
internal Vertex AI compatible proxy backend.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic_ai._run_context import RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ModelResponsePart,
    ModelResponseStreamEvent,
    TextPart,
    ThinkingPart,
    ToolCallPart,
)
from pydantic_ai.models import ModelRequestParameters, StreamedResponse
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from code_puppy.gemini_model import GeminiModel, generate_tool_call_id

logger = logging.getLogger(__name__)


class WalmartGeminiModel(GeminiModel):
    """Gemini Model for Walmart's internal proxy backend.

    This subclass uses the Vertex AI compatible URL format that Walmart's
    backend expects:
      {base_url}/v1beta1/publishers/google/models/{model}:generateContent

    Authentication is via the X-Goog-Api-Key header (set on http_client),
    NOT via URL parameter.

    Streaming is simulated: the backend converts streaming requests to
    non-streaming under the hood, so this class calls request() and wraps
    the result as a synthetic stream for pydantic_ai compatibility.
    """

    def _build_url(self, action: str, streaming: bool = False) -> str:
        """Build the URL for Walmart's Vertex AI compatible endpoint.

        Args:
            action: The API action (e.g., 'generateContent', 'streamGenerateContent')
            streaming: Whether this is a streaming request (adds alt=sse)

        Returns:
            The full URL for the request.
        """
        base = f"{self._base_url}/v1beta1/publishers/google/models/{self._model_name}:{action}"
        if streaming:
            base += "?alt=sse"
        return base

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Make a non-streaming request to the Gemini API (header auth only)."""
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

        # Make request using Walmart's Vertex AI compatible URL format
        client = await self._get_client()
        url = self._build_url("generateContent")
        headers = self._get_headers()

        response = await client.post(url, json=body, headers=headers)

        if response.status_code != 200:
            raise RuntimeError(
                f"Gemini API error {response.status_code}: {response.text}"
            )

        data = response.json()
        return self._parse_response(data)

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncIterator[StreamedResponse]:
        """Simulate streaming by calling request() and wrapping the response.

        Walmart's backend converts streaming requests to non-streaming
        anyway, so this avoids SSE parsing issues and gives pydantic_ai
        the StreamedResponse it expects from the DBOS agent path.
        """
        # Make the actual non-streaming request
        response = await self.request(
            messages, model_settings, model_request_parameters
        )

        yield _SyntheticStreamedResponse(
            model_response=response,
            model_request_parameters=model_request_parameters,
            _model_name_str=self._model_name,
            _provider_name_str=self.system,
        )


@dataclass
class _SyntheticStreamedResponse(StreamedResponse):
    """Wraps a complete ModelResponse as a StreamedResponse.

    Used when the backend doesn't support real SSE streaming.
    Emits all parts from the pre-fetched response as stream events.
    """

    model_response: ModelResponse
    _model_name_str: str
    _provider_name_str: str = "google"
    _timestamp_val: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    async def _get_event_iterator(
        self,
    ) -> AsyncIterator[ModelResponseStreamEvent]:
        """Emit pre-fetched response parts as stream events."""
        self._usage = self.model_response.usage
        self.finish_reason = self.model_response.finish_reason
        self.provider_response_id = self.model_response.provider_response_id

        for part in self.model_response.parts:
            if isinstance(part, ThinkingPart):
                event = self._parts_manager.handle_thinking_delta(
                    vendor_part_id=None,
                    content=part.content or "",
                    signature=part.signature,
                    provider_name=self._model_name_str,
                )
                if event:
                    yield event

            elif isinstance(part, TextPart):
                for event in self._parts_manager.handle_text_delta(
                    vendor_part_id=None,
                    content=part.content,
                ):
                    yield event

            elif isinstance(part, ToolCallPart):
                event = self._parts_manager.handle_tool_call_delta(
                    vendor_part_id=uuid.uuid4(),
                    tool_name=part.tool_name,
                    args=part.args,
                    tool_call_id=part.tool_call_id
                    or generate_tool_call_id(),
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
        return None

    @property
    def timestamp(self) -> datetime:
        return self._timestamp_val
