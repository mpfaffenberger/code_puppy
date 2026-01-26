"""Walmart-specific Gemini Model implementation.

This module provides the WalmartGeminiModel class that uses Walmart's
internal Vertex AI compatible proxy backend.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic_ai._run_context import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import ModelRequestParameters, StreamedResponse
from pydantic_ai.settings import ModelSettings

from code_puppy.gemini_model import GeminiModel, GeminiStreamingResponse


class WalmartGeminiModel(GeminiModel):
    """Gemini Model for Walmart's internal proxy backend.

    This subclass uses the Vertex AI compatible URL format that Walmart's
    backend expects:
      {base_url}/v1beta1/publishers/google/models/{model}:generateContent

    Authentication is via the X-Goog-Api-Key header (set on http_client),
    NOT via URL parameter.
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
        """Make a streaming request to the Gemini API (header auth only)."""
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

        # Make streaming request using Walmart's Vertex AI compatible URL format
        client = await self._get_client()
        url = self._build_url("streamGenerateContent", streaming=True)
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
        )
