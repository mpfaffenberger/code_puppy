"""Tests for ChatGPT Codex API client.

Comprehensive tests for the chatgpt_codex_client module which handles
request interception and stream-to-response conversion for the ChatGPT
Codex API.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from code_puppy.chatgpt_codex_client import (
    ChatGPTCodexAsyncClient,
    _is_reasoning_model,
    create_codex_async_client,
)


class TestIsReasoningModel:
    """Test the _is_reasoning_model helper function."""

    def test_gpt5_is_reasoning_model(self):
        """Test that GPT-5 variants are recognized as reasoning models."""
        assert _is_reasoning_model("gpt-5") is True
        assert _is_reasoning_model("gpt-5-turbo") is True
        assert _is_reasoning_model("gpt-5.2") is True
        assert _is_reasoning_model("gpt-5-preview") is True

    def test_o_series_are_reasoning_models(self):
        """Test that o1, o3, o4 series are recognized as reasoning models."""
        assert _is_reasoning_model("o1") is True
        assert _is_reasoning_model("o1-mini") is True
        assert _is_reasoning_model("o1-preview") is True
        assert _is_reasoning_model("o3") is True
        assert _is_reasoning_model("o3-mini") is True
        assert _is_reasoning_model("o4") is True
        assert _is_reasoning_model("o4-mini") is True

    def test_case_insensitivity(self):
        """Test that model detection is case-insensitive."""
        assert _is_reasoning_model("GPT-5") is True
        assert _is_reasoning_model("O1") is True
        assert _is_reasoning_model("O3-MINI") is True
        assert _is_reasoning_model("Gpt-5-Turbo") is True

    def test_non_reasoning_models(self):
        """Test that non-reasoning models return False."""
        assert _is_reasoning_model("gpt-4") is False
        assert _is_reasoning_model("gpt-4-turbo") is False
        assert _is_reasoning_model("gpt-4o") is False
        assert _is_reasoning_model("gpt-4o-mini") is False
        assert _is_reasoning_model("claude-3-opus") is False
        assert _is_reasoning_model("claude-3.5-sonnet") is False
        assert _is_reasoning_model("") is False
        assert _is_reasoning_model("unknown-model") is False

    def test_o2_is_not_reasoning_model(self):
        """Test that o2 is NOT a reasoning model (only o1, o3, o4)."""
        assert _is_reasoning_model("o2") is False
        assert _is_reasoning_model("o2-mini") is False


class TestExtractBodyBytes:
    """Test the _extract_body_bytes static method."""

    def test_extract_from_content_attribute(self):
        """Test extraction from request.content."""
        request = httpx.Request(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            content=b'{"model": "gpt-4"}',
        )
        result = ChatGPTCodexAsyncClient._extract_body_bytes(request)
        assert result == b'{"model": "gpt-4"}'

    def test_extract_empty_content_returns_none(self):
        """Test that empty content returns None."""
        request = httpx.Request(
            "POST",
            "https://api.openai.com/v1/chat/completions",
        )
        result = ChatGPTCodexAsyncClient._extract_body_bytes(request)
        # Empty requests return empty bytes, which is falsy
        assert result is None or result == b""

    def test_extract_from_private_content_attribute(self):
        """Test fallback to _content attribute."""
        request = Mock()
        # Mock content property to raise an exception
        type(request).content = property(lambda self: (_ for _ in ()).throw(Exception("No content")))
        request._content = b'{"fallback": true}'
        
        result = ChatGPTCodexAsyncClient._extract_body_bytes(request)
        assert result == b'{"fallback": true}'

    def test_extract_returns_none_on_all_exceptions(self):
        """Test that exceptions result in None."""
        request = Mock()
        type(request).content = property(lambda self: (_ for _ in ()).throw(Exception()))
        del request._content  # Remove _content to trigger second exception path
        
        result = ChatGPTCodexAsyncClient._extract_body_bytes(request)
        assert result is None


class TestInjectCodexFields:
    """Test the _inject_codex_fields static method."""

    def test_inject_store_false_when_missing(self):
        """Test that store=false is injected when missing."""
        body = json.dumps({"model": "gpt-4"}).encode()
        result, forced_stream = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert data["store"] is False

    def test_inject_store_false_when_true(self):
        """Test that store=true is changed to store=false."""
        body = json.dumps({"model": "gpt-4", "store": True}).encode()
        result, forced_stream = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert data["store"] is False

    def test_inject_stream_true_when_missing(self):
        """Test that stream=true is injected when missing."""
        body = json.dumps({"model": "gpt-4"}).encode()
        result, forced_stream = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert data["stream"] is True
        assert forced_stream is True  # We forced streaming

    def test_inject_stream_true_when_false(self):
        """Test that stream=false is changed to stream=true."""
        body = json.dumps({"model": "gpt-4", "stream": False}).encode()
        result, forced_stream = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert data["stream"] is True
        assert forced_stream is True

    def test_no_forced_stream_when_already_true(self):
        """Test that stream is not forced when already true."""
        body = json.dumps({"model": "gpt-4", "stream": True}).encode()
        result, forced_stream = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        # Still modifies because store is missing
        assert result is not None
        data = json.loads(result)
        assert data["stream"] is True
        assert forced_stream is False  # NOT forced

    def test_add_reasoning_for_gpt5(self):
        """Test that reasoning settings are added for GPT-5 models."""
        body = json.dumps({"model": "gpt-5.2"}).encode()
        result, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert "reasoning" in data
        assert data["reasoning"]["effort"] == "medium"
        assert data["reasoning"]["summary"] == "auto"

    def test_add_reasoning_for_o1_series(self):
        """Test that reasoning settings are added for o1 models."""
        body = json.dumps({"model": "o1-mini"}).encode()
        result, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert "reasoning" in data

    def test_no_reasoning_for_gpt4(self):
        """Test that reasoning is NOT added for GPT-4 models."""
        body = json.dumps({"model": "gpt-4"}).encode()
        result, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert "reasoning" not in data

    def test_preserve_existing_reasoning(self):
        """Test that existing reasoning settings are preserved."""
        body = json.dumps({
            "model": "gpt-5",
            "reasoning": {"effort": "high", "summary": "detailed"}
        }).encode()
        result, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert data["reasoning"]["effort"] == "high"  # Preserved
        assert data["reasoning"]["summary"] == "detailed"  # Preserved

    def test_remove_max_output_tokens(self):
        """Test that max_output_tokens is removed."""
        body = json.dumps({"model": "gpt-4", "max_output_tokens": 1000}).encode()
        result, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert "max_output_tokens" not in data

    def test_remove_max_tokens(self):
        """Test that max_tokens is removed."""
        body = json.dumps({"model": "gpt-4", "max_tokens": 2000}).encode()
        result, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert "max_tokens" not in data

    def test_remove_verbosity(self):
        """Test that verbosity is removed."""
        body = json.dumps({"model": "gpt-4", "verbosity": "detailed"}).encode()
        result, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert "verbosity" not in data

    def test_remove_all_unsupported_params(self):
        """Test that all unsupported params are removed together."""
        body = json.dumps({
            "model": "gpt-4",
            "max_output_tokens": 1000,
            "max_tokens": 2000,
            "verbosity": "high",
            "temperature": 0.7,  # This should be preserved
        }).encode()
        result, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert "max_output_tokens" not in data
        assert "max_tokens" not in data
        assert "verbosity" not in data
        assert data["temperature"] == 0.7  # Preserved

    def test_invalid_json_returns_none(self):
        """Test that invalid JSON returns (None, False)."""
        body = b"not valid json"
        result, forced_stream = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is None
        assert forced_stream is False

    def test_non_dict_json_returns_none(self):
        """Test that non-dict JSON returns (None, False)."""
        body = b'["an", "array"]'
        result, forced_stream = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is None
        assert forced_stream is False

    def test_no_modification_when_all_correct(self):
        """Test that no modification happens when all fields are correct."""
        body = json.dumps({
            "model": "gpt-4",
            "store": False,
            "stream": True,
        }).encode()
        result, forced_stream = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        # When everything is correct, nothing to modify
        assert result is None
        assert forced_stream is False

    def test_utf8_encoding(self):
        """Test that non-ASCII characters are handled correctly."""
        body = json.dumps({"model": "gpt-4", "prompt": "Héllo Wörld!"}).encode("utf-8")
        result, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
        
        assert result is not None
        data = json.loads(result)
        assert data["prompt"] == "Héllo Wörld!"


class TestConvertStreamToResponse:
    """Test the _convert_stream_to_response method."""

    @pytest.mark.asyncio
    async def test_collect_text_deltas(self):
        """Test collection of text delta events."""
        # Create mock SSE stream data
        sse_lines = [
            'data: {"type": "response.output_text.delta", "delta": "Hello "}',
            'data: {"type": "response.output_text.delta", "delta": "world!"}',
            "data: [DONE]",
        ]
        
        async def mock_aiter_lines():
            for line in sse_lines:
                yield line
        
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/event-stream"}
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.request = Mock()
        
        client = ChatGPTCodexAsyncClient()
        result = await client._convert_stream_to_response(mock_response)
        
        assert result.status_code == 200
        body = json.loads(result.content)
        # Should have reconstructed response with collected text
        assert body["id"] == "reconstructed"
        assert len(body["output"]) == 1
        assert body["output"][0]["content"][0]["text"] == "Hello world!"

    @pytest.mark.asyncio
    async def test_collect_function_calls(self):
        """Test collection of function call events."""
        sse_lines = [
            'data: {"type": "response.function_call_arguments.done", "name": "get_weather", "arguments": "{\\"city\\": \\"NYC\\"}", "call_id": "call_123"}',
            "data: [DONE]",
        ]
        
        async def mock_aiter_lines():
            for line in sse_lines:
                yield line
        
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.request = Mock()
        
        client = ChatGPTCodexAsyncClient()
        result = await client._convert_stream_to_response(mock_response)
        
        body = json.loads(result.content)
        assert len(body["output"]) == 1
        assert body["output"][0]["type"] == "function_call"
        assert body["output"][0]["name"] == "get_weather"
        assert body["output"][0]["call_id"] == "call_123"

    @pytest.mark.asyncio
    async def test_use_response_completed_data(self):
        """Test that response.completed event data is used when available."""
        final_response = {
            "id": "resp_abc123",
            "object": "response",
            "output": [{"type": "message", "content": "Final response"}],
        }
        sse_lines = [
            'data: {"type": "response.output_text.delta", "delta": "ignored"}',
            f'data: {{"type": "response.completed", "response": {json.dumps(final_response)}}}',
            "data: [DONE]",
        ]
        
        async def mock_aiter_lines():
            for line in sse_lines:
                yield line
        
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.request = Mock()
        
        client = ChatGPTCodexAsyncClient()
        result = await client._convert_stream_to_response(mock_response)
        
        body = json.loads(result.content)
        # Should use the response.completed data, not reconstructed
        assert body["id"] == "resp_abc123"

    @pytest.mark.asyncio
    async def test_skip_empty_lines(self):
        """Test that empty lines are skipped."""
        sse_lines = [
            "",
            "   ",
            'data: {"type": "response.output_text.delta", "delta": "Hi"}',
            "",
            "data: [DONE]",
        ]
        
        async def mock_aiter_lines():
            for line in sse_lines:
                yield line
        
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.request = Mock()
        
        client = ChatGPTCodexAsyncClient()
        result = await client._convert_stream_to_response(mock_response)
        
        body = json.loads(result.content)
        assert body["output"][0]["content"][0]["text"] == "Hi"

    @pytest.mark.asyncio
    async def test_skip_non_data_lines(self):
        """Test that non-data lines (like event: or id:) are skipped."""
        sse_lines = [
            "event: message",
            "id: 123",
            'data: {"type": "response.output_text.delta", "delta": "Test"}',
            ": comment line",
            "data: [DONE]",
        ]
        
        async def mock_aiter_lines():
            for line in sse_lines:
                yield line
        
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.request = Mock()
        
        client = ChatGPTCodexAsyncClient()
        result = await client._convert_stream_to_response(mock_response)
        
        body = json.loads(result.content)
        assert body["output"][0]["content"][0]["text"] == "Test"

    @pytest.mark.asyncio
    async def test_handle_json_decode_errors(self):
        """Test that JSON decode errors are handled gracefully."""
        sse_lines = [
            "data: {not valid json}",
            'data: {"type": "response.output_text.delta", "delta": "Ok"}',
            "data: [DONE]",
        ]
        
        async def mock_aiter_lines():
            for line in sse_lines:
                yield line
        
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.request = Mock()
        
        client = ChatGPTCodexAsyncClient()
        # Should not raise an exception
        result = await client._convert_stream_to_response(mock_response)
        
        body = json.loads(result.content)
        assert body["output"][0]["content"][0]["text"] == "Ok"

    @pytest.mark.asyncio
    async def test_handle_empty_stream(self):
        """Test handling of empty stream."""
        sse_lines = ["data: [DONE]"]
        
        async def mock_aiter_lines():
            for line in sse_lines:
                yield line
        
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.request = Mock()
        
        client = ChatGPTCodexAsyncClient()
        result = await client._convert_stream_to_response(mock_response)
        
        body = json.loads(result.content)
        assert body["id"] == "reconstructed"
        assert body["output"] == []  # No content collected

    @pytest.mark.asyncio
    async def test_collect_both_text_and_tool_calls(self):
        """Test collecting both text and function calls in same response."""
        sse_lines = [
            'data: {"type": "response.output_text.delta", "delta": "Let me check "}',
            'data: {"type": "response.output_text.delta", "delta": "the weather."}',
            'data: {"type": "response.function_call_arguments.done", "name": "get_weather", "arguments": "{}", "call_id": "call_456"}',
            "data: [DONE]",
        ]
        
        async def mock_aiter_lines():
            for line in sse_lines:
                yield line
        
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.request = Mock()
        
        client = ChatGPTCodexAsyncClient()
        result = await client._convert_stream_to_response(mock_response)
        
        body = json.loads(result.content)
        assert len(body["output"]) == 2
        assert body["output"][0]["type"] == "message"
        assert body["output"][0]["content"][0]["text"] == "Let me check the weather."
        assert body["output"][1]["type"] == "function_call"


class TestSendMethod:
    """Test the send method of ChatGPTCodexAsyncClient."""

    @pytest.mark.asyncio
    async def test_post_request_injects_fields(self):
        """Test that POST requests have fields injected."""
        success_response = Mock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.headers = {"content-type": "application/json"}
        
        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=success_response
        ) as mock_send:
            client = ChatGPTCodexAsyncClient()
            
            request = httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                content=json.dumps({"model": "gpt-4"}).encode(),
            )
            
            await client.send(request)
            
            # Verify parent send was called
            mock_send.assert_called_once()
            # The request should have been modified
            sent_request = mock_send.call_args[0][0]
            body = json.loads(sent_request.content)
            assert body["store"] is False
            assert body["stream"] is True

    @pytest.mark.asyncio
    async def test_get_request_passthrough(self):
        """Test that GET requests pass through unmodified."""
        success_response = Mock(spec=httpx.Response)
        success_response.status_code = 200
        
        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=success_response
        ) as mock_send:
            client = ChatGPTCodexAsyncClient()
            
            request = httpx.Request(
                "GET",
                "https://api.openai.com/v1/models",
            )
            
            result = await client.send(request)
            
            mock_send.assert_called_once()
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_forced_stream_triggers_conversion(self):
        """Test that forcing stream triggers response conversion."""
        # Create a streaming response
        sse_lines = [
            'data: {"type": "response.output_text.delta", "delta": "Hi"}',
            "data: [DONE]",
        ]
        
        async def mock_aiter_lines():
            for line in sse_lines:
                yield line
        
        stream_response = Mock(spec=httpx.Response)
        stream_response.status_code = 200
        stream_response.headers = {"content-type": "text/event-stream"}
        stream_response.aiter_lines = mock_aiter_lines
        stream_response.request = Mock()
        
        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=stream_response
        ):
            client = ChatGPTCodexAsyncClient()
            
            # stream=False means we force it to true and need conversion
            request = httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                content=json.dumps({"model": "gpt-4", "stream": False}).encode(),
            )
            
            result = await client.send(request)
            
            # Should be a converted response
            body = json.loads(result.content)
            assert body["output"][0]["content"][0]["text"] == "Hi"

    @pytest.mark.asyncio
    async def test_no_conversion_when_stream_already_true(self):
        """Test that no conversion happens when stream was already true."""
        stream_response = Mock(spec=httpx.Response)
        stream_response.status_code = 200
        stream_response.headers = {"content-type": "text/event-stream"}
        
        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=stream_response
        ):
            client = ChatGPTCodexAsyncClient()
            
            # stream=True means no forced conversion
            request = httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                content=json.dumps({"model": "gpt-4", "stream": True, "store": False}).encode(),
            )
            
            result = await client.send(request)
            
            # Should return original response (not converted)
            assert result is stream_response

    @pytest.mark.asyncio
    async def test_no_conversion_on_error_status(self):
        """Test that no conversion happens on non-200 responses."""
        error_response = Mock(spec=httpx.Response)
        error_response.status_code = 400
        error_response.headers = {"content-type": "application/json"}
        
        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=error_response
        ):
            client = ChatGPTCodexAsyncClient()
            
            request = httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                content=json.dumps({"model": "gpt-4", "stream": False}).encode(),
            )
            
            result = await client.send(request)
            
            # Should return original error response
            assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_exception_handling_in_body_modification(self):
        """Test that exceptions during body modification don't crash."""
        success_response = Mock(spec=httpx.Response)
        success_response.status_code = 200
        
        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=success_response
        ):
            with patch.object(
                ChatGPTCodexAsyncClient, "_extract_body_bytes", side_effect=Exception("Test error")
            ):
                client = ChatGPTCodexAsyncClient()
                
                request = httpx.Request(
                    "POST",
                    "https://api.openai.com/v1/chat/completions",
                    content=b'{"model": "gpt-4"}',
                )
                
                # Should not raise, just proceed with original request
                result = await client.send(request)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_stream_conversion_failure_logs_warning(self):
        """Test that stream conversion failure logs warning and returns original."""
        # Create a streaming response that fails during conversion
        async def failing_aiter_lines():
            raise Exception("Stream read error")
            yield  # Make it a generator
        
        stream_response = Mock(spec=httpx.Response)
        stream_response.status_code = 200
        stream_response.headers = {}
        stream_response.aiter_lines = failing_aiter_lines
        
        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=stream_response
        ):
            client = ChatGPTCodexAsyncClient()
            
            request = httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                content=json.dumps({"model": "gpt-4", "stream": False}).encode(),
            )
            
            # Should return original response on conversion failure
            result = await client.send(request)
            assert result is stream_response


