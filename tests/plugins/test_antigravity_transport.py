"""Comprehensive test coverage for Antigravity OAuth transport module.

Tests the HTTP transport mechanisms, authentication header handling,
request/response processing, error handling, retries, and async patterns
for the Antigravity OAuth plugin.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from code_puppy.plugins.antigravity_oauth.transport import (
    AntigravityClient,
    UnwrappedResponse,
    UnwrappedSSEResponse,
    _inline_refs,
    create_antigravity_client,
)


class TestInlineRefs:
    """Test cases for _inline_refs schema transformation function."""

    def test_inline_refs_basic_resolution(self):
        """Test basic $ref resolution from $defs."""
        schema = {
            "type": "object",
            "$defs": {
                "Person": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "number"},
                    },
                }
            },
            "properties": {"user": {"$ref": "#/$defs/Person"}},
        }

        result = _inline_refs(schema)

        assert "$defs" not in result
        assert result["properties"]["user"]["type"] == "object"
        assert "name" in result["properties"]["user"]["properties"]

    def test_inline_refs_definitions_key(self):
        """Test $ref resolution from 'definitions' key (alternative to $defs)."""
        schema = {
            "type": "object",
            "definitions": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"},
                    },
                }
            },
            "properties": {"address": {"$ref": "#/definitions/Address"}},
        }

        result = _inline_refs(schema)

        assert "definitions" not in result
        assert result["properties"]["address"]["type"] == "object"

    def test_inline_refs_unresolvable_ref(self):
        """Test handling of unresolvable $ref (should return generic object)."""
        schema = {
            "type": "object",
            "properties": {"data": {"$ref": "#/$defs/NonExistent"}},
        }

        result = _inline_refs(schema)

        assert result["properties"]["data"]["type"] == "object"

    def test_inline_refs_union_simplification_gemini(self):
        """Test anyOf/oneOf/allOf simplification for Gemini models.

        Gemini doesn't support union types at all - we need to simplify them!
        """
        schema = {
            "type": "object",
            "anyOf": [{"type": "string"}, {"type": "number"}],
        }

        result = _inline_refs(schema, simplify_unions=True)

        # Should simplify to the first type (string)
        assert "anyOf" not in result
        assert "any_of" not in result  # We don't convert to snake_case anymore!
        assert result["type"] == "string"

    def test_inline_refs_union_simplification_claude(self):
        """Test anyOf/oneOf simplification for Claude models."""
        schema = {
            "type": "object",
            "anyOf": [
                {"type": "string", "description": "A string value"},
                {"type": "null"},
            ],
        }

        result = _inline_refs(schema, simplify_unions=True)

        # Should simplify to just the string type (first non-null)
        assert result["type"] == "string"
        assert result["description"] == "A string value"
        assert "anyOf" not in result

    def test_inline_refs_discriminated_union_flattening(self):
        """Test flattening of discriminated unions (like EditFilePayload).

        When multiple object types are in a union, we merge them into one
        object with all properties from all types.
        """
        schema = {
            "$defs": {
                "PayloadA": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
                "PayloadB": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "delete_snippet": {"type": "string"},
                    },
                },
            },
            "type": "object",
            "properties": {
                "payload": {
                    "anyOf": [
                        {"$ref": "#/$defs/PayloadA"},
                        {"$ref": "#/$defs/PayloadB"},
                        {"type": "string"},
                    ]
                }
            },
        }

        result = _inline_refs(schema, simplify_unions=True)

        # Should flatten to single object with all properties
        assert "anyOf" not in result["properties"]["payload"]
        assert result["properties"]["payload"]["type"] == "object"
        props = result["properties"]["payload"]["properties"]
        assert "file_path" in props
        assert "content" in props
        assert "delete_snippet" in props

    def test_inline_refs_additional_properties_removed(self):
        """Test additionalProperties removal when simplifying."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": {"type": "string"},
        }

        result = _inline_refs(schema, simplify_unions=True)

        assert "additionalProperties" not in result
        assert "properties" in result

    def test_inline_refs_allof_merging(self):
        """Test allOf merging when simplifying."""
        schema = {
            "allOf": [
                {"type": "object", "properties": {"name": {"type": "string"}}},
                {"properties": {"age": {"type": "integer"}}},
            ],
        }

        result = _inline_refs(schema, simplify_unions=True)

        # allOf should be merged into a single object
        assert "allOf" not in result
        assert "all_of" not in result
        assert "properties" in result
        assert "name" in result["properties"]
        assert "age" in result["properties"]

    def test_inline_refs_removes_unsupported_fields(self):
        """Test removal of unsupported schema fields."""
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "test-schema",
            "type": "string",
            "default": "hello",
            "examples": ["example1", "example2"],
            "const": "fixed_value",
        }

        result = _inline_refs(schema)

        assert "$schema" not in result
        assert "$id" not in result
        assert "default" not in result
        assert "examples" not in result
        assert "const" not in result
        assert result["type"] == "string"

    def test_inline_refs_nested_structures(self):
        """Test nested object and array structures."""
        schema = {
            "type": "object",
            "$defs": {
                "Item": {"type": "object", "properties": {"id": {"type": "string"}}}
            },
            "properties": {
                "items": {"type": "array", "items": {"$ref": "#/$defs/Item"}}
            },
        }

        result = _inline_refs(schema)

        assert result["properties"]["items"]["type"] == "array"
        assert result["properties"]["items"]["items"]["type"] == "object"

    def test_inline_refs_non_dict_input(self):
        """Test handling of non-dict input."""
        assert _inline_refs("string") == "string"
        assert _inline_refs(123) == 123
        assert _inline_refs([1, 2, 3]) == [1, 2, 3]

    def test_inline_refs_merges_properties(self):
        """Test that properties from original object are merged with resolved ref."""
        schema = {
            "$defs": {
                "Base": {"type": "object", "properties": {"id": {"type": "string"}}}
            },
            "properties": {
                "data": {
                    "$ref": "#/$defs/Base",
                    "description": "Extended description",
                    "required": ["id"],
                }
            },
        }

        result = _inline_refs(schema)

        assert result["properties"]["data"]["type"] == "object"
        assert result["properties"]["data"]["description"] == "Extended description"
        assert "required" in result["properties"]["data"]


