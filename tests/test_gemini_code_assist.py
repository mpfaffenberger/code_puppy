"""Comprehensive tests for gemini_code_assist.py.

Tests for the GeminiCodeAssistModel and StreamedResponse classes which
provide integration with Google's Code Assist API.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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
from pydantic_ai.usage import RequestUsage

from code_puppy.gemini_code_assist import GeminiCodeAssistModel, StreamedResponse

# =============================================================================
# Helper Classes
# =============================================================================


class AsyncIteratorMock:
    """Helper class to mock async iterators."""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


# =============================================================================
# GeminiCodeAssistModel Construction Tests
# =============================================================================


class TestGeminiCodeAssistModelConstruction:
    """Test GeminiCodeAssistModel construction and basic properties."""

    def test_basic_construction(self):
        """Test model construction with required parameters."""
        model = GeminiCodeAssistModel(
            model_name="gemini-2.0-flash",
            access_token="test_token_123",
            project_id="my-project",
        )

        assert model.model_name() == "gemini-2.0-flash"
        assert model.access_token == "test_token_123"
        assert model.project_id == "my-project"
        assert model.api_base_url == "https://cloudcode-pa.googleapis.com"
        assert model.api_version == "v1internal"

    def test_construction_with_custom_api_url(self):
        """Test model construction with custom API base URL."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
            api_base_url="https://custom.api.example.com",
        )

        assert model.api_base_url == "https://custom.api.example.com"

    def test_construction_with_custom_api_version(self):
        """Test model construction with custom API version."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
            api_version="v2",
        )

        assert model.api_version == "v2"

    def test_system_property(self):
        """Test that system property returns 'google'."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        assert model.system == "google"


# =============================================================================
# Headers Tests
# =============================================================================


