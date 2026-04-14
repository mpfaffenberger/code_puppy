"""Tests for the reasoning_opaque round-trip interceptor.

Verifies that reasoning_client.py correctly:
- Captures reasoning_opaque from streaming SSE responses
- Captures reasoning_opaque from non-streaming responses
- Injects reasoning_opaque into outgoing request bodies
- Handles edge cases gracefully (malformed JSON, missing fields, etc.)
"""

from __future__ import annotations

import json

import httpx
import pytest

from code_puppy.plugins.copilot_auth.reasoning_client import (
    _MAX_CACHE_ENTRIES,
    _OpaqueCapturingStream,
    _capture_from_content,
    _inject_opaque_into_request,
    _strip_all_reasoning_fields,
    _text_key,
    patch_client_for_reasoning_opaque,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse_line(data: dict) -> bytes:
    return f"data: {json.dumps(data)}\n\n".encode()


def _sse_done() -> bytes:
    return b"data: [DONE]\n\n"


def _make_streaming_event(
    reasoning_text: str | None = None,
    reasoning_opaque: str | None = None,
    finish_reason: str | None = None,
) -> dict:
    delta: dict = {}
    if reasoning_text is not None:
        delta["reasoning_text"] = reasoning_text
    if reasoning_opaque is not None:
        delta["reasoning_opaque"] = reasoning_opaque
    choice: dict = {"delta": delta, "index": 0}
    if finish_reason:
        choice["finish_reason"] = finish_reason
    return {"choices": [choice]}


def _make_non_streaming_response(
    reasoning_text: str,
    reasoning_opaque: str,
) -> bytes:
    return json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello!",
                        "reasoning_text": reasoning_text,
                        "reasoning_opaque": reasoning_opaque,
                    }
                }
            ]
        }
    ).encode()


def _make_request_body(messages: list[dict]) -> bytes:
    return json.dumps({"model": "claude-sonnet-4", "messages": messages}).encode()


class FakeAsyncStream:
    """Minimal async-iterable that yields byte chunks."""

    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for chunk in self._chunks:
            yield chunk


# ---------------------------------------------------------------------------
# _text_key
# ---------------------------------------------------------------------------


class TestTextKey:
    def test_deterministic(self):
        assert _text_key("hello") == _text_key("hello")

    def test_different_inputs_differ(self):
        assert _text_key("hello") != _text_key("world")

    def test_returns_32_chars(self):
        assert len(_text_key("anything")) == 32


# ---------------------------------------------------------------------------
# _OpaqueCapturingStream
# ---------------------------------------------------------------------------