class TestUnwrappedResponse:
    """Test cases for UnwrappedResponse class."""

    def test_unwrapped_response_basic(self):
        """Test basic response unwrapping."""
        original = httpx.Response(
            status_code=200,
            content=b'{"response": {"message": "hello"}}',
            headers={"content-type": "application/json"},
        )

        # Simulate aread() being called
        original.read()

        unwrapped = UnwrappedResponse(original)

        assert unwrapped.status_code == 200
        assert unwrapped.json() == {"message": "hello"}
        assert unwrapped.text == '{"message": "hello"}'
        assert b'{"message": "hello"}' in unwrapped.content

    def test_unwrapped_response_no_wrapper(self):
        """Test response without Antigravity wrapper."""
        original = httpx.Response(
            status_code=200,
            content=b'{"direct": "data"}',
            headers={"content-type": "application/json"},
        )
        original.read()

        unwrapped = UnwrappedResponse(original)

        assert unwrapped.json() == {"direct": "data"}

    def test_unwrapped_response_invalid_json(self):
        """Test response with invalid JSON."""
        original = httpx.Response(
            status_code=200, content=b"not json", headers={"content-type": "text/plain"}
        )
        original.read()

        unwrapped = UnwrappedResponse(original)

        # Should fall back to raw content
        assert unwrapped.content == b"not json"
        assert unwrapped.text == "not json"

    @pytest.mark.asyncio
    async def test_unwrapped_response_aread_method(self):
        """Test async read method."""
        original = httpx.Response(
            status_code=200,
            content=b'{"response": {"test": "value"}}',
            headers={"content-type": "application/json"},
        )
        original.read()

        unwrapped = UnwrappedResponse(original)

        # Test aread
        data = await unwrapped.aread()
        assert b'{"test": "value"}' in data

        # Test read
        data_sync = unwrapped.read()
        assert data_sync == data