class TestGetHeaders:
    """Test _get_headers method."""

    def test_headers_include_authorization(self):
        """Test that headers include proper Authorization."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="my_secret_token",
            project_id="project",
        )

        headers = model._get_headers()

        assert headers["Authorization"] == "Bearer my_secret_token"
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"


# =============================================================================
# Build Request Tests
# =============================================================================


class TestBuildRequest:
    """Test _build_request method with various message types."""

    def _create_model(self):
        """Create a test model instance."""
        return GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="test-project",
        )

    def _create_request_params(self, tools=None):
        """Create ModelRequestParameters."""
        return ModelRequestParameters(
            function_tools=tools or [],
        )

    def test_build_request_with_user_prompt(self):
        """Test building request with user prompt."""
        model = self._create_model()
        messages = [
            ModelRequest(parts=[UserPromptPart(content="Hello, world!")])
        ]

        request = model._build_request(
            messages, None, self._create_request_params()
        )

        assert request["model"] == "gemini-pro"
        assert request["project"] == "test-project"
        assert "user_prompt_id" in request
        assert len(request["request"]["contents"]) == 1
        assert request["request"]["contents"][0]["role"] == "user"
        assert request["request"]["contents"][0]["parts"][0]["text"] == "Hello, world!"

    def test_build_request_with_system_prompt(self):
        """Test building request with system prompt."""
        model = self._create_model()
        messages = [
            ModelRequest(parts=[
                SystemPromptPart(content="You are a helpful assistant."),
                UserPromptPart(content="Hi!")
            ])
        ]

        request = model._build_request(
            messages, None, self._create_request_params()
        )

        assert "systemInstruction" in request["request"]
        assert request["request"]["systemInstruction"]["role"] == "user"
        assert request["request"]["systemInstruction"]["parts"][0]["text"] == "You are a helpful assistant."

    def test_build_request_multiple_system_prompts(self):
        """Test building request with multiple system prompts."""
        model = self._create_model()
        messages = [
            ModelRequest(parts=[
                SystemPromptPart(content="Rule 1: Be helpful."),
                SystemPromptPart(content="Rule 2: Be concise."),
                UserPromptPart(content="Hi!")
            ])
        ]

        request = model._build_request(
            messages, None, self._create_request_params()
        )

        # Multiple system prompts should be combined
        assert "systemInstruction" in request["request"]
        parts = request["request"]["systemInstruction"]["parts"]
        assert len(parts) == 2
        assert parts[0]["text"] == "Rule 1: Be helpful."
        assert parts[1]["text"] == "Rule 2: Be concise."

    def test_build_request_with_tool_return(self):
        """Test building request with tool return part."""
        model = self._create_model()
        messages = [
            ModelRequest(parts=[
                ToolReturnPart(
                    tool_name="get_weather",
                    content="Sunny, 72°F",
                    tool_call_id="call_123"
                )
            ])
        ]

        request = model._build_request(
            messages, None, self._create_request_params()
        )

        content = request["request"]["contents"][0]
        assert content["role"] == "user"
        func_response = content["parts"][0]["functionResponse"]
        assert func_response["name"] == "get_weather"
        assert func_response["response"]["result"] == "Sunny, 72°F"

    def test_build_request_with_tool_return_dict_content(self):
        """Test building request with tool return containing dict."""
        model = self._create_model()
        messages = [
            ModelRequest(parts=[
                ToolReturnPart(
                    tool_name="get_data",
                    content={"temperature": 72, "unit": "F"},
                    tool_call_id="call_123"
                )
            ])
        ]

        request = model._build_request(
            messages, None, self._create_request_params()
        )

        content = request["request"]["contents"][0]
        func_response = content["parts"][0]["functionResponse"]
        # Dict content should be JSON serialized
        result = func_response["response"]["result"]
        assert json.loads(result) == {"temperature": 72, "unit": "F"}

    def test_build_request_with_model_response_text(self):
        """Test building request with model response containing text."""
        model = self._create_model()
        messages = [
            ModelRequest(parts=[UserPromptPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Hi there!")]),
        ]

        request = model._build_request(
            messages, None, self._create_request_params()
        )

        contents = request["request"]["contents"]
        assert len(contents) == 2
        assert contents[1]["role"] == "model"
        assert contents[1]["parts"][0]["text"] == "Hi there!"

    def test_build_request_with_model_response_tool_call(self):
        """Test building request with model response containing tool call."""
        model = self._create_model()
        messages = [
            ModelRequest(parts=[UserPromptPart(content="What's the weather?")]),
            ModelResponse(parts=[
                ToolCallPart(
                    tool_name="get_weather",
                    args={"city": "London"},
                    tool_call_id="call_abc"
                )
            ]),
        ]

        request = model._build_request(
            messages, None, self._create_request_params()
        )

        contents = request["request"]["contents"]
        assert len(contents) == 2
        model_content = contents[1]
        assert model_content["role"] == "model"
        func_call = model_content["parts"][0]["functionCall"]
        assert func_call["name"] == "get_weather"
        assert func_call["args"] == {"city": "London"}
        # First tool call should have thoughtSignature
        assert model_content["parts"][0]["thoughtSignature"] == "skip_thought_signature_validator"

    def test_build_request_multiple_tool_calls(self):
        """Test that only first tool call gets thoughtSignature."""
        model = self._create_model()
        messages = [
            ModelResponse(parts=[
                ToolCallPart(tool_name="tool1", args={}, tool_call_id="1"),
                ToolCallPart(tool_name="tool2", args={}, tool_call_id="2"),
            ]),
        ]

        request = model._build_request(
            messages, None, self._create_request_params()
        )

        parts = request["request"]["contents"][0]["parts"]
        assert len(parts) == 2
        # Only first should have thoughtSignature
        assert "thoughtSignature" in parts[0]
        assert "thoughtSignature" not in parts[1]


# =============================================================================
# Build Tools Tests
# =============================================================================


class TestBuildTools:
    """Test _build_tools method."""

    def test_build_tools_basic(self):
        """Test building basic tool definitions."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        tools = [
            ToolDefinition(
                name="get_weather",
                description="Get the weather for a city",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"}
                    }
                }
            )
        ]

        result = model._build_tools(tools)

        assert "functionDeclarations" in result
        assert len(result["functionDeclarations"]) == 1
        func = result["functionDeclarations"][0]
        assert func["name"] == "get_weather"
        assert func["description"] == "Get the weather for a city"
        assert "parametersJsonSchema" in func

    def test_build_tools_no_description(self):
        """Test building tool with no description."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        tools = [
            ToolDefinition(
                name="my_tool",
                description=None,
                parameters_json_schema=None
            )
        ]

        result = model._build_tools(tools)

        func = result["functionDeclarations"][0]
        assert func["name"] == "my_tool"
        assert func["description"] == ""  # Empty string for None
        assert "parametersJsonSchema" not in func

    def test_build_tools_multiple(self):
        """Test building multiple tools."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        tools = [
            ToolDefinition(name="tool1", description="First tool", parameters_json_schema=None),
            ToolDefinition(name="tool2", description="Second tool", parameters_json_schema=None),
        ]

        result = model._build_tools(tools)

        assert len(result["functionDeclarations"]) == 2
        assert result["functionDeclarations"][0]["name"] == "tool1"
        assert result["functionDeclarations"][1]["name"] == "tool2"