class TestOpaqueCapturingStream:
    @pytest.mark.asyncio
    async def test_captures_opaque_from_streaming_deltas(self):
        cache: dict[str, str] = {}
        chunks = [
            _sse_line(_make_streaming_event(reasoning_text="Think")),
            _sse_line(_make_streaming_event(reasoning_text="ing...")),
            _sse_line(_make_streaming_event(reasoning_opaque="opaque_part1")),
            _sse_line(_make_streaming_event(reasoning_opaque="_part2")),
            _sse_line(_make_streaming_event(finish_reason="stop")),
            _sse_done(),
        ]
        inner = FakeAsyncStream(chunks)
        wrapper = _OpaqueCapturingStream(inner, cache, "reasoning_text")

        collected = []
        async for chunk in wrapper:
            collected.append(chunk)

        # All bytes pass through unchanged
        assert collected == chunks

        # Opaque was captured, keyed by the full text
        key = _text_key("Thinking...")
        assert key in cache
        assert cache[key] == "opaque_part1_part2"

    @pytest.mark.asyncio
    async def test_passthrough_when_no_opaque(self):
        cache: dict[str, str] = {}
        chunks = [
            _sse_line(_make_streaming_event(reasoning_text="Just thinking")),
            _sse_line(_make_streaming_event(finish_reason="stop")),
            _sse_done(),
        ]
        inner = FakeAsyncStream(chunks)
        wrapper = _OpaqueCapturingStream(inner, cache, "reasoning_text")

        async for _ in wrapper:
            pass

        # No opaque data → nothing cached
        assert cache == {}

    @pytest.mark.asyncio
    async def test_handles_malformed_json_gracefully(self):
        cache: dict[str, str] = {}
        chunks = [
            b"data: {invalid json}\n\n",
            _sse_line(_make_streaming_event(reasoning_text="OK")),
            _sse_line(_make_streaming_event(reasoning_opaque="opq")),
            _sse_line(_make_streaming_event(finish_reason="stop")),
        ]
        inner = FakeAsyncStream(chunks)
        wrapper = _OpaqueCapturingStream(inner, cache, "reasoning_text")

        collected = []
        async for chunk in wrapper:
            collected.append(chunk)

        # Should still capture from valid events
        assert _text_key("OK") in cache

    @pytest.mark.asyncio
    async def test_aclose_flushes_remaining(self):
        cache: dict[str, str] = {}
        chunks = [
            _sse_line(_make_streaming_event(reasoning_text="partial")),
            _sse_line(_make_streaming_event(reasoning_opaque="opq_data")),
            # No finish_reason, no [DONE] — simulates abrupt close
        ]
        inner = FakeAsyncStream(chunks)
        wrapper = _OpaqueCapturingStream(inner, cache, "reasoning_text")

        async for _ in wrapper:
            pass
        # The finally in _iter_impl calls _flush after iteration

        assert _text_key("partial") in cache
        assert cache[_text_key("partial")] == "opq_data"


# ---------------------------------------------------------------------------
# _capture_from_content (non-streaming)
# ---------------------------------------------------------------------------


class TestCaptureFromContent:
    def test_captures_from_non_streaming_response(self):
        cache: dict[str, str] = {}
        content = _make_non_streaming_response("My thoughts", "encrypted_blob")
        _capture_from_content(content, cache, "reasoning_text")

        key = _text_key("My thoughts")
        assert key in cache
        assert cache[key] == "encrypted_blob"

    def test_ignores_response_without_opaque(self):
        cache: dict[str, str] = {}
        content = json.dumps(
            {"choices": [{"message": {"reasoning_text": "thoughts"}}]}
        ).encode()
        _capture_from_content(content, cache, "reasoning_text")
        assert cache == {}

    def test_handles_bad_json(self):
        cache: dict[str, str] = {}
        _capture_from_content(b"not json", cache, "reasoning_text")
        assert cache == {}


# ---------------------------------------------------------------------------
# _inject_opaque_into_request
# ---------------------------------------------------------------------------