class TestUnwrappedSSEResponse:
    """Test cases for UnwrappedSSEResponse class."""

    @pytest.mark.asyncio
    async def test_aiter_lines_with_wrapper(self):
        """Test SSE line iteration with Antigravity wrapper."""

        class MockAsyncIter:
            def __init__(self, items):
                self.items = iter(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.items)
                except StopIteration:
                    raise StopAsyncIteration from None

        mock_response = Mock()
        mock_response.aiter_lines = Mock(
            return_value=MockAsyncIter(
                [
                    'data: {"response": {"text": "hello"}}',
                    'data: {"response": {"text": "world"}}',
                ]
            )
        )

        unwrapped = UnwrappedSSEResponse(mock_response)

        lines = []
        async for line in unwrapped.aiter_lines():
            lines.append(line)

        assert len(lines) == 2
        assert '{"text": "hello"}' in lines[0]
        assert '{"text": "world"}' in lines[1]

    @pytest.mark.asyncio
    async def test_aiter_lines_with_done(self):
        """Test SSE line iteration with [DONE] marker."""

        class MockAsyncIter:
            def __init__(self, items):
                self.items = iter(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.items)
                except StopIteration:
                    raise StopAsyncIteration from None

        mock_response = Mock()
        mock_response.aiter_lines = Mock(
            return_value=MockAsyncIter(
                [
                    'data: {"response": {"text": "hello"}}',
                    "data: [DONE]",
                ]
            )
        )

        unwrapped = UnwrappedSSEResponse(mock_response)

        lines = []
        async for line in unwrapped.aiter_lines():
            lines.append(line)

        assert len(lines) == 2
        assert "[DONE]" in lines[1]

    @pytest.mark.asyncio
    async def test_aiter_lines_non_data(self):
        """Test SSE lines that don't start with 'data: '."""

        class MockAsyncIter:
            def __init__(self, items):
                self.items = iter(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.items)
                except StopIteration:
                    raise StopAsyncIteration from None

        mock_response = Mock()
        mock_response.aiter_lines = Mock(
            return_value=MockAsyncIter(
                [
                    "event: message",
                    'data: {"response": {"text": "hello"}}',
                ]
            )
        )

        unwrapped = UnwrappedSSEResponse(mock_response)

        lines = []
        async for line in unwrapped.aiter_lines():
            lines.append(line)

        assert len(lines) == 2
        assert lines[0] == "event: message"

    @pytest.mark.asyncio
    async def test_aiter_text(self):
        """Test SSE text iteration."""

        class MockAsyncIter:
            def __init__(self, items):
                self.items = iter(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.items)
                except StopIteration:
                    raise StopAsyncIteration from None

        mock_response = Mock()
        mock_response.aiter_text = Mock(
            return_value=MockAsyncIter(
                [
                    'data: {"response": {"text": "hello"}}\n',
                    'data: {"response": {"text": "world"}}\n',
                ]
            )
        )

        unwrapped = UnwrappedSSEResponse(mock_response)

        chunks = []
        async for chunk in unwrapped.aiter_text():
            chunks.append(chunk)

        assert len(chunks) == 2
        assert '"text": "hello"' in chunks[0]

    @pytest.mark.asyncio
    async def test_aiter_bytes(self):
        """Test SSE bytes iteration."""

        class MockAsyncIter:
            def __init__(self, items):
                self.items = iter(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.items)
                except StopIteration:
                    raise StopAsyncIteration from None

        mock_response = Mock()
        mock_response.aiter_text = Mock(
            return_value=MockAsyncIter(
                [
                    'data: {"response": {"text": "hello"}}\n',
                ]
            )
        )

        unwrapped = UnwrappedSSEResponse(mock_response)

        chunks = []
        async for chunk in unwrapped.aiter_bytes():
            chunks.append(chunk)

        assert len(chunks) == 1
        assert isinstance(chunks[0], bytes)
        assert b'"text": "hello"' in chunks[0]