# =============================================================================
# Build Generation Config Tests
# =============================================================================


class TestBuildGenerationConfig:
    """Test _build_generation_config method.

    Note: ModelSettings is a TypedDict, so we use MagicMock to properly
    test attribute access since hasattr() doesn't work on TypedDict.
    """

    def test_build_generation_config_none(self):
        """Test with None model_settings."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        result = model._build_generation_config(None)

        assert result is None

    def test_build_generation_config_with_temperature(self):
        """Test with temperature setting."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        # Use MagicMock to simulate object with attributes
        settings = MagicMock()
        settings.temperature = 0.7
        settings.top_p = None
        settings.max_tokens = None
        result = model._build_generation_config(settings)

        assert result is not None
        assert result["temperature"] == 0.7

    def test_build_generation_config_with_top_p(self):
        """Test with top_p setting."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        settings = MagicMock()
        settings.temperature = None
        settings.top_p = 0.9
        settings.max_tokens = None
        result = model._build_generation_config(settings)

        assert result is not None
        assert result["topP"] == 0.9

    def test_build_generation_config_with_max_tokens(self):
        """Test with max_tokens setting."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        settings = MagicMock()
        settings.temperature = None
        settings.top_p = None
        settings.max_tokens = 1000
        result = model._build_generation_config(settings)

        assert result is not None
        assert result["maxOutputTokens"] == 1000

    def test_build_generation_config_empty_settings(self):
        """Test with empty model settings."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        settings = ModelSettings()  # TypedDict - hasattr won't find these
        result = model._build_generation_config(settings)

        # TypedDict doesn't work with hasattr, so returns None
        assert result is None

    def test_build_generation_config_all_settings(self):
        """Test with all settings combined."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        settings = MagicMock()
        settings.temperature = 0.5
        settings.top_p = 0.95
        settings.max_tokens = 2000
        result = model._build_generation_config(settings)

        assert result["temperature"] == 0.5
        assert result["topP"] == 0.95
        assert result["maxOutputTokens"] == 2000


# =============================================================================
# Parse Response Tests
# =============================================================================