class TestInjectOpaqueIntoRequest:
    def test_injects_opaque_for_matching_assistant_message(self):
        thinking_text = "I'm thinking deeply"
        cache = {_text_key(thinking_text): "encrypted_opaque_data"}

        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "reasoning_text": thinking_text, "content": "Hello!"},
        ]
        body = _make_request_body(messages)
        request = httpx.Request(
            "POST", "https://api.example.com/v1/chat/completions", content=body
        )

        client = httpx.AsyncClient()
        _inject_opaque_into_request(request, cache, client, "reasoning_text")

        result_body = json.loads(request.content)
        assistant_msg = result_body["messages"][1]
        assert assistant_msg["reasoning_opaque"] == "encrypted_opaque_data"

    def test_skips_messages_that_already_have_opaque(self):
        thinking_text = "Some thoughts"
        cache = {_text_key(thinking_text): "new_opaque"}

        messages = [
            {
                "role": "assistant",
                "reasoning_text": thinking_text,
                "reasoning_opaque": "original_opaque",
                "content": "Hi",
            },
        ]
        body = _make_request_body(messages)
        request = httpx.Request(
            "POST", "https://api.example.com/v1/chat/completions", content=body
        )

        client = httpx.AsyncClient()
        _inject_opaque_into_request(request, cache, client, "reasoning_text")

        result_body = json.loads(request.content)
        # Should NOT overwrite existing opaque
        assert result_body["messages"][0]["reasoning_opaque"] == "original_opaque"

    def test_no_op_for_non_assistant_messages(self):
        cache = {_text_key("stuff"): "opaque"}
        messages = [{"role": "user", "content": "Hi", "reasoning_text": "stuff"}]
        body = _make_request_body(messages)
        request = httpx.Request(
            "POST", "https://api.example.com/v1/chat/completions", content=body
        )

        original_content = request.content
        client = httpx.AsyncClient()
        _inject_opaque_into_request(request, cache, client, "reasoning_text")

        # Content should be unchanged (user messages don't get opaque)
        assert request.content == original_content

    def test_strips_reasoning_text_on_cache_miss(self):
        """When no opaque is cached, reasoning_text is stripped to prevent 400."""
        cache: dict[str, str] = {}
        messages = [
            {
                "role": "assistant",
                "reasoning_text": "unknown thoughts",
                "content": "Hi",
            },
        ]
        body = _make_request_body(messages)
        request = httpx.Request(
            "POST", "https://api.example.com/v1/chat/completions", content=body
        )

        client = httpx.AsyncClient()
        _inject_opaque_into_request(request, cache, client, "reasoning_text")

        result_body = json.loads(request.content)
        # reasoning_text should have been stripped
        assert "reasoning_text" not in result_body["messages"][0]
        # content should still be there
        assert result_body["messages"][0]["content"] == "Hi"

    def test_handles_empty_body_gracefully(self):
        cache = {_text_key("x"): "y"}
        request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
        client = httpx.AsyncClient()
        # Should not raise
        _inject_opaque_into_request(request, cache, client, "reasoning_text")

    def test_handles_non_json_body_gracefully(self):
        cache = {_text_key("x"): "y"}
        request = httpx.Request(
            "POST",
            "https://api.example.com/v1/chat/completions",
            content=b"not json",
        )
        client = httpx.AsyncClient()
        _inject_opaque_into_request(request, cache, client, "reasoning_text")


# ---------------------------------------------------------------------------
# _strip_all_reasoning_fields (recovery layer)
# ---------------------------------------------------------------------------


class TestStripAllReasoningFields:
    def test_strips_both_fields_from_assistant_messages(self):
        messages = [
            {"role": "user", "content": "Hi"},
            {
                "role": "assistant",
                "content": "Hello!",
                "reasoning_text": "some thoughts",
                "reasoning_opaque": "encrypted_blob",
            },
            {"role": "user", "content": "How?"},
            {
                "role": "assistant",
                "content": "Like this.",
                "reasoning_text": "more thoughts",
            },
        ]
        body = _make_request_body(messages)
        request = httpx.Request(
            "POST", "https://api.example.com/v1/chat/completions", content=body
        )
        client = httpx.AsyncClient()

        result = _strip_all_reasoning_fields(request, client, "reasoning_text")

        assert result is True
        result_body = json.loads(request.content)
        for msg in result_body["messages"]:
            assert "reasoning_text" not in msg
            assert "reasoning_opaque" not in msg
        # Content should be preserved
        assert result_body["messages"][1]["content"] == "Hello!"
        assert result_body["messages"][3]["content"] == "Like this."

    def test_returns_false_when_nothing_to_strip(self):
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        body = _make_request_body(messages)
        request = httpx.Request(
            "POST", "https://api.example.com/v1/chat/completions", content=body
        )
        client = httpx.AsyncClient()

        result = _strip_all_reasoning_fields(request, client, "reasoning_text")
        assert result is False

    def test_does_not_touch_user_messages(self):
        messages = [
            {"role": "user", "content": "Hi", "reasoning_text": "sneaky"},
        ]
        body = _make_request_body(messages)
        request = httpx.Request(
            "POST", "https://api.example.com/v1/chat/completions", content=body
        )
        client = httpx.AsyncClient()

        result = _strip_all_reasoning_fields(request, client, "reasoning_text")
        assert result is False

    def test_handles_empty_body(self):
        request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
        client = httpx.AsyncClient()
        result = _strip_all_reasoning_fields(request, client, "reasoning_text")
        assert result is False


