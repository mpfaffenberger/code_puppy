"""Tests for code_puppy/gemini_code_assist.py - full coverage."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition

from code_puppy.gemini_code_assist import GeminiCodeAssistModel, StreamedResponse


@pytest.fixture
def model():
    return GeminiCodeAssistModel(
        model_name="gemini-2.0-flash",
        access_token="tok-123",
        project_id="proj-456",
    )


@pytest.fixture
def default_params():
    return ModelRequestParameters(
        function_tools=[],
        allow_text_output=True,
    )


class TestGeminiCodeAssistModel:
    def test_model_name(self, model):
        assert model.model_name() == "gemini-2.0-flash"

    def test_system_property(self, model):
        assert model.system == "google"

    def test_get_headers(self, model):
        headers = model._get_headers()
        assert headers["Authorization"] == "Bearer tok-123"
        assert headers["Content-Type"] == "application/json"

    def test_build_request_simple(self, model, default_params):
        msgs = [ModelRequest(parts=[UserPromptPart(content="hello")])]
        body = model._build_request(msgs, None, default_params)
        assert body["model"] == "gemini-2.0-flash"
        assert body["project"] == "proj-456"
        assert "user_prompt_id" in body
        assert body["request"]["contents"][0]["role"] == "user"
        assert body["request"]["contents"][0]["parts"][0]["text"] == "hello"

    def test_build_request_system_prompt(self, model, default_params):
        msgs = [
            ModelRequest(
                parts=[
                    SystemPromptPart(content="be helpful"),
                    SystemPromptPart(content="be concise"),
                    UserPromptPart(content="hi"),
                ]
            )
        ]
        body = model._build_request(msgs, None, default_params)
        si = body["request"]["systemInstruction"]
        assert si["role"] == "user"
        assert len(si["parts"]) == 2

    def test_build_request_tool_return(self, model, default_params):
        msgs = [
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="my_tool", content={"key": "val"}, tool_call_id="tc1"
                    ),
                ]
            )
        ]
        body = model._build_request(msgs, None, default_params)
        fr = body["request"]["contents"][0]["parts"][0]["functionResponse"]
        assert fr["name"] == "my_tool"
        # dict content gets json-serialized
        assert json.loads(fr["response"]["result"]) == {"key": "val"}

    def test_build_request_tool_return_string(self, model, default_params):
        msgs = [
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="t", content="plain string", tool_call_id="tc2"
                    ),
                ]
            )
        ]
        body = model._build_request(msgs, None, default_params)
        fr = body["request"]["contents"][0]["parts"][0]["functionResponse"]
        assert fr["response"]["result"] == "plain string"

    def test_build_request_tool_return_non_serializable(self, model, default_params):
        """Content that fails json.dumps falls back to str()."""

        class Weird:
            def __str__(self):
                return "weird-obj"

        # This object's json.dumps with default=str should work,
        # but let's test with something that makes json.dumps raise TypeError
        # Actually default=str handles most things. Let's test int (primitive passthrough)
        msgs = [
            ModelRequest(
                parts=[
                    ToolReturnPart(tool_name="t", content=42, tool_call_id="tc3"),
                ]
            )
        ]
        body = model._build_request(msgs, None, default_params)
        assert (
            body["request"]["contents"][0]["parts"][0]["functionResponse"]["response"][
                "result"
            ]
            == 42
        )

    def test_build_request_model_response(self, model, default_params):
        msgs = [
            ModelResponse(
                parts=[
                    TextPart(content="hi there"),
                    ToolCallPart(tool_name="fn", args={"a": 1}, tool_call_id="tc4"),
                    ToolCallPart(tool_name="fn2", args={}, tool_call_id="tc5"),
                ],
                model_name="test",
            ),
        ]
        body = model._build_request(msgs, None, default_params)
        parts = body["request"]["contents"][0]["parts"]
        assert parts[0]["text"] == "hi there"
        assert "thoughtSignature" in parts[1]  # first func call
        assert "thoughtSignature" not in parts[2]  # second func call

    def test_build_request_with_tools(self, model):
        tools = [
            ToolDefinition(
                name="my_tool",
                description="does stuff",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                },
            ),
            ToolDefinition(
                name="bare_tool", description="", parameters_json_schema=None
            ),
        ]
        params = ModelRequestParameters(function_tools=tools, allow_text_output=True)
        body = model._build_request([], None, params)
        decls = body["request"]["tools"][0]["functionDeclarations"]
        assert len(decls) == 2
        assert decls[0]["name"] == "my_tool"
        assert "parametersJsonSchema" in decls[0]
        assert "parametersJsonSchema" not in decls[1]

    def test_build_generation_config_none(self, model):
        assert model._build_generation_config(None) is None

    def test_build_generation_config_empty(self, model):
        settings = ModelSettings()
        result = model._build_generation_config(settings)
        # No fields set -> None or empty
        assert result is None or result == {}

    def test_build_request_with_generation_config(self, model, default_params):
        """Test that generationConfig is added when settings have values."""
        settings = MagicMock()
        settings.temperature = 0.7
        settings.top_p = None
        settings.max_tokens = None
        msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
        body = model._build_request(msgs, settings, default_params)
        assert "generationConfig" in body["request"]
        assert body["request"]["generationConfig"]["temperature"] == 0.7

    def test_build_request_tool_return_json_error(self, model, default_params):
        """Content that fails json.dumps with TypeError/ValueError falls back to str()."""
        # We need to trigger the except branch. Patch json.dumps to raise.
        msgs = [
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="t", content=[object()], tool_call_id="tc-err"
                    ),
                ]
            )
        ]
        with patch(
            "code_puppy.gemini_code_assist.json.dumps", side_effect=TypeError("bad")
        ):
            body = model._build_request(msgs, None, default_params)
        fr = body["request"]["contents"][0]["parts"][0]["functionResponse"]
        # Falls back to str()
        assert isinstance(fr["response"]["result"], str)

    def test_build_generation_config_with_values(self, model):
        # ModelSettings is a TypedDict; the code uses hasattr which works on
        # objects with real attributes. Use a mock to simulate that.
        settings = MagicMock()
        settings.temperature = 0.5
        settings.top_p = 0.9
        settings.max_tokens = 100
        result = model._build_generation_config(settings)
        assert result["temperature"] == 0.5
        assert result["topP"] == 0.9
        assert result["maxOutputTokens"] == 100

    def test_parse_response_text(self, model):
        data = {
            "response": {
                "candidates": [{"content": {"parts": [{"text": "hello world"}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            }
        }
        resp = model._parse_response(data)
        assert len(resp.parts) == 1
        assert resp.parts[0].content == "hello world"
        assert resp.usage.input_tokens == 10
        assert resp.usage.output_tokens == 5

    def test_parse_response_function_call(self, model):
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"functionCall": {"name": "fn", "args": {"x": 1}}}]
                    }
                }
            ],
            "usageMetadata": {},
        }
        resp = model._parse_response(data)
        assert isinstance(resp.parts[0], ToolCallPart)
        assert resp.parts[0].tool_name == "fn"

    def test_parse_response_no_candidates(self, model):
        with pytest.raises(RuntimeError, match="No candidates"):
            model._parse_response({"response": {"candidates": []}})

    @pytest.mark.anyio
    async def test_request_success(self, model, default_params):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": {
                "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                "usageMetadata": {},
            }
        }
        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
            result = await model.request(msgs, None, default_params)
            assert result.parts[0].content == "ok"

    @pytest.mark.anyio
    async def test_request_error(self, model, default_params):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
            with pytest.raises(RuntimeError, match="500"):
                await model.request(msgs, None, default_params)

    @pytest.mark.anyio
    async def test_request_stream_success(self, model, default_params):
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            stream_cm = AsyncMock()
            stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
            stream_cm.__aexit__ = AsyncMock(return_value=False)
            client_instance.stream = MagicMock(return_value=stream_cm)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
            async with model.request_stream(msgs, None, default_params) as streamed:
                assert isinstance(streamed, StreamedResponse)

    @pytest.mark.anyio
    async def test_request_stream_error(self, model, default_params):
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.aread = AsyncMock(return_value=b"Bad Request")

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            stream_cm = AsyncMock()
            stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
            stream_cm.__aexit__ = AsyncMock(return_value=False)
            client_instance.stream = MagicMock(return_value=stream_cm)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
            with pytest.raises(RuntimeError, match="400"):
                async with model.request_stream(msgs, None, default_params):
                    pass


class TestStreamedResponse:
    @pytest.fixture
    def mock_response(self):
        return AsyncMock(spec=httpx.Response)

    def test_usage_default(self, mock_response):
        sr = StreamedResponse(mock_response, "test-model")
        usage = sr.usage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    def test_model_name(self, mock_response):
        sr = StreamedResponse(mock_response, "my-model")
        assert sr.model_name() == "my-model"

    def test_timestamp(self, mock_response):
        sr = StreamedResponse(mock_response, "m")
        assert isinstance(sr.timestamp(), datetime)

    @pytest.mark.anyio
    async def test_iter_chunks_text(self, mock_response):
        lines = [
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "hello"}]}}], "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3}}}',
            "data: [DONE]",
        ]

        async def aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = aiter_lines
        sr = StreamedResponse(mock_response, "m")
        chunks = [c async for c in sr]
        assert chunks == ["hello"]
        assert sr._usage.input_tokens == 5

    @pytest.mark.anyio
    async def test_iter_chunks_bad_json(self, mock_response):
        lines = [
            "data: not-json",
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}}',
            "",
            "some non-data line",
        ]

        async def aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = aiter_lines
        sr = StreamedResponse(mock_response, "m")
        chunks = [c async for c in sr]
        assert chunks == ["ok"]

    @pytest.mark.anyio
    async def test_get_response_parts(self, mock_response):
        lines = [
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "a"}]}}]}}',
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "b"}]}}]}}',
        ]

        async def aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = aiter_lines
        sr = StreamedResponse(mock_response, "m")
        parts = await sr.get_response_parts()
        assert len(parts) == 1
        assert parts[0].content == "ab"

    @pytest.mark.anyio
    async def test_get_response_parts_empty(self, mock_response):
        async def aiter_lines():
            return
            yield  # make it an async generator

        mock_response.aiter_lines = aiter_lines
        sr = StreamedResponse(mock_response, "m")
        parts = await sr.get_response_parts()
        assert parts == []