class TestParseResponse:
    """Test _parse_response method."""

    def test_parse_response_text(self):
        """Test parsing response with text content."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        data = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [{"text": "Hello! How can I help?"}]
                    }
                }],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 5
                }
            }
        }

        response = model._parse_response(data)

        assert isinstance(response, ModelResponse)
        assert len(response.parts) == 1
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == "Hello! How can I help?"
        assert response.model_name == "gemini-pro"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 5

    def test_parse_response_function_call(self):
        """Test parsing response with function call."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        data = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "functionCall": {
                                "name": "get_weather",
                                "args": {"city": "London"}
                            }
                        }]
                    }
                }],
                "usageMetadata": {}
            }
        }

        response = model._parse_response(data)

        assert len(response.parts) == 1
        assert isinstance(response.parts[0], ToolCallPart)
        assert response.parts[0].tool_name == "get_weather"
        assert response.parts[0].args_as_dict() == {"city": "London"}

    def test_parse_response_mixed_parts(self):
        """Test parsing response with mixed text and function calls."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        data = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [
                            {"text": "Let me check the weather."},
                            {"functionCall": {"name": "get_weather", "args": {}}}
                        ]
                    }
                }],
                "usageMetadata": {}
            }
        }

        response = model._parse_response(data)

        assert len(response.parts) == 2
        assert isinstance(response.parts[0], TextPart)
        assert isinstance(response.parts[1], ToolCallPart)

    def test_parse_response_no_wrapper(self):
        """Test parsing response without outer 'response' wrapper."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        # Direct format (not wrapped in "response")
        data = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Direct response"}]
                }
            }],
            "usageMetadata": {}
        }

        response = model._parse_response(data)

        assert response.parts[0].content == "Direct response"

    def test_parse_response_no_candidates_raises(self):
        """Test that empty candidates raises RuntimeError."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        data = {"response": {"candidates": []}}

        with pytest.raises(RuntimeError, match="No candidates in response"):
            model._parse_response(data)

    def test_parse_response_missing_candidates_raises(self):
        """Test that missing candidates key raises RuntimeError."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        data = {"response": {}}

        with pytest.raises(RuntimeError, match="No candidates in response"):
            model._parse_response(data)

    def test_parse_response_empty_usage(self):
        """Test parsing response with missing usage metadata."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        data = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Response"}]
                }
            }]
            # No usageMetadata
        }

        response = model._parse_response(data)

        assert response.usage.input_tokens == 0
        assert response.usage.output_tokens == 0


# =============================================================================
# Request Method Tests
# =============================================================================


class TestRequest:
    """Test the async request method."""

    async def test_request_success(self):
        """Test successful request."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [{"text": "Hello!"}]
                    }
                }],
                "usageMetadata": {
                    "promptTokenCount": 5,
                    "candidatesTokenCount": 3
                }
            }
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            messages = [ModelRequest(parts=[UserPromptPart(content="Hi")])]
            params = ModelRequestParameters(
                function_tools=[],
            )

            response = await model.request(messages, None, params)

        assert isinstance(response, ModelResponse)
        assert response.parts[0].content == "Hello!"
        assert response.usage.input_tokens == 5
        assert response.usage.output_tokens == 3

    async def test_request_api_error(self):
        """Test request with API error."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            messages = [ModelRequest(parts=[UserPromptPart(content="Hi")])]
            params = ModelRequestParameters(
                function_tools=[],
            )

            with pytest.raises(RuntimeError, match="Code Assist API error 500"):
                await model.request(messages, None, params)

    async def test_request_unauthorized(self):
        """Test request with 401 error."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="bad_token",
            project_id="project",
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            messages = [ModelRequest(parts=[UserPromptPart(content="Hi")])]
            params = ModelRequestParameters(
                function_tools=[],
            )

            with pytest.raises(RuntimeError, match="Code Assist API error 401"):
                await model.request(messages, None, params)

    async def test_request_with_tools(self):
        """Test request with tool definitions."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [{"text": "Using tool"}]
                    }
                }],
                "usageMetadata": {}
            }
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            messages = [ModelRequest(parts=[UserPromptPart(content="Hi")])]
            tools = [
                ToolDefinition(
                    name="my_tool",
                    description="A test tool",
                    parameters_json_schema={"type": "object"}
                )
            ]
            params = ModelRequestParameters(
                function_tools=tools,
            )

            await model.request(messages, None, params)

            # Verify the request body includes tools
            call_args = mock_client.post.call_args
            request_body = call_args[1]["json"]
            assert "tools" in request_body["request"]

    async def test_request_url_construction(self):
        """Test that request URL is constructed correctly."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
            api_base_url="https://custom.api.com",
            api_version="v2",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
            "usageMetadata": {}
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            messages = [ModelRequest(parts=[UserPromptPart(content="Hi")])]
            params = ModelRequestParameters(
                function_tools=[],
            )

            await model.request(messages, None, params)

            call_args = mock_client.post.call_args
            url = call_args[0][0]
            assert url == "https://custom.api.com/v2:generateContent"