# ---------------------------------------------------------------------------
# 400 retry integration (patch_client_for_reasoning_opaque)
# ---------------------------------------------------------------------------


class TestRetryOn400:
    @pytest.mark.asyncio
    async def test_prevention_strips_orphaned_reasoning_text(self):
        """Prevention layer: orphaned reasoning_text is stripped before send.

        If we have no cached opaque, the reasoning_text gets removed
        *before* the request is sent, so we never even hit a 400.
        """
        call_count = 0
        sent_bodies: list[dict] = []

        client = httpx.AsyncClient()

        # Patch client.send directly (no opaque cache = prevention kicks in)
        from code_puppy.plugins.copilot_auth.reasoning_client import (
            _inject_opaque_into_request,
        )

        opaque_cache: dict[str, str] = {}  # Empty — will trigger stripping

        async def tracking_send(request, *args, **kwargs):
            nonlocal call_count
            if request.method == "POST":
                _inject_opaque_into_request(
                    request, opaque_cache, client, "reasoning_text"
                )
            call_count += 1
            body = json.loads(request.content) if request.content else {}
            sent_bodies.append(body)
            return httpx.Response(200, content=b'{"choices": []}', request=request)

        client.send = tracking_send

        messages = [
            {"role": "user", "content": "Hi"},
            {
                "role": "assistant",
                "reasoning_text": "deep thoughts",
                "content": "Hello!",
            },
        ]
        body = json.dumps({"model": "claude-sonnet-4", "messages": messages}).encode()
        request = httpx.Request(
            "POST", "https://api.example.com/v1/chat/completions", content=body
        )

        response = await client.send(request)

        assert response.status_code == 200
        assert call_count == 1  # Only one call — no retry needed
        # reasoning_text was stripped before sending
        sent_msgs = sent_bodies[0]["messages"]
        assert "reasoning_text" not in sent_msgs[1]

    @pytest.mark.asyncio
    async def test_recovery_strips_and_retries_on_400(self):
        """Recovery layer: if we get a 400 despite injection, strip and retry.

        Simulates stale/bad opaque data that passes prevention but the
        API still rejects.
        """
        call_count = 0

        from code_puppy.plugins.copilot_auth.reasoning_client import (
            _inject_opaque_into_request,
            _strip_all_reasoning_fields,
        )

        thinking_text = "deep thoughts"
        # Seed cache with BAD opaque — will pass prevention but API rejects
        opaque_cache = {_text_key(thinking_text): "stale_bad_opaque"}

        client = httpx.AsyncClient()

        async def fake_send(request, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            body = json.loads(request.content) if request.content else {}
            msgs = body.get("messages", [])
            has_opaque = any(
                "reasoning_opaque" in m for m in msgs if isinstance(m, dict)
            )
            if has_opaque:
                # API rejects stale opaque
                return httpx.Response(
                    400,
                    content=b'{"error": "invalid reasoning_opaque"}',
                    request=request,
                )
            return httpx.Response(
                200,
                content=b'{"choices": [{"message": {"content": "ok"}}]}',
                request=request,
            )

        # Wire up manually: inject → send → on 400, strip → retry
        async def orchestrated_send(request, *args, **kwargs):
            if request.method == "POST":
                _inject_opaque_into_request(
                    request, opaque_cache, client, "reasoning_text"
                )
            response = await fake_send(request, *args, **kwargs)
            if response.status_code == 400 and request.method == "POST":
                if _strip_all_reasoning_fields(request, client, "reasoning_text"):
                    response = await fake_send(request, *args, **kwargs)
            return response

        client.send = orchestrated_send

        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "reasoning_text": thinking_text, "content": "Hello!"},
            {"role": "user", "content": "Now what?"},
        ]
        body = json.dumps({"model": "claude-sonnet-4", "messages": messages}).encode()
        request = httpx.Request(
            "POST", "https://api.example.com/v1/chat/completions", content=body
        )

        response = await client.send(request)

        # First call: 400 (bad opaque). Second call: 200 (reasoning stripped).
        assert response.status_code == 200
        assert call_count == 2