class TestAntigravityClientWrapRequest:
    """Test cases for AntigravityClient._wrap_request method."""

    def setup_method(self):
        """Setup test client."""
        self.client = AntigravityClient(project_id="test-project", model_name="")

    def test_wrap_request_basic_structure(self):
        """Test basic request wrapping structure."""
        content = b'{"contents": [{"parts": [{"text": "hello"}]}]}'
        url = "/v1/models/gemini-pro:generateContent"

        new_content, new_path, new_query, is_claude_thinking = (
            self.client._wrap_request(content, url)
        )

        wrapped = json.loads(new_content)
        assert wrapped["project"] == "test-project"
        assert wrapped["model"] == "gemini-pro"
        assert "request" in wrapped
        assert "requestId" in wrapped
        assert "userAgent" in wrapped
        assert wrapped["userAgent"] == "antigravity"

    def test_wrap_request_claude_model_extraction(self):
        """Test Claude model name extraction and tier handling."""
        content = b'{"contents": []}'
        url = "/v1/models/claude-sonnet-4-5-thinking-low:generateContent"

        new_content, new_path, new_query, is_claude_thinking = (
            self.client._wrap_request(content, url)
        )

        wrapped = json.loads(new_content)
        assert wrapped["model"] == "claude-sonnet-4-5-thinking"
        assert is_claude_thinking is True
        assert "thinkingConfig" in wrapped["request"]["generationConfig"]

    def test_wrap_request_claude_different_tiers(self):
        """Test Claude tier extraction for low/medium/high."""
        test_cases = [
            ("claude-sonnet-4-5-thinking-low", 8192),
            ("claude-sonnet-4-5-thinking-medium", 16384),
            ("claude-sonnet-4-5-thinking-high", 32768),
        ]

        for model_name, expected_budget in test_cases:
            content = b'{"contents": []}'
            url = f"/v1/models/{model_name}:generateContent"

            new_content, _, _, _ = self.client._wrap_request(content, url)

            wrapped = json.loads(new_content)
            thinking_config = wrapped["request"]["generationConfig"]["thinkingConfig"]
            assert thinking_config["thinkingBudget"] == expected_budget

    def test_wrap_request_gemini_thinking_config(self):
        """Test Gemini 3 thinking config generation."""
        content = b'{"contents": []}'
        url = "/v1/models/gemini-3-pro-high:generateContent"

        new_content, _, _, _ = self.client._wrap_request(content, url)

        wrapped = json.loads(new_content)
        thinking_config = wrapped["request"]["generationConfig"]["thinkingConfig"]
        assert thinking_config["includeThoughts"] is True
        assert thinking_config["thinkingLevel"] == "high"

    def test_wrap_request_system_instruction_cleanup(self):
        """Test systemInstruction role field removal."""
        content = b'{"contents": [], "systemInstruction": {"role": "system", "parts": [{"text": "be helpful"}]}}'
        url = "/v1/models/gemini-pro:generateContent"

        new_content, _, _, _ = self.client._wrap_request(content, url)

        wrapped = json.loads(new_content)
        sys_instruction = wrapped["request"]["systemInstruction"]
        assert "role" not in sys_instruction
        assert "parts" in sys_instruction

    def test_wrap_request_tools_transformation(self):
        """Test tools parameter transformation and $ref inlining."""
        content = json.dumps(
            {
                "tools": [
                    {
                        "functionDeclarations": [
                            {
                                "name": "test_func",
                                "parameters_json_schema": {
                                    "$defs": {
                                        "ParamType": {
                                            "type": "object",
                                            "properties": {"value": {"type": "string"}},
                                        }
                                    },
                                    "type": "object",
                                    "properties": {
                                        "param": {"$ref": "#/$defs/ParamType"},
                                        "optional_field": {
                                            "anyOf": [
                                                {"type": "string"},
                                                {"type": "null"},
                                            ]
                                        },
                                    },
                                },
                            }
                        ]
                    }
                ]
            }
        ).encode()

        url = "/v1/models/gemini-pro:generateContent"

        new_content, _, _, _ = self.client._wrap_request(content, url)

        wrapped = json.loads(new_content)
        params = wrapped["request"]["tools"][0]["functionDeclarations"][0]["parameters"]

        # Check that parameters_json_schema was renamed to parameters
        assert (
            "parameters_json_schema"
            not in wrapped["request"]["tools"][0]["functionDeclarations"][0]
        )
        assert "parameters" in wrapped["request"]["tools"][0]["functionDeclarations"][0]

        # Check that $ref was inlined
        assert "$defs" not in params
        assert params["properties"]["param"]["type"] == "object"

        # Check that anyOf unions were simplified (not converted to any_of)
        # Gemini doesn't support union types at all!
        assert "anyOf" not in params["properties"]["optional_field"]
        assert "any_of" not in params["properties"]["optional_field"]
        # The union should be simplified to just "string" (first non-null type)
        assert params["properties"]["optional_field"]["type"] == "string"

    def test_wrap_request_generation_config_cleanup(self):
        """Test generationConfig cleanup and enhancement."""
        content = json.dumps(
            {
                "generationConfig": {
                    "temperature": 0.7,
                    "responseModalities": ["TEXT"],  # Should be removed
                    "topK": 50,  # Should be preserved
                }
            }
        ).encode()

        url = "/v1/models/gemini-pro:generateContent"

        new_content, _, _, _ = self.client._wrap_request(content, url)

        wrapped = json.loads(new_content)
        gen_config = wrapped["request"]["generationConfig"]

        assert "responseModalities" not in gen_config
        assert gen_config["topK"] == 50
        assert gen_config["topP"] == 0.95  # Added if not present
        assert gen_config["maxOutputTokens"] == 64000  # Always set

    def test_wrap_request_default_project_id(self):
        """Test default project ID when not provided."""
        client = AntigravityClient(project_id="", model_name="")
        content = b'{"contents": []}'
        url = "/v1/models/gemini-pro:generateContent"

        new_content, _, _, _ = client._wrap_request(content, url)

        wrapped = json.loads(new_content)
        from code_puppy.plugins.antigravity_oauth.constants import (
            ANTIGRAVITY_DEFAULT_PROJECT_ID,
        )

        assert wrapped["project"] == ANTIGRAVITY_DEFAULT_PROJECT_ID

    def test_wrap_request_stream_url_transformation(self):
        """Test URL transformation for streaming endpoints."""
        content = b'{"contents": []}'
        url = "/v1/models/gemini-pro:streamGenerateContent"

        _, new_path, new_query, _ = self.client._wrap_request(content, url)

        assert new_path == "/v1internal:streamGenerateContent"
        assert new_query == "alt=sse"

    def test_wrap_request_regular_url_transformation(self):
        """Test URL transformation for regular endpoints."""
        content = b'{"contents": []}'
        url = "/v1/models/gemini-pro:generateContent"

        _, new_path, new_query, _ = self.client._wrap_request(content, url)

        assert new_path == "/v1internal:generateContent"
        assert new_query == ""

    def test_wrap_request_invalid_json(self):
        """Test handling of invalid JSON in request body."""
        content = b"invalid json{"
        url = "/v1/models/gemini-pro:generateContent"

        new_content, new_path, new_query, _ = self.client._wrap_request(content, url)

        # Should return original content
        assert new_content == content
        assert new_path == url
        assert new_query == ""

    def test_wrap_request_claude_non_thinking_model(self):
        """Test non-thinking Claude model handling."""
        content = b'{"contents": []}'
        url = "/v1/models/claude-sonnet-4-5:generateContent"

        new_content, _, _, is_claude_thinking = self.client._wrap_request(content, url)

        wrapped = json.loads(new_content)
        assert is_claude_thinking is False
        # Should not have thinkingConfig for non-thinking models
        gen_config = wrapped["request"].get("generationConfig", {})
        assert "thinkingConfig" not in gen_config