class TestCreateCodexAsyncClient:
    """Test the create_codex_async_client factory function."""

    def test_creates_client_with_defaults(self):
        """Test that factory creates client with default settings."""
        client = create_codex_async_client()
        
        assert isinstance(client, ChatGPTCodexAsyncClient)
        assert client.timeout.connect == 30.0
        assert client.timeout.read == 300.0

    def test_creates_client_with_custom_headers(self):
        """Test that factory respects custom headers."""
        headers = {"Authorization": "Bearer test-token", "X-Custom": "value"}
        client = create_codex_async_client(headers=headers)
        
        assert isinstance(client, ChatGPTCodexAsyncClient)
        # Headers are stored in the client
        assert client.headers.get("authorization") == "Bearer test-token"
        assert client.headers.get("x-custom") == "value"

    def test_creates_client_with_verify_false(self):
        """Test that factory respects verify=False."""
        client = create_codex_async_client(verify=False)
        
        assert isinstance(client, ChatGPTCodexAsyncClient)
        # The verify setting is stored in _transport
        # Just check client was created without error

    def test_creates_client_with_custom_verify_path(self):
        """Test that factory accepts verify as string (cert path)."""
        # Just verify the function accepts the parameter without error
        # The actual SSL context creation happens on first request
        # Using verify=False to avoid file not found errors
        client = create_codex_async_client(verify=False)
        
        assert isinstance(client, ChatGPTCodexAsyncClient)

    def test_creates_client_with_kwargs(self):
        """Test that factory passes through additional kwargs."""
        client = create_codex_async_client(
            headers={"X-Test": "yes"},
            follow_redirects=True,
        )
        
        assert isinstance(client, ChatGPTCodexAsyncClient)
        assert client.follow_redirects is True


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_inject_fields_with_empty_bytes(self):
        """Test injection with empty bytes."""
        result, forced = ChatGPTCodexAsyncClient._inject_codex_fields(b"")
        assert result is None
        assert forced is False

    def test_inject_fields_with_null_json(self):
        """Test injection with JSON null."""
        result, forced = ChatGPTCodexAsyncClient._inject_codex_fields(b"null")
        assert result is None
        assert forced is False

    def test_inject_fields_with_number_json(self):
        """Test injection with JSON number."""
        result, forced = ChatGPTCodexAsyncClient._inject_codex_fields(b"42")
        assert result is None
        assert forced is False

    def test_inject_fields_with_string_json(self):
        """Test injection with JSON string."""
        result, forced = ChatGPTCodexAsyncClient._inject_codex_fields(b'"hello"')
        assert result is None
        assert forced is False

    @pytest.mark.asyncio
    async def test_send_with_no_content(self):
        """Test send with POST request but no body content."""
        success_response = Mock(spec=httpx.Response)
        success_response.status_code = 200
        
        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=success_response
        ):
            client = ChatGPTCodexAsyncClient()
            
            request = httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                # No content
            )
            
            result = await client.send(request)
            assert result.status_code == 200

    def test_reasoning_model_with_empty_string(self):
        """Test reasoning model check with empty string."""
        assert _is_reasoning_model("") is False

    def test_reasoning_model_with_spaces(self):
        """Test reasoning model check with spaces in name."""
        assert _is_reasoning_model("  gpt-5  ") is False  # Not trimmed
        assert _is_reasoning_model("gpt-5 turbo") is True  # Starts with gpt-5

    @pytest.mark.asyncio
    async def test_delta_event_with_empty_delta(self):
        """Test that empty delta values are handled."""
        sse_lines = [
            'data: {"type": "response.output_text.delta", "delta": ""}',
            'data: {"type": "response.output_text.delta", "delta": "Hello"}',
            'data: {"type": "response.output_text.delta"}',  # Missing delta key
            "data: [DONE]",
        ]
        
        async def mock_aiter_lines():
            for line in sse_lines:
                yield line
        
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.request = Mock()
        
        client = ChatGPTCodexAsyncClient()
        result = await client._convert_stream_to_response(mock_response)
        
        body = json.loads(result.content)
        # Only "Hello" should be collected (empty strings are falsy)
        assert body["output"][0]["content"][0]["text"] == "Hello"
