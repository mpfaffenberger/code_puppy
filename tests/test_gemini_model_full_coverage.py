"""Full coverage tests for code_puppy/gemini_model.py."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition

from code_puppy.gemini_model import (
    BYPASS_THOUGHT_SIGNATURE,
    GeminiModel,
    GeminiStreamingResponse,
    _flatten_union_to_object_gemini,
    _sanitize_schema_for_gemini,
    generate_tool_call_id,
)


@pytest.fixture
def model():
    return GeminiModel(
        model_name="gemini-2.0-flash",
        api_key="test-key",
    )


@pytest.fixture
def model_with_client():
    client = httpx.AsyncClient()
    return GeminiModel(
        model_name="gemini-2.0-flash",
        api_key="test-key",
        http_client=client,
    )


@pytest.fixture
def default_params():
    return ModelRequestParameters(
        function_tools=[],
        allow_text_output=True,
    )


# --- Utility functions ---


class TestUtilities:
    def test_generate_tool_call_id(self):
        result = generate_tool_call_id()
        uuid.UUID(result)  # should not raise

    def test_bypass_thought_signature(self):
        assert isinstance(BYPASS_THOUGHT_SIGNATURE, str)


# --- Schema sanitization ---


class TestSanitizeSchema:
    def test_non_dict_passthrough(self):
        assert _sanitize_schema_for_gemini("hello") == "hello"
        assert _sanitize_schema_for_gemini(42) == 42

    def test_removes_defs_and_additional_properties(self):
        schema = {
            "type": "object",
            "$defs": {"Foo": {"type": "string"}},
            "additionalProperties": False,
            "properties": {"x": {"type": "string"}},
        }
        result = _sanitize_schema_for_gemini(schema)
        assert "$defs" not in result
        assert "additionalProperties" not in result
        assert result["properties"]["x"]["type"] == "string"

    def test_resolves_ref(self):
        schema = {
            "$defs": {"Foo": {"type": "string", "description": "a foo"}},
            "$ref": "#/$defs/Foo",
        }
        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "string"

    def test_resolves_ref_definitions(self):
        schema = {
            "definitions": {"Bar": {"type": "integer"}},
            "$ref": "#/definitions/Bar",
        }
        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "integer"

    def test_unresolvable_ref(self):
        schema = {"$ref": "#/$defs/Missing"}
        result = _sanitize_schema_for_gemini(schema)
        assert result == {"type": "object"}

    def test_unknown_ref_format(self):
        schema = {"$ref": "http://example.com/schema"}
        result = _sanitize_schema_for_gemini(schema)
        assert result == {"type": "object"}

    def test_anyof_simple_nullable(self):
        schema = {
            "anyOf": [
                {"type": "string"},
                {"type": "null"},
            ],
            "description": "nullable string",
        }
        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "string"
        assert result["description"] == "nullable string"

    def test_oneof_simple(self):
        schema = {
            "oneOf": [
                {"type": "integer"},
                {"type": "null"},
            ],
        }
        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "integer"

    def test_anyof_complex_union_with_refs(self):
        schema = {
            "$defs": {
                "TypeA": {
                    "type": "object",
                    "properties": {"a": {"type": "string"}},
                },
                "TypeB": {
                    "type": "object",
                    "properties": {"b": {"type": "integer"}},
                },
            },
            "anyOf": [
                {"$ref": "#/$defs/TypeA"},
                {"$ref": "#/$defs/TypeB"},
            ],
            "description": "union type",
        }
        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "object"
        assert "a" in result["properties"]
        assert "b" in result["properties"]
        assert result["description"] == "union type"

    def test_anyof_with_string_and_objects(self):
        schema = {
            "anyOf": [
                {"type": "string"},
                {"type": "object", "properties": {"x": {"type": "string"}}},
                {"type": "object", "properties": {"y": {"type": "integer"}}},
            ],
        }
        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "object"
        assert "x" in result["properties"]
        assert "y" in result["properties"]

    def test_allof_merges(self):
        schema = {
            "allOf": [
                {"type": "object", "properties": {"a": {"type": "string"}}},
                {"properties": {"b": {"type": "integer"}}},
            ],
            "description": "merged",
        }
        result = _sanitize_schema_for_gemini(schema)
        assert "a" in result["properties"]
        assert "b" in result["properties"]
        assert result["description"] == "merged"

    def test_removes_default_examples_const(self):
        schema = {
            "type": "string",
            "default": "foo",
            "examples": ["a", "b"],
            "const": "fixed",
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "test",
        }
        result = _sanitize_schema_for_gemini(schema)
        assert "default" not in result
        assert "examples" not in result
        assert "const" not in result
        assert "$schema" not in result
        assert "$id" not in result

    def test_scalar_value_passthrough(self):
        """Test that scalar values in schema are returned as-is."""
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 0},
            },
        }
        result = _sanitize_schema_for_gemini(schema)
        # minimum is a scalar that goes through resolve_refs else branch
        assert result["properties"]["count"]["type"] == "integer"

    def test_recursive_list_processing(self):
        schema = {
            "type": "array",
            "items": {"type": "string"},
        }
        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "array"
        assert result["items"]["type"] == "string"

    def test_ref_with_extra_props(self):
        schema = {
            "$defs": {
                "Foo": {"type": "object", "properties": {"x": {"type": "string"}}}
            },
            "$ref": "#/$defs/Foo",
            "description": "extra desc",
        }
        result = _sanitize_schema_for_gemini(schema)
        assert result["description"] == "extra desc"
        assert "x" in result["properties"]


class TestFlattenUnion:
    def test_all_null_types(self):
        result = _flatten_union_to_object_gemini(
            [{"type": "null"}, {"type": "null"}], {}, lambda x: x
        )
        assert result == {"type": "object"}

    def test_string_only(self):
        result = _flatten_union_to_object_gemini(
            [{"type": "string"}, {"type": "null"}], {}, lambda x: x
        )
        assert result == {"type": "string"}

    def test_non_dict_items_ignored(self):
        result = _flatten_union_to_object_gemini(
            ["not a dict", {"type": "string"}], {}, lambda x: x
        )
        assert result == {"type": "string"}

    def test_unresolvable_ref_in_union(self):
        result = _flatten_union_to_object_gemini(
            [{"$ref": "#/$defs/Missing"}], {}, lambda x: x
        )
        assert result == {"type": "object"}

    def test_ref_with_definitions_prefix(self):
        defs = {"Foo": {"type": "object", "properties": {"x": {"type": "string"}}}}
        result = _flatten_union_to_object_gemini(
            [{"$ref": "#/definitions/Foo"}], defs, lambda x: x
        )
        assert "x" in result["properties"]


# --- GeminiModel properties ---


class TestGeminiModelProperties:
    def test_model_name(self, model):
        assert model.model_name == "gemini-2.0-flash"

    def test_base_url(self, model):
        assert "generativelanguage" in model.base_url

    def test_base_url_trailing_slash(self):
        m = GeminiModel("test", "key", base_url="https://example.com/")
        assert not m.base_url.endswith("/")

    def test_system(self, model):
        assert model.system == "google"

    def test_get_instructions(self, model):
        assert model._get_instructions([], None) is None

    def test_prepare_request(self, model):
        s, p = model.prepare_request(None, None)
        assert s is None and p is None

    def test_get_headers(self, model):
        h = model._get_headers()
        assert h["x-goog-api-key"] == "test-key"
        assert h["Content-Type"] == "application/json"


# --- Client management ---


class TestClientManagement:
    @pytest.mark.anyio
    async def test_get_client_creates_new(self, model):
        client = await model._get_client()
        assert isinstance(client, httpx.AsyncClient)
        await model._close_client()

    @pytest.mark.anyio
    async def test_get_client_reuses(self, model):
        c1 = await model._get_client()
        c2 = await model._get_client()
        assert c1 is c2
        await model._close_client()

    @pytest.mark.anyio
    async def test_close_client_owned(self, model):
        await model._get_client()
        await model._close_client()
        assert model._http_client is None

    @pytest.mark.anyio
    async def test_close_client_not_owned(self, model_with_client):
        await model_with_client._close_client()
        # Not owned, so not closed
        assert model_with_client._http_client is not None
        await model_with_client._http_client.aclose()


# --- Message mapping ---


class TestMapUserPrompt:
    @pytest.mark.anyio
    async def test_string_content(self, model):
        part = UserPromptPart(content="hello")
        result = await model._map_user_prompt(part)
        assert result == [{"text": "hello"}]

    @pytest.mark.anyio
    async def test_list_content_strings(self, model):
        part = UserPromptPart(content=["a", "b"])
        result = await model._map_user_prompt(part)
        assert result == [{"text": "a"}, {"text": "b"}]

    @pytest.mark.anyio
    async def test_list_content_media(self, model):
        media = MagicMock()
        media.media_type = "image/png"
        media.data = b"\x89PNG"
        part = UserPromptPart(content=[media])
        result = await model._map_user_prompt(part)
        assert "inline_data" in result[0]
        assert result[0]["inline_data"]["mime_type"] == "image/png"

    @pytest.mark.anyio
    async def test_list_content_media_string_data(self, model):
        media = MagicMock()
        media.media_type = "image/jpeg"
        media.data = "already-base64"
        part = UserPromptPart(content=[media])
        result = await model._map_user_prompt(part)
        assert result[0]["inline_data"]["data"] == "already-base64"

    @pytest.mark.anyio
    async def test_list_content_other(self, model):
        part = UserPromptPart(content=[42])
        result = await model._map_user_prompt(part)
        assert result == [{"text": "42"}]

    @pytest.mark.anyio
    async def test_non_string_non_list(self, model):
        part = UserPromptPart(content=123)
        result = await model._map_user_prompt(part)
        assert result == [{"text": "123"}]


class TestMapMessages:
    @pytest.mark.anyio
    async def test_empty_messages(self, model, default_params):
        si, contents = await model._map_messages([], default_params)
        assert si is None
        assert len(contents) == 1  # fallback empty content

    @pytest.mark.anyio
    async def test_system_prompt(self, model, default_params):
        msgs = [
            ModelRequest(
                parts=[SystemPromptPart(content="sys"), UserPromptPart(content="hi")]
            )
        ]
        si, contents = await model._map_messages(msgs, default_params)
        assert si is not None
        assert si["parts"][0]["text"] == "sys"

    @pytest.mark.anyio
    async def test_tool_return(self, model, default_params):
        msgs = [
            ModelRequest(
                parts=[ToolReturnPart(tool_name="t", content="ok", tool_call_id="id1")]
            )
        ]
        _, contents = await model._map_messages(msgs, default_params)
        fr = contents[0]["parts"][0]["function_response"]
        assert fr["name"] == "t"

    @pytest.mark.anyio
    async def test_retry_prompt_no_tool(self, model, default_params):
        msgs = [ModelRequest(parts=[RetryPromptPart(content="try again")])]
        _, contents = await model._map_messages(msgs, default_params)
        assert "text" in contents[0]["parts"][0]

    @pytest.mark.anyio
    async def test_retry_prompt_with_tool(self, model, default_params):
        msgs = [
            ModelRequest(
                parts=[
                    RetryPromptPart(content="err", tool_name="t", tool_call_id="id1")
                ]
            )
        ]
        _, contents = await model._map_messages(msgs, default_params)
        fr = contents[0]["parts"][0]["function_response"]
        assert "error" in fr["response"]

    @pytest.mark.anyio
    async def test_merge_consecutive_user_messages(self, model, default_params):
        msgs = [
            ModelRequest(parts=[UserPromptPart(content="a")]),
            ModelRequest(parts=[UserPromptPart(content="b")]),
        ]
        _, contents = await model._map_messages(msgs, default_params)
        # Both should be merged into one user message
        assert len(contents) == 1
        assert len(contents[0]["parts"]) == 2

    @pytest.mark.anyio
    async def test_merge_consecutive_model_responses(self, model, default_params):
        msgs = [
            ModelRequest(parts=[UserPromptPart(content="hi")]),
            ModelResponse(parts=[TextPart(content="a")], model_name="m"),
            ModelResponse(parts=[TextPart(content="b")], model_name="m"),
        ]
        _, contents = await model._map_messages(msgs, default_params)
        model_msgs = [c for c in contents if c["role"] == "model"]
        assert len(model_msgs) == 1
        assert len(model_msgs[0]["parts"]) == 2

    @pytest.mark.anyio
    async def test_instructions_injected(self, model, default_params):
        with patch.object(model, "_get_instructions", return_value="INJECTED"):
            msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
            si, _ = await model._map_messages(msgs, default_params)
            assert si["parts"][0]["text"] == "INJECTED"


class TestMapModelResponse:
    def test_empty_parts(self, model):
        resp = ModelResponse(parts=[], model_name="m")
        assert model._map_model_response(resp) is None

    def test_tool_call_with_bypass_signature(self, model):
        resp = ModelResponse(
            parts=[ToolCallPart(tool_name="fn", args={"a": 1}, tool_call_id="tc1")],
            model_name="m",
        )
        result = model._map_model_response(resp)
        assert result["parts"][0]["thoughtSignature"] == BYPASS_THOUGHT_SIGNATURE

    def test_thinking_then_tool_call(self, model):
        resp = ModelResponse(
            parts=[
                ThinkingPart(content="let me think", signature="sig123"),
                ToolCallPart(tool_name="fn", args={}, tool_call_id="tc1"),
            ],
            model_name="m",
        )
        result = model._map_model_response(resp)
        assert result["parts"][0]["thought"] is True
        assert result["parts"][0]["thoughtSignature"] == "sig123"
        assert result["parts"][1]["thoughtSignature"] == "sig123"

    def test_thinking_then_text(self, model):
        resp = ModelResponse(
            parts=[
                ThinkingPart(content="hmm", signature="sig456"),
                TextPart(content="answer"),
            ],
            model_name="m",
        )
        result = model._map_model_response(resp)
        assert result["parts"][1]["thoughtSignature"] == "sig456"

    def test_thinking_no_signature(self, model):
        resp = ModelResponse(
            parts=[
                ThinkingPart(content="hmm"),
                ToolCallPart(tool_name="fn", args={}, tool_call_id="tc1"),
            ],
            model_name="m",
        )
        result = model._map_model_response(resp)
        # No signature -> bypass
        assert result["parts"][1]["thoughtSignature"] == BYPASS_THOUGHT_SIGNATURE

    def test_text_without_pending_signature(self, model):
        resp = ModelResponse(
            parts=[TextPart(content="hello")],
            model_name="m",
        )
        result = model._map_model_response(resp)
        assert "thoughtSignature" not in result["parts"][0]

    def test_thinking_empty_content_ignored(self, model):
        resp = ModelResponse(
            parts=[ThinkingPart(content="")],
            model_name="m",
        )
        result = model._map_model_response(resp)
        assert result is None


# --- Build tools ---


class TestBuildTools:
    def test_build_tools(self, model):
        tools = [
            ToolDefinition(
                name="fn", description="desc", parameters_json_schema={"type": "object"}
            ),
            ToolDefinition(name="fn2", description="", parameters_json_schema=None),
        ]
        result = model._build_tools(tools)
        assert len(result) == 1
        decls = result[0]["functionDeclarations"]
        assert len(decls) == 2
        assert "parameters" in decls[0]
        assert "parameters" not in decls[1]


# --- Build generation config ---


class TestBuildGenerationConfig:
    def test_none_settings(self, model):
        assert model._build_generation_config(None) == {}

    def test_with_temperature(self, model):
        s = {"temperature": 0.5}
        result = model._build_generation_config(s)
        assert result["temperature"] == 0.5

    def test_with_top_p(self, model):
        result = model._build_generation_config({"top_p": 0.9})
        assert result["topP"] == 0.9

    def test_with_max_tokens(self, model):
        result = model._build_generation_config({"max_tokens": 100})
        assert result["maxOutputTokens"] == 100

    def test_thinking_disabled(self, model):
        result = model._build_generation_config({"thinking_enabled": False})
        assert "thinkingConfig" not in result

    def test_thinking_level(self, model):
        result = model._build_generation_config({"thinking_level": "high"})
        assert result["thinkingConfig"]["thinkingLevel"] == "high"
        assert result["thinkingConfig"]["includeThoughts"] is True


# --- Request ---


class TestRequest:
    @pytest.mark.anyio
    async def test_request_success(self, model, default_params):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_resp)
        model._http_client = mock_client

        msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
        result = await model.request(msgs, None, default_params)
        assert result.parts[0].content == "ok"
        assert result.usage.input_tokens == 10

    @pytest.mark.anyio
    async def test_request_with_tools_and_settings(self, model):
        tools = [
            ToolDefinition(
                name="fn", description="d", parameters_json_schema={"type": "object"}
            )
        ]
        params = ModelRequestParameters(function_tools=tools, allow_text_output=True)
        settings = {"temperature": 0.5}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {},
        }
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_resp)
        model._http_client = mock_client

        msgs = [
            ModelRequest(
                parts=[SystemPromptPart(content="sys"), UserPromptPart(content="hi")]
            )
        ]
        await model.request(msgs, settings, params)
        call_body = mock_client.post.call_args[1]["json"]
        assert "tools" in call_body
        assert "generationConfig" in call_body
        assert "systemInstruction" in call_body

    @pytest.mark.anyio
    async def test_request_error(self, model, default_params):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Error"

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_resp)
        model._http_client = mock_client

        msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
        with pytest.raises(RuntimeError, match="500"):
            await model.request(msgs, None, default_params)


# --- Parse response ---


class TestParseResponse:
    def test_no_candidates(self, model):
        result = model._parse_response({"candidates": []})
        assert result.parts[0].content == ""

    def test_no_candidates_key(self, model):
        result = model._parse_response({})
        assert result.parts[0].content == ""

    def test_text_part(self, model):
        data = {
            "candidates": [{"content": {"parts": [{"text": "hello"}]}}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 2},
            "requestId": "req123",
        }
        result = model._parse_response(data)
        assert isinstance(result.parts[0], TextPart)
        assert result.provider_response_id == "req123"

    def test_thinking_part(self, model):
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "thinking...",
                                "thought": True,
                                "thoughtSignature": "sig",
                            }
                        ]
                    }
                }
            ],
            "usageMetadata": {},
        }
        result = model._parse_response(data)
        assert isinstance(result.parts[0], ThinkingPart)
        assert result.parts[0].signature == "sig"

    def test_function_call(self, model):
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "fn",
                                    "args": {"x": 1},
                                    "id": "tc1",
                                }
                            }
                        ]
                    }
                }
            ],
            "usageMetadata": {},
        }
        result = model._parse_response(data)
        assert isinstance(result.parts[0], ToolCallPart)
        assert result.parts[0].tool_call_id == "tc1"

    def test_function_call_no_id(self, model):
        data = {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "fn"}}]}}],
            "usageMetadata": {},
        }
        result = model._parse_response(data)
        assert result.parts[0].tool_call_id  # auto-generated


# --- Streaming ---


class TestRequestStream:
    @pytest.mark.anyio
    async def test_stream_success(self, model, default_params):
        chunks = [
            "",
            'data: {"candidates": [{"content": {"parts": [{"text": "hi"}]}}], "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}, "responseId": "r1"}',
            "not a data line",
            'data: {"candidates": [{"content": {"parts": [{"text": ""}]}}]}',  # empty text
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def aiter_lines():
            for line in chunks:
                yield line

        mock_response.aiter_lines = aiter_lines

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        model._http_client = mock_client

        msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
        async with model.request_stream(msgs, None, default_params) as streamed:
            events = []
            async for event in streamed:
                events.append(event)

    @pytest.mark.anyio
    async def test_stream_error(self, model, default_params):
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.aread = AsyncMock(return_value=b"Bad Request")

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        model._http_client = mock_client

        msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
        async with model.request_stream(msgs, None, default_params) as streamed:
            with pytest.raises(RuntimeError, match="400"):
                async for _ in streamed:
                    pass

    @pytest.mark.anyio
    async def test_stream_bad_json(self, model, default_params):
        chunks = [
            "data: not-valid-json",
            'data: {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}',
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def aiter_lines():
            for line in chunks:
                yield line

        mock_response.aiter_lines = aiter_lines

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        model._http_client = mock_client

        msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
        async with model.request_stream(msgs, None, default_params) as streamed:
            events = []
            async for event in streamed:
                events.append(event)

    @pytest.mark.anyio
    async def test_stream_with_tools_and_settings(self, model):
        tools = [
            ToolDefinition(
                name="fn", description="d", parameters_json_schema={"type": "object"}
            )
        ]
        params = ModelRequestParameters(function_tools=tools, allow_text_output=True)

        chunks = [
            'data: {"candidates": [{"content": {"parts": [{"functionCall": {"name": "fn", "args": {"x": 1}}}]}}]}',
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def aiter_lines():
            for line in chunks:
                yield line

        mock_response.aiter_lines = aiter_lines

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        model._http_client = mock_client

        msgs = [
            ModelRequest(
                parts=[SystemPromptPart(content="sys"), UserPromptPart(content="hi")]
            )
        ]
        async with model.request_stream(msgs, {"temperature": 0.5}, params) as streamed:
            async for _ in streamed:
                pass

    @pytest.mark.anyio
    async def test_stream_thinking_part(self, model, default_params):
        chunks = [
            'data: {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": true}]}}]}',
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def aiter_lines():
            for line in chunks:
                yield line

        mock_response.aiter_lines = aiter_lines

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        model._http_client = mock_client

        msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
        async with model.request_stream(msgs, None, default_params) as streamed:
            async for _ in streamed:
                pass

    @pytest.mark.anyio
    async def test_stream_no_candidates(self, model, default_params):
        chunks = [
            'data: {"usageMetadata": {"promptTokenCount": 5}}',
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def aiter_lines():
            for line in chunks:
                yield line

        mock_response.aiter_lines = aiter_lines

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        model._http_client = mock_client

        msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
        async with model.request_stream(msgs, None, default_params) as streamed:
            async for _ in streamed:
                pass


class TestGeminiStreamingResponseProperties:
    def test_properties(self):
        async def empty():
            return
            yield

        sr = GeminiStreamingResponse(
            model_request_parameters=ModelRequestParameters(
                function_tools=[], allow_text_output=True
            ),
            _chunks=empty(),
            _model_name_str="gemini-test",
            _provider_name_str="google",
            _provider_url_str="https://example.com",
        )
        assert sr.model_name == "gemini-test"
        assert sr.provider_name == "google"
        assert sr.provider_url == "https://example.com"
        assert isinstance(sr.timestamp, datetime)

    def test_default_provider(self):
        async def empty():
            return
            yield

        sr = GeminiStreamingResponse(
            model_request_parameters=ModelRequestParameters(
                function_tools=[], allow_text_output=True
            ),
            _chunks=empty(),
            _model_name_str="test",
        )
        assert sr.provider_name == "google"
        assert sr.provider_url is None