class TestAntigravityClientSend:
    """Test cases for AntigravityClient.send method."""

    @pytest.mark.asyncio
    async def test_send_successful_request(self):
        """Test successful request with response unwrapping."""
        client = AntigravityClient(project_id="test-project", model_name="")

        # Mock the parent send method
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"response": {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}}'
        mock_response.is_stream_consumed = False
        mock_response.aread = AsyncMock()

        with patch.object(
            httpx.AsyncClient, "send", AsyncMock(return_value=mock_response)
        ):
            request = httpx.Request(
                "POST",
                "https://example.com/v1/models/gemini-pro:generateContent",
                content=b'{"test": "data"}',
            )
            response = await client.send(request)

            assert response.status_code == 200
            # Should be unwrapped
            assert "candidates" in response.json()

    @pytest.mark.asyncio
    async def test_send_streaming_request(self):
        """Test streaming request with SSE response unwrapping."""
        client = AntigravityClient(project_id="test-project", model_name="")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/event-stream"}
        mock_response.is_stream_consumed = False

        with patch.object(
            httpx.AsyncClient, "send", AsyncMock(return_value=mock_response)
        ):
            request = httpx.Request(
                "POST",
                "/v1/models/gemini-pro:streamGenerateContent",
                content=b'{"test": "data"}',
            )
            response = await client.send(request)

            assert isinstance(response, UnwrappedSSEResponse)

    @pytest.mark.asyncio
    async def test_send_endpoint_fallback_on_403(self):
        """Test endpoint fallback on 403 error."""
        client = AntigravityClient(project_id="test-project", model_name="")

        # First endpoint returns 403, second returns 200
        responses = [
            Mock(status_code=403, is_stream_consumed=False, aread=AsyncMock()),
            Mock(
                status_code=200,
                is_stream_consumed=False,
                aread=AsyncMock(),
                content=b'{"response": {"success": true}}',
            ),
        ]

        with patch.object(httpx.AsyncClient, "send", AsyncMock(side_effect=responses)):
            request = httpx.Request(
                "POST",
                "/v1/models/gemini-pro:generateContent",
                content=b'{"test": "data"}',
            )
            response = await client.send(request)

            # Should succeed with second endpoint
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_send_endpoint_fallback_on_500(self):
        """Test endpoint fallback on 500 error."""
        client = AntigravityClient(project_id="test-project", model_name="")

        responses = [
            Mock(status_code=500, is_stream_consumed=False, aread=AsyncMock()),
            Mock(
                status_code=200,
                is_stream_consumed=False,
                aread=AsyncMock(),
                content=b'{"response": {"success": true}}',
            ),
        ]

        with patch.object(httpx.AsyncClient, "send", AsyncMock(side_effect=responses)):
            request = httpx.Request(
                "POST",
                "/v1/models/gemini-pro:generateContent",
                content=b'{"test": "data"}',
            )
            response = await client.send(request)

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_send_rate_limit_retry(self):
        """Test rate limit handling with retry."""
        client = AntigravityClient(project_id="test-project", model_name="")

        rate_limit_response = Mock()
        rate_limit_response.status_code = 429
        rate_limit_response.is_stream_consumed = False
        rate_limit_response.aread = AsyncMock()
        rate_limit_response.content = json.dumps(
            {
                "error": {
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "0.1s",
                        }
                    ]
                }
            }
        ).encode()

        success_response = Mock()
        success_response.status_code = 200
        success_response.is_stream_consumed = False
        success_response.aread = AsyncMock()
        success_response.content = b'{"response": {"success": true}}'

        with patch.object(
            httpx.AsyncClient,
            "send",
            AsyncMock(side_effect=[rate_limit_response, success_response]),
        ):
            with patch("asyncio.sleep", AsyncMock()):  # Skip actual sleep
                request = httpx.Request(
                    "POST",
                    "/v1/models/gemini-pro:generateContent",
                    content=b'{"test": "data"}',
                )
                response = await client.send(request)

                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_send_rate_limit_exhausted_retries(self):
        """Test rate limit with exhausted retries."""
        client = AntigravityClient(project_id="test-project", model_name="")

        rate_limit_response = Mock()
        rate_limit_response.status_code = 429
        rate_limit_response.is_stream_consumed = False
        rate_limit_response.aread = AsyncMock()
        rate_limit_response.content = json.dumps(
            {
                "error": {
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "0.1s",
                        }
                    ]
                }
            }
        ).encode()

        # Return rate limit many times (more than max retries)
        # The client should try each endpoint with retries
        responses = [rate_limit_response] * 20  # Provide many responses

        with patch.object(httpx.AsyncClient, "send", AsyncMock(side_effect=responses)):
            with patch("asyncio.sleep", AsyncMock()):
                request = httpx.Request(
                    "POST",
                    "/v1/models/gemini-pro:generateContent",
                    content=b'{"test": "data"}',
                )
                response = await client.send(request)

                # Should return last response (still 429) after exhausting retries
                assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_send_rate_limit_long_delay_fallback(self):
        """Test fallback to next endpoint on long rate limit delay."""
        client = AntigravityClient(project_id="test-project", model_name="")

        long_delay_response = Mock()
        long_delay_response.status_code = 429
        long_delay_response.is_stream_consumed = False
        long_delay_response.aread = AsyncMock()
        long_delay_response.content = json.dumps(
            {
                "error": {
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "60.0s",  # Too long
                        }
                    ]
                }
            }
        ).encode()

        success_response = Mock()
        success_response.status_code = 200
        success_response.is_stream_consumed = False
        success_response.aread = AsyncMock()
        success_response.content = b'{"response": {"success": true}}'

        with patch.object(
            httpx.AsyncClient,
            "send",
            AsyncMock(side_effect=[long_delay_response, success_response]),
        ):
            request = httpx.Request(
                "POST",
                "/v1/models/gemini-pro:generateContent",
                content=b'{"test": "data"}',
            )
            response = await client.send(request)

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_send_claude_thinking_headers(self):
        """Test anthropic-beta header addition for Claude thinking models."""
        client = AntigravityClient(project_id="test-project", model_name="")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"response": {"candidates": []}}'
        mock_response.is_stream_consumed = False
        mock_response.aread = AsyncMock()

        with patch.object(
            httpx.AsyncClient, "send", AsyncMock(return_value=mock_response)
        ) as mock_send:
            request = httpx.Request(
                "POST",
                "/v1/models/claude-sonnet-4-5-thinking-low:generateContent",
                content=b'{"contents": []}',
            )
            await client.send(request)

            # Check that the request was made with anthropic-beta header
            sent_request = mock_send.call_args[0][0]
            assert "anthropic-beta" in sent_request.headers
            assert (
                "interleaved-thinking-2025-05-14"
                in sent_request.headers["anthropic-beta"]
            )

    @pytest.mark.asyncio
    async def test_send_non_post_request(self):
        """Test that non-POST requests pass through unchanged."""
        client = AntigravityClient(project_id="test-project", model_name="")

        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(
            httpx.AsyncClient, "send", AsyncMock(return_value=mock_response)
        ):
            request = httpx.Request("GET", "https://example.com/api/data")
            response = await client.send(request)

            assert response.status_code == 200
            # Should call parent send method directly