# ---------------------------------------------------------------------------
# patch_client_for_reasoning_opaque (integration)
# ---------------------------------------------------------------------------


class TestPatchClientIntegration:
    """End-to-end tests through the actual patched client pipeline.

    These replace the original stub tests that only verified send was
    replaced.  The trick: set ``client.send`` to a fake *before* calling
    ``patch_client_for_reasoning_opaque``, so the patch captures the fake
    as ``original_send`` inside its closure.
    """

    @pytest.mark.asyncio
    async def test_full_round_trip_captures_and_injects_opaque(self):
        """Response → cache → next request: opaque survives the round-trip."""
        thinking = "Let me analyze this step by step"
        opaque = "encrypted_round_trip_data_abc123"
        captured_requests: list[dict] = []

        async def fake_send(request, *args, **kwargs):
            if request.method == "POST" and request.content:
                captured_requests.append(json.loads(request.content))
            return httpx.Response(
                200,
                content=_make_non_streaming_response(thinking, opaque),
                request=request,
            )

        client = httpx.AsyncClient()
        client.send = fake_send  # Captured as original_send by patch
        patch_client_for_reasoning_opaque(client)

        # 1st call — seeds the opaque cache from the response
        req1 = httpx.Request(
            "POST",
            "https://api.example.com/chat/completions",
            content=_make_request_body([{"role": "user", "content": "Hi"}]),
        )
        await client.send(req1)

        # 2nd call — assistant message with reasoning_text should get
        # the cached opaque injected before reaching fake_send
        req2 = httpx.Request(
            "POST",
            "https://api.example.com/chat/completions",
            content=_make_request_body(
                [
                    {"role": "user", "content": "Hi"},
                    {
                        "role": "assistant",
                        "reasoning_text": thinking,
                        "content": "Hello!",
                    },
                    {"role": "user", "content": "Follow up?"},
                ]
            ),
        )
        await client.send(req2)

        # The fake_send should have received the injected opaque
        assistant_msg = captured_requests[1]["messages"][1]
        assert assistant_msg["reasoning_opaque"] == opaque
        assert assistant_msg["reasoning_text"] == thinking  # Preserved

    @pytest.mark.asyncio
    async def test_get_requests_pass_through_unmodified(self):
        """GET requests should flow straight through without interception."""
        received_methods: list[str] = []

        async def fake_send(request, *args, **kwargs):
            received_methods.append(request.method)
            return httpx.Response(200, content=b'{"ok": true}', request=request)

        client = httpx.AsyncClient()
        client.send = fake_send
        patch_client_for_reasoning_opaque(client)

        req = httpx.Request("GET", "https://api.example.com/models")
        resp = await client.send(req)

        assert resp.status_code == 200
        assert received_methods == ["GET"]

    @pytest.mark.asyncio
    async def test_recovery_400_retries_through_patched_pipeline(self):
        """Full pipeline: stale opaque → 400 → strip → retry → 200."""
        thinking = "deep analysis"
        opaque = "stale_encrypted_blob"
        call_count = 0

        async def fake_send(request, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            body = json.loads(request.content) if request.content else {}
            msgs = body.get("messages", [])
            has_opaque = any(
                "reasoning_opaque" in m for m in msgs if isinstance(m, dict)
            )
            if call_count == 1:
                # Seed call — return opaque so it's cached
                return httpx.Response(
                    200,
                    content=_make_non_streaming_response(thinking, opaque),
                    request=request,
                )
            if has_opaque:
                # API rejects stale opaque
                return httpx.Response(
                    400,
                    content=b'{"error": "invalid reasoning_opaque"}',
                    request=request,
                )
            # After strip, no opaque → success
            return httpx.Response(
                200,
                content=b'{"choices": [{"message": {"content": "ok"}}]}',
                request=request,
            )

        client = httpx.AsyncClient()
        client.send = fake_send
        patch_client_for_reasoning_opaque(client)

        # Seed the cache
        req1 = httpx.Request(
            "POST",
            "https://api.example.com/chat/completions",
            content=_make_request_body([{"role": "user", "content": "Hi"}]),
        )
        await client.send(req1)

        # Now send with reasoning_text — opaque will be injected (stale),
        # API returns 400, recovery strips and retries → 200
        req2 = httpx.Request(
            "POST",
            "https://api.example.com/chat/completions",
            content=_make_request_body(
                [
                    {"role": "user", "content": "Hi"},
                    {
                        "role": "assistant",
                        "reasoning_text": thinking,
                        "content": "Hello!",
                    },
                    {"role": "user", "content": "Now what?"},
                ]
            ),
        )
        resp = await client.send(req2)

        assert resp.status_code == 200
        # 1 seed + 1 rejected + 1 retry = 3 calls
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_recovery_returns_retry_response_when_both_fail(self):
        """When recovery also fails, the RETRY response is returned.

        Regression: the old log message said "returning original error"
        but the code actually returned the retry response.  Now both
        the log and the behaviour agree.
        """
        thinking = "some analysis"
        opaque = "will_go_stale"
        call_count = 0

        async def fake_send(request, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Seed call
                return httpx.Response(
                    200,
                    content=_make_non_streaming_response(thinking, opaque),
                    request=request,
                )
            if call_count == 2:
                # First real call: 400 (stale opaque)
                return httpx.Response(
                    400,
                    content=b'{"error": "bad opaque"}',
                    request=request,
                )
            # Retry after strip: ALSO fails with a distinct status
            return httpx.Response(
                502,
                content=b'{"error": "gateway timeout"}',
                request=request,
            )

        client = httpx.AsyncClient()
        client.send = fake_send
        patch_client_for_reasoning_opaque(client)

        # Seed
        req1 = httpx.Request(
            "POST",
            "https://api.example.com/chat/completions",
            content=_make_request_body([{"role": "user", "content": "Hi"}]),
        )
        await client.send(req1)

        # Trigger: 400 → strip → retry → 502
        req2 = httpx.Request(
            "POST",
            "https://api.example.com/chat/completions",
            content=_make_request_body(
                [
                    {"role": "user", "content": "Hi"},
                    {
                        "role": "assistant",
                        "reasoning_text": thinking,
                        "content": "Hello!",
                    },
                ]
            ),
        )
        resp = await client.send(req2)

        # Must be the RETRY response (502), NOT the original (400)
        assert resp.status_code == 502
        assert call_count == 3


# ---------------------------------------------------------------------------
# Cache eviction
# ---------------------------------------------------------------------------


class TestCacheEviction:
    @pytest.mark.asyncio
    async def test_cache_evicts_oldest_entries(self):
        cache: dict[str, str] = {}
        # Fill cache beyond max
        for i in range(_MAX_CACHE_ENTRIES + 10):
            cache[_text_key(f"text_{i}")] = f"opaque_{i}"

        # Simulate a flush that would trigger eviction
        chunks = [
            _sse_line(_make_streaming_event(reasoning_text="final")),
            _sse_line(_make_streaming_event(reasoning_opaque="final_opaque")),
            _sse_line(_make_streaming_event(finish_reason="stop")),
        ]
        inner = FakeAsyncStream(chunks)
        wrapper = _OpaqueCapturingStream(inner, cache, "reasoning_text")

        async for _ in wrapper:
            pass

        # Cache should have been trimmed
        assert len(cache) <= _MAX_CACHE_ENTRIES
        # The newest entry should still be there
        assert _text_key("final") in cache