# =============================================================================
# Request Stream Tests
# =============================================================================


class TestRequestStream:
    """Test the async request_stream method."""

    async def test_request_stream_success(self):
        """Test successful streaming request."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200

        # Create a proper async context manager for stream
        class MockStreamContext:
            async def __aenter__(self):
                return mock_response
            async def __aexit__(self, *args):
                pass

        mock_client = MagicMock()
        mock_client.stream.return_value = MockStreamContext()

        # Create async context manager for client
        class MockClientContext:
            async def __aenter__(self):
                return mock_client
            async def __aexit__(self, *args):
                pass

        with patch("httpx.AsyncClient", return_value=MockClientContext()):
            messages = [ModelRequest(parts=[UserPromptPart(content="Hi")])]
            params = ModelRequestParameters(
                function_tools=[],
            )

            async with model.request_stream(messages, None, params) as stream:
                assert isinstance(stream, StreamedResponse)

    async def test_request_stream_error(self):
        """Test streaming request with API error."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        mock_response = MagicMock()
        mock_response.status_code = 500

        async def mock_aread():
            return b"Server Error"
        mock_response.aread = mock_aread

        class MockStreamContext:
            async def __aenter__(self):
                return mock_response
            async def __aexit__(self, *args):
                pass

        mock_client = MagicMock()
        mock_client.stream.return_value = MockStreamContext()

        class MockClientContext:
            async def __aenter__(self):
                return mock_client
            async def __aexit__(self, *args):
                pass

        with patch("httpx.AsyncClient", return_value=MockClientContext()):
            messages = [ModelRequest(parts=[UserPromptPart(content="Hi")])]
            params = ModelRequestParameters(
                function_tools=[],
            )

            with pytest.raises(RuntimeError, match="Code Assist API error 500"):
                async with model.request_stream(messages, None, params):
                    pass

    async def test_request_stream_url_construction(self):
        """Test that streaming URL includes SSE parameter."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200

        class MockStreamContext:
            async def __aenter__(self):
                return mock_response
            async def __aexit__(self, *args):
                pass

        captured_url = []

        def mock_stream(method, url, **kwargs):
            captured_url.append(url)
            return MockStreamContext()

        mock_client = MagicMock()
        mock_client.stream = mock_stream

        class MockClientContext:
            async def __aenter__(self):
                return mock_client
            async def __aexit__(self, *args):
                pass

        with patch("httpx.AsyncClient", return_value=MockClientContext()):
            messages = [ModelRequest(parts=[UserPromptPart(content="Hi")])]
            params = ModelRequestParameters(
                function_tools=[],
            )

            async with model.request_stream(messages, None, params):
                pass

            assert len(captured_url) == 1
            assert "streamGenerateContent" in captured_url[0]
            assert "alt=sse" in captured_url[0]


# =============================================================================
# StreamedResponse Tests
# =============================================================================


class TestStreamedResponse:
    """Test the StreamedResponse class."""

    def test_construction(self):
        """Test StreamedResponse construction."""
        mock_response = MagicMock()
        stream = StreamedResponse(mock_response, "gemini-pro")

        assert stream.model_name() == "gemini-pro"
        assert stream._usage is None
        assert isinstance(stream.timestamp(), datetime)

    def test_model_name(self):
        """Test model_name method."""
        mock_response = MagicMock()
        stream = StreamedResponse(mock_response, "custom-model")

        assert stream.model_name() == "custom-model"

    def test_timestamp_is_utc(self):
        """Test that timestamp is in UTC."""
        mock_response = MagicMock()
        stream = StreamedResponse(mock_response, "model")

        ts = stream.timestamp()
        assert ts.tzinfo == timezone.utc

    def test_usage_default(self):
        """Test usage returns empty RequestUsage when not set."""
        mock_response = MagicMock()
        stream = StreamedResponse(mock_response, "model")

        usage = stream.usage()
        assert isinstance(usage, RequestUsage)
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    def test_usage_after_setting(self):
        """Test usage returns correct values when set."""
        mock_response = MagicMock()
        stream = StreamedResponse(mock_response, "model")
        stream._usage = RequestUsage(input_tokens=100, output_tokens=50)

        usage = stream.usage()
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50

    async def test_iter_chunks_empty(self):
        """Test iterating over empty response."""
        mock_response = MagicMock()
        mock_response.aiter_lines.return_value = AsyncIteratorMock([])

        stream = StreamedResponse(mock_response, "model")

        chunks = []
        async for chunk in stream:
            chunks.append(chunk)

        assert chunks == []

    async def test_iter_chunks_with_text(self):
        """Test iterating over response with text chunks."""
        lines = [
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}}',
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": " World"}]}}]}}',
            'data: [DONE]',
        ]

        mock_response = MagicMock()
        mock_response.aiter_lines.return_value = AsyncIteratorMock(lines)

        stream = StreamedResponse(mock_response, "model")

        chunks = []
        async for chunk in stream:
            chunks.append(chunk)

        assert chunks == ["Hello", " World"]

    async def test_iter_chunks_extracts_usage(self):
        """Test that usage metadata is extracted during iteration."""
        lines = [
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "Hi"}]}}], "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}}',
            'data: [DONE]',
        ]

        mock_response = MagicMock()
        mock_response.aiter_lines.return_value = AsyncIteratorMock(lines)

        stream = StreamedResponse(mock_response, "model")

        async for _ in stream:
            pass

        assert stream._usage is not None
        assert stream._usage.input_tokens == 10
        assert stream._usage.output_tokens == 5

    async def test_iter_chunks_handles_malformed_json(self):
        """Test that malformed JSON is skipped."""
        lines = [
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "Good"}]}}]}}',
            'data: {malformed json',
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": " Chunk"}]}}]}}',
            'data: [DONE]',
        ]

        mock_response = MagicMock()
        mock_response.aiter_lines.return_value = AsyncIteratorMock(lines)

        stream = StreamedResponse(mock_response, "model")

        chunks = []
        async for chunk in stream:
            chunks.append(chunk)

        assert chunks == ["Good", " Chunk"]

    async def test_iter_chunks_ignores_non_data_lines(self):
        """Test that non-data lines are ignored."""
        lines = [
            'event: message',
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "Text"}]}}]}}',
            '',  # Empty line
            'data: [DONE]',
        ]

        mock_response = MagicMock()
        mock_response.aiter_lines.return_value = AsyncIteratorMock(lines)

        stream = StreamedResponse(mock_response, "model")

        chunks = []
        async for chunk in stream:
            chunks.append(chunk)

        assert chunks == ["Text"]

    async def test_get_response_parts_text(self):
        """Test get_response_parts with text content."""
        lines = [
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "Hello "}]}}]}}',
            'data: {"response": {"candidates": [{"content": {"parts": [{"text": "World!"}]}}]}}',
            'data: [DONE]',
        ]

        mock_response = MagicMock()
        mock_response.aiter_lines.return_value = AsyncIteratorMock(lines)

        stream = StreamedResponse(mock_response, "model")

        parts = await stream.get_response_parts()

        assert len(parts) == 1
        assert isinstance(parts[0], TextPart)
        assert parts[0].content == "Hello World!"

    async def test_get_response_parts_empty(self):
        """Test get_response_parts with no content."""
        lines = ['data: [DONE]']

        mock_response = MagicMock()
        mock_response.aiter_lines.return_value = AsyncIteratorMock(lines)

        stream = StreamedResponse(mock_response, "model")

        parts = await stream.get_response_parts()

        assert parts == []


# =============================================================================
# Integration Tests
# =============================================================================


class TestBuildRequestWithTools:
    """Test _build_request with tool definitions in request params."""

    def test_request_includes_tools(self):
        """Test that tools are included in request when provided."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        messages = [ModelRequest(parts=[UserPromptPart(content="Hi")])]
        tools = [
            ToolDefinition(
                name="search",
                description="Search the web",
                parameters_json_schema={"type": "object"}
            )
        ]
        params = ModelRequestParameters(
            function_tools=tools,
        )

        request = model._build_request(messages, None, params)

        assert "tools" in request["request"]
        assert len(request["request"]["tools"]) == 1

    def test_request_with_generation_config(self):
        """Test that generation config is included."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        messages = [ModelRequest(parts=[UserPromptPart(content="Hi")])]
        # Use MagicMock since ModelSettings is a TypedDict and hasattr won't work
        settings = MagicMock()
        settings.temperature = 0.5
        settings.top_p = None
        settings.max_tokens = None
        params = ModelRequestParameters(
            function_tools=[],
        )

        request = model._build_request(messages, settings, params)

        assert "generationConfig" in request["request"]
        assert request["request"]["generationConfig"]["temperature"] == 0.5


class TestToolReturnSerialization:
    """Test various content types in ToolReturnPart."""

    def test_tool_return_with_list(self):
        """Test tool return with list content."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        messages = [
            ModelRequest(parts=[
                ToolReturnPart(
                    tool_name="get_items",
                    content=["item1", "item2", "item3"],
                    tool_call_id="call_123"
                )
            ])
        ]

        params = ModelRequestParameters(
            function_tools=[],
        )

        request = model._build_request(messages, None, params)

        content = request["request"]["contents"][0]
        result = content["parts"][0]["functionResponse"]["response"]["result"]
        assert json.loads(result) == ["item1", "item2", "item3"]

    def test_tool_return_with_int(self):
        """Test tool return with integer content."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        messages = [
            ModelRequest(parts=[
                ToolReturnPart(
                    tool_name="count",
                    content=42,
                    tool_call_id="call_123"
                )
            ])
        ]

        params = ModelRequestParameters(
            function_tools=[],
        )

        request = model._build_request(messages, None, params)

        content = request["request"]["contents"][0]
        result = content["parts"][0]["functionResponse"]["response"]["result"]
        assert result == 42

    def test_tool_return_with_bool(self):
        """Test tool return with boolean content."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        messages = [
            ModelRequest(parts=[
                ToolReturnPart(
                    tool_name="is_valid",
                    content=True,
                    tool_call_id="call_123"
                )
            ])
        ]

        params = ModelRequestParameters(
            function_tools=[],
        )

        request = model._build_request(messages, None, params)

        content = request["request"]["contents"][0]
        result = content["parts"][0]["functionResponse"]["response"]["result"]
        assert result is True

    def test_tool_return_with_none(self):
        """Test tool return with None content."""
        model = GeminiCodeAssistModel(
            model_name="gemini-pro",
            access_token="token",
            project_id="project",
        )

        messages = [
            ModelRequest(parts=[
                ToolReturnPart(
                    tool_name="void_func",
                    content=None,
                    tool_call_id="call_123"
                )
            ])
        ]

        params = ModelRequestParameters(
            function_tools=[],
        )

        request = model._build_request(messages, None, params)

        content = request["request"]["contents"][0]
        result = content["parts"][0]["functionResponse"]["response"]["result"]
        assert result is None