class TestRateLimitParsing:
    """Test cases for rate limit delay extraction and parsing."""

    @pytest.mark.asyncio
    async def test_extract_rate_limit_delay_retry_info(self):
        """Test extracting delay from RetryInfo."""
        client = AntigravityClient()

        response = httpx.Response(
            status_code=429,
            content=json.dumps(
                {
                    "error": {
                        "details": [
                            {
                                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                                "retryDelay": "0.088325827s",
                            }
                        ]
                    }
                }
            ).encode(),
        )

        delay = await client._extract_rate_limit_delay(response)

        assert abs(delay - 0.088325827) < 0.001

    @pytest.mark.asyncio
    async def test_extract_rate_limit_delay_error_info(self):
        """Test extracting delay from ErrorInfo metadata."""
        client = AntigravityClient()

        response = httpx.Response(
            status_code=429,
            content=json.dumps(
                {
                    "error": {
                        "details": [
                            {
                                "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                                "metadata": {"quotaResetDelay": "88.325827ms"},
                            }
                        ]
                    }
                }
            ).encode(),
        )

        delay = await client._extract_rate_limit_delay(response)

        assert abs(delay - 0.088325827) < 0.001

    @pytest.mark.asyncio
    async def test_extract_rate_limit_delay_default_fallback(self):
        """Test default delay when parsing fails."""
        client = AntigravityClient()

        response = httpx.Response(status_code=429, content=b'{"error": {}}')

        delay = await client._extract_rate_limit_delay(response)

        assert delay == 2.0

    @pytest.mark.asyncio
    async def test_extract_rate_limit_delay_invalid_json(self):
        """Test handling of invalid JSON in rate limit response."""
        client = AntigravityClient()

        response = httpx.Response(status_code=429, content=b"invalid json")

        delay = await client._extract_rate_limit_delay(response)

        assert delay == 2.0

    def test_parse_duration_seconds(self):
        """Test parsing seconds format."""
        client = AntigravityClient()

        assert abs(client._parse_duration("0.5s") - 0.5) < 0.001
        assert abs(client._parse_duration("10s") - 10.0) < 0.001

    def test_parse_duration_milliseconds(self):
        """Test parsing milliseconds format."""
        client = AntigravityClient()

        assert abs(client._parse_duration("500ms") - 0.5) < 0.001
        assert abs(client._parse_duration("1000ms") - 1.0) < 0.001

    def test_parse_duration_raw_number(self):
        """Test parsing raw number (assumed seconds)."""
        client = AntigravityClient()

        assert abs(client._parse_duration("2.5") - 2.5) < 0.001

    def test_parse_duration_invalid(self):
        """Test handling of invalid duration strings."""
        client = AntigravityClient()

        assert client._parse_duration("") is None
        assert client._parse_duration("invalid") is None
        assert client._parse_duration(None) is None

    def test_parse_duration_whitespace(self):
        """Test parsing with whitespace."""
        client = AntigravityClient()

        assert abs(client._parse_duration("  0.5s  ") - 0.5) < 0.001


class TestCreateAntigravityClient:
    """Test cases for create_antigravity_client factory function."""

    def test_create_client_basic(self):
        """Test basic client creation."""
        client = create_antigravity_client(
            access_token="test-token",
            project_id="test-project",
            model_name="gemini-pro",
        )

        assert isinstance(client, AntigravityClient)
        assert client.project_id == "test-project"
        assert client.model_name == "gemini-pro"

    def test_create_client_auth_header(self):
        """Test Authorization header is set correctly."""
        client = create_antigravity_client(access_token="test-token-123")

        assert client.headers["Authorization"] == "Bearer test-token-123"

    def test_create_client_default_headers(self):
        """Test default Antigravity headers are included."""
        client = create_antigravity_client(access_token="test-token")

        assert "X-Goog-Api-Client" in client.headers
        assert "Client-Metadata" in client.headers
        assert "x-goog-api-key" in client.headers
        assert client.headers["x-goog-api-key"] == ""

    def test_create_client_custom_headers(self):
        """Test custom headers override defaults."""
        client = create_antigravity_client(
            access_token="test-token",
            headers={"X-Custom": "value", "Authorization": "Bearer override"},
        )

        assert client.headers["X-Custom"] == "value"
        assert client.headers["Authorization"] == "Bearer override"

    def test_create_client_timeout_configuration(self):
        """Test timeout configuration."""
        client = create_antigravity_client(access_token="test-token")

        assert client.timeout.connect == 30.0
        assert client.timeout.read == 180.0

    def test_create_client_base_url(self):
        """Test base URL configuration."""
        custom_url = "https://custom.example.com"
        client = create_antigravity_client(
            access_token="test-token", base_url=custom_url
        )

        assert str(client.base_url).rstrip("/") == custom_url
