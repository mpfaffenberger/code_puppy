"""Tests for subagent_stream_handler module.

Covers:
- Token estimation (_estimate_tokens)
- Callback firing (_fire_callback)
- Event stream handling (PartStartEvent, PartDeltaEvent, PartEndEvent)
- Different part types (Thinking, Text, ToolCall)
- Manager updates and status tracking
- Error handling and edge cases
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import PartDeltaEvent, PartEndEvent, PartStartEvent, RunContext
from pydantic_ai.messages import (
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)

from code_puppy.agents.subagent_stream_handler import (
    _estimate_tokens,
    _fire_callback,
    _handle_event,
    subagent_stream_handler,
)

# =============================================================================
# Token Estimation Tests
# =============================================================================


class TestEstimateTokens:
    """Tests for the _estimate_tokens function."""

    def test_empty_string_returns_zero(self):
        """Empty string should return 0 tokens."""
        assert _estimate_tokens("") == 0

    def test_none_like_empty_returns_zero(self):
        """Falsy content should return 0 tokens."""
        # Empty string is the only falsy case the function handles
        assert _estimate_tokens("") == 0

    def test_short_content_returns_minimum_one(self):
        """Very short content (< 4 chars) should return minimum 1 token."""
        assert _estimate_tokens("a") == 1
        assert _estimate_tokens("ab") == 1
        assert _estimate_tokens("abc") == 1

    def test_four_chars_returns_one_token(self):
        """4 characters should return 1 token (4 chars = 1 token heuristic)."""
        assert _estimate_tokens("abcd") == 1

    def test_longer_content_scales_correctly(self):
        """Longer content should scale at ~4 chars per token."""
        # 8 chars = 2 tokens
        assert _estimate_tokens("abcdefgh") == 2
        # 16 chars = 4 tokens
        assert _estimate_tokens("a" * 16) == 4
        # 100 chars = 25 tokens
        assert _estimate_tokens("x" * 100) == 25

    def test_realistic_text_estimation(self):
        """Test with realistic text content."""
        text = "Hello, this is a test message for token estimation."
        # len(text) // 4 = estimated tokens
        expected = len(text) // 4
        assert _estimate_tokens(text) == expected


# =============================================================================
# Callback Firing Tests
# =============================================================================


class TestFireCallback:
    """Tests for the _fire_callback function."""

    def test_fire_callback_no_event_loop(self):
        """Test callback handling when no event loop is running."""
        # When no event loop is available, should not raise
        # This tests the RuntimeError handling path
        with patch(
            "code_puppy.agents.subagent_stream_handler.asyncio.get_running_loop",
            side_effect=RuntimeError("No running event loop"),
        ):
            # Should not raise, just log debug
            _fire_callback("part_start", {"index": 0}, "session-123")

    def test_fire_callback_import_error(self):
        """Test callback handling when callbacks module is unavailable."""
        # Simulate ImportError when importing callbacks
        with patch(
            "code_puppy.agents.subagent_stream_handler.asyncio.get_running_loop",
            return_value=MagicMock(),
        ):
            with patch.dict("sys.modules", {"code_puppy.callbacks": None}):
                # Should not raise
                _fire_callback("part_start", {"index": 0}, "session-123")

    def test_fire_callback_general_exception(self):
        """Test callback handling for general exceptions."""
        # Simulate exception during callback import
        with patch(
            "code_puppy.agents.subagent_stream_handler.asyncio.get_running_loop",
            side_effect=Exception("Some unexpected error"),
        ):
            # Should not raise, just log debug
            _fire_callback("part_start", {"index": 0}, "session-123")


# =============================================================================
# Handle Event Tests
# =============================================================================


class TestHandleEvent:
    """Tests for the _handle_event function."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock SubAgentConsoleManager."""
        manager = MagicMock()
        manager.update_agent = MagicMock()
        return manager

    @pytest.mark.asyncio
    async def test_handle_event_no_session_id(self, mock_manager):
        """Test that events are skipped when session_id is None."""
        event = MagicMock(spec=PartStartEvent)

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id=None,
                token_count=0,
                tool_call_count=0,
                active_tool_parts=set(),
            )

            # Should not update manager or fire callback
            mock_manager.update_agent.assert_not_called()
            mock_fire.assert_not_called()

    # -------------------------------------------------------------------------
    # PartStartEvent Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_handle_part_start_thinking(self, mock_manager):
        """Test handling PartStartEvent with ThinkingPart."""
        thinking_part = ThinkingPart(content="thinking content")
        event = PartStartEvent(index=0, part=thinking_part)

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id="session-123",
                token_count=10,
                tool_call_count=0,
                active_tool_parts=set(),
            )

            mock_manager.update_agent.assert_called_once_with(
                "session-123", status="thinking"
            )
            mock_fire.assert_called_once()
            call_args = mock_fire.call_args
            assert call_args[0][0] == "part_start"
            assert call_args[0][1]["part_type"] == "ThinkingPart"
            assert call_args[0][2] == "session-123"

    @pytest.mark.asyncio
    async def test_handle_part_start_text(self, mock_manager):
        """Test handling PartStartEvent with TextPart."""
        text_part = TextPart(content="text content")
        event = PartStartEvent(index=0, part=text_part)

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id="session-123",
                token_count=10,
                tool_call_count=0,
                active_tool_parts=set(),
            )

            mock_manager.update_agent.assert_called_once_with(
                "session-123", status="running"
            )
            mock_fire.assert_called_once()
            call_args = mock_fire.call_args
            assert call_args[0][0] == "part_start"
            assert call_args[0][1]["part_type"] == "TextPart"

    @pytest.mark.asyncio
    async def test_handle_part_start_tool_call(self, mock_manager):
        """Test handling PartStartEvent with ToolCallPart."""
        tool_part = ToolCallPart(
            tool_name="my_tool", args="{}", tool_call_id="call-123"
        )
        event = PartStartEvent(index=0, part=tool_part)

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id="session-123",
                token_count=10,
                tool_call_count=2,  # Already 2 tool calls
                active_tool_parts=set(),
            )

            mock_manager.update_agent.assert_called_once_with(
                "session-123",
                status="tool_calling",
                tool_call_count=3,  # +1 for the new one
                current_tool="my_tool",
            )
            mock_fire.assert_called_once()
            call_args = mock_fire.call_args
            assert call_args[0][1]["tool_name"] == "my_tool"
            assert call_args[0][1]["tool_call_id"] == "call-123"

    # -------------------------------------------------------------------------
    # PartDeltaEvent Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_handle_part_delta_text(self, mock_manager):
        """Test handling PartDeltaEvent with TextPartDelta."""
        delta = TextPartDelta(content_delta="hello world")
        event = PartDeltaEvent(index=0, delta=delta)

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id="session-123",
                token_count=10,
                tool_call_count=0,
                active_tool_parts=set(),
            )

            # Should update token count (10 + estimate of "hello world")
            mock_manager.update_agent.assert_called_once()
            call_kwargs = mock_manager.update_agent.call_args[1]
            assert "token_count" in call_kwargs
            assert call_kwargs["token_count"] > 10  # Added tokens

            mock_fire.assert_called_once()
            call_args = mock_fire.call_args
            assert call_args[0][1]["content_delta"] == "hello world"

    @pytest.mark.asyncio
    async def test_handle_part_delta_text_empty(self, mock_manager):
        """Test handling PartDeltaEvent with empty TextPartDelta."""
        delta = TextPartDelta(content_delta="")
        event = PartDeltaEvent(index=0, delta=delta)

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id="session-123",
                token_count=10,
                tool_call_count=0,
                active_tool_parts=set(),
            )

            # Should NOT update manager for empty delta
            mock_manager.update_agent.assert_not_called()
            # Should still fire callback
            mock_fire.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_part_delta_thinking(self, mock_manager):
        """Test handling PartDeltaEvent with ThinkingPartDelta."""
        delta = ThinkingPartDelta(content_delta="thinking...")
        event = PartDeltaEvent(index=0, delta=delta)

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id="session-123",
                token_count=5,
                tool_call_count=0,
                active_tool_parts=set(),
            )

            mock_manager.update_agent.assert_called_once()
            call_kwargs = mock_manager.update_agent.call_args[1]
            assert call_kwargs["token_count"] > 5

            mock_fire.assert_called_once()
            call_args = mock_fire.call_args
            assert call_args[0][1]["content_delta"] == "thinking..."

    @pytest.mark.asyncio
    async def test_handle_part_delta_tool_call(self, mock_manager):
        """Test handling PartDeltaEvent with ToolCallPartDelta."""
        delta = ToolCallPartDelta(args_delta='{"key": "value"}')
        event = PartDeltaEvent(index=0, delta=delta)

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id="session-123",
                token_count=10,
                tool_call_count=1,
                active_tool_parts={0},
            )

            # ToolCallPartDelta doesn't update manager
            mock_manager.update_agent.assert_not_called()
            mock_fire.assert_called_once()
            call_args = mock_fire.call_args
            assert call_args[0][1]["args_delta"] == '{"key": "value"}'

    # -------------------------------------------------------------------------
    # PartEndEvent Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_handle_part_end_tool_call(self, mock_manager):
        """Test handling PartEndEvent when a tool call ends."""
        tool_part = ToolCallPart(tool_name="my_tool", args="{}", tool_call_id="t1")
        event = PartEndEvent(index=0, part=tool_part)
        active_parts = {0}  # Index 0 is a tool call

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id="session-123",
                token_count=10,
                tool_call_count=1,
                active_tool_parts=active_parts,
            )

            # Should reset status since no more active tool parts
            mock_manager.update_agent.assert_called_once_with(
                "session-123",
                current_tool=None,
                status="running",
            )
            mock_fire.assert_called_once()
            call_args = mock_fire.call_args
            assert call_args[0][0] == "part_end"

    @pytest.mark.asyncio
    async def test_handle_part_end_tool_call_with_remaining(self, mock_manager):
        """Test handling PartEndEvent when other tool calls remain active."""
        tool_part = ToolCallPart(tool_name="my_tool", args="{}", tool_call_id="t1")
        event = PartEndEvent(index=0, part=tool_part)
        active_parts = {0, 1}  # Index 0 ends, index 1 still active

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id="session-123",
                token_count=10,
                tool_call_count=2,
                active_tool_parts=active_parts,
            )

            # Should NOT reset status since tool call at index 1 is still active
            mock_manager.update_agent.assert_not_called()
            mock_fire.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_part_end_non_tool(self, mock_manager):
        """Test handling PartEndEvent for non-tool parts."""
        text_part = TextPart(content="some text")
        event = PartEndEvent(index=0, part=text_part)
        active_parts = set()  # No active tool parts

        with patch(
            "code_puppy.agents.subagent_stream_handler._fire_callback"
        ) as mock_fire:
            await _handle_event(
                event=event,
                manager=mock_manager,
                session_id="session-123",
                token_count=10,
                tool_call_count=0,
                active_tool_parts=active_parts,
            )

            # Should not update manager for non-tool part end
            mock_manager.update_agent.assert_not_called()
            mock_fire.assert_called_once()


# =============================================================================
# Main Stream Handler Tests
# =============================================================================


class TestSubagentStreamHandler:
    """Tests for the main subagent_stream_handler function."""

    @pytest.fixture
    def mock_ctx(self):
        """Create a mock RunContext."""
        return MagicMock(spec=RunContext)

    @pytest.fixture
    def mock_manager(self):
        """Create a mock SubAgentConsoleManager."""
        manager = MagicMock()
        manager.update_agent = MagicMock()
        return manager

    async def _create_async_events(self, events):
        """Helper to create async iterable from list of events."""
        for event in events:
            yield event

    @pytest.mark.asyncio
    async def test_stream_handler_with_session_id(self, mock_ctx, mock_manager):
        """Test stream handler uses provided session_id."""
        text_part = TextPart(content="hello")
        events = [PartStartEvent(index=0, part=text_part)]

        with patch(
            "code_puppy.messaging.subagent_console.SubAgentConsoleManager.get_instance",
            return_value=mock_manager,
        ):
            with patch("code_puppy.messaging.get_session_context"):
                with patch("code_puppy.agents.subagent_stream_handler._fire_callback"):
                    await subagent_stream_handler(
                        mock_ctx,
                        self._create_async_events(events),
                        session_id="explicit-session",
                    )

                    # Should NOT call get_session_context when session_id provided
                    mock_manager.update_agent.assert_called()
                    call_args = mock_manager.update_agent.call_args_list[0]
                    assert call_args[0][0] == "explicit-session"

    @pytest.mark.asyncio
    async def test_stream_handler_fallback_to_context(self, mock_ctx, mock_manager):
        """Test stream handler falls back to get_session_context."""
        text_part = TextPart(content="hello")
        events = [PartStartEvent(index=0, part=text_part)]

        with patch(
            "code_puppy.messaging.subagent_console.SubAgentConsoleManager.get_instance",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.messaging.get_session_context",
                return_value="context-session",
            ):
                with patch("code_puppy.agents.subagent_stream_handler._fire_callback"):
                    await subagent_stream_handler(
                        mock_ctx,
                        self._create_async_events(events),
                        session_id=None,  # No session_id provided
                    )

                    mock_manager.update_agent.assert_called()
                    call_args = mock_manager.update_agent.call_args_list[0]
                    assert call_args[0][0] == "context-session"

    @pytest.mark.asyncio
    async def test_stream_handler_tracks_tool_calls(self, mock_ctx, mock_manager):
        """Test stream handler tracks tool call count."""
        tool_part1 = ToolCallPart(tool_name="tool1", args="{}", tool_call_id="t1")
        tool_part2 = ToolCallPart(tool_name="tool2", args="{}", tool_call_id="t2")
        events = [
            PartStartEvent(index=0, part=tool_part1),
            PartStartEvent(index=1, part=tool_part2),
        ]

        with patch(
            "code_puppy.messaging.subagent_console.SubAgentConsoleManager.get_instance",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.messaging.get_session_context",
                return_value="session-123",
            ):
                with patch("code_puppy.agents.subagent_stream_handler._fire_callback"):
                    await subagent_stream_handler(
                        mock_ctx,
                        self._create_async_events(events),
                    )

                    # Should have two update_agent calls with increasing tool counts
                    assert mock_manager.update_agent.call_count == 2
                    calls = mock_manager.update_agent.call_args_list
                    assert calls[0][1]["tool_call_count"] == 1
                    assert calls[1][1]["tool_call_count"] == 2

    @pytest.mark.asyncio
    async def test_stream_handler_tracks_tokens(self, mock_ctx, mock_manager):
        """Test stream handler accumulates token count."""
        events = [
            PartStartEvent(index=0, part=TextPart(content="")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="hello")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="world")),
        ]

        with patch(
            "code_puppy.messaging.subagent_console.SubAgentConsoleManager.get_instance",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.messaging.get_session_context",
                return_value="session-123",
            ):
                with patch("code_puppy.agents.subagent_stream_handler._fire_callback"):
                    await subagent_stream_handler(
                        mock_ctx,
                        self._create_async_events(events),
                    )

                    # Token counts should be updated for each delta
                    delta_calls = [
                        c
                        for c in mock_manager.update_agent.call_args_list
                        if "token_count" in c[1]
                    ]
                    assert len(delta_calls) == 2

    @pytest.mark.asyncio
    async def test_stream_handler_handles_event_error(self, mock_ctx, mock_manager):
        """Test stream handler continues on event handling errors."""

        async def error_events():
            yield PartStartEvent(index=0, part=TextPart(content=""))
            # This will cause an error in _handle_event
            yield "invalid_event"
            yield PartStartEvent(index=1, part=TextPart(content=""))

        with patch(
            "code_puppy.messaging.subagent_console.SubAgentConsoleManager.get_instance",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.messaging.get_session_context",
                return_value="session-123",
            ):
                with patch("code_puppy.agents.subagent_stream_handler._fire_callback"):
                    # Should not raise, should continue processing
                    await subagent_stream_handler(
                        mock_ctx,
                        error_events(),
                    )

                    # Should have processed first and third events
                    assert mock_manager.update_agent.call_count >= 1

    @pytest.mark.asyncio
    async def test_stream_handler_part_end_removes_active(self, mock_ctx, mock_manager):
        """Test stream handler removes completed tool parts from active set."""
        tool_part = ToolCallPart(tool_name="my_tool", args="{}", tool_call_id="t1")
        events = [
            PartStartEvent(index=0, part=tool_part),
            PartEndEvent(index=0, part=tool_part),
        ]

        with patch(
            "code_puppy.messaging.subagent_console.SubAgentConsoleManager.get_instance",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.messaging.get_session_context",
                return_value="session-123",
            ):
                with patch("code_puppy.agents.subagent_stream_handler._fire_callback"):
                    await subagent_stream_handler(
                        mock_ctx,
                        self._create_async_events(events),
                    )

                    # Last call should reset current_tool to None
                    last_call = mock_manager.update_agent.call_args_list[-1]
                    assert last_call[1].get("current_tool") is None
                    assert last_call[1].get("status") == "running"

    @pytest.mark.asyncio
    async def test_stream_handler_empty_events(self, mock_ctx, mock_manager):
        """Test stream handler handles empty event stream."""

        async def empty_events():
            return
            yield  # Make this a generator

        with patch(
            "code_puppy.messaging.subagent_console.SubAgentConsoleManager.get_instance",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.messaging.get_session_context",
                return_value="session-123",
            ):
                with patch("code_puppy.agents.subagent_stream_handler._fire_callback"):
                    # Should not raise
                    await subagent_stream_handler(
                        mock_ctx,
                        empty_events(),
                    )

                    # No events, no updates
                    mock_manager.update_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_handler_mixed_event_types(self, mock_ctx, mock_manager):
        """Test stream handler processes a realistic sequence of events."""
        thinking_part = ThinkingPart(content="")
        text_part = TextPart(content="")
        tool_part = ToolCallPart(tool_name="search", args="{}", tool_call_id="c1")

        events = [
            # Start thinking
            PartStartEvent(index=0, part=thinking_part),
            PartDeltaEvent(index=0, delta=ThinkingPartDelta(content_delta="let me")),
            PartDeltaEvent(index=0, delta=ThinkingPartDelta(content_delta=" think")),
            PartEndEvent(index=0, part=thinking_part),
            # Text response
            PartStartEvent(index=1, part=text_part),
            PartDeltaEvent(index=1, delta=TextPartDelta(content_delta="Here is")),
            PartDeltaEvent(index=1, delta=TextPartDelta(content_delta=" the answer")),
            PartEndEvent(index=1, part=text_part),
            # Tool call
            PartStartEvent(index=2, part=tool_part),
            PartDeltaEvent(
                index=2, delta=ToolCallPartDelta(args_delta='{"query": "test"}')
            ),
            PartEndEvent(index=2, part=tool_part),
        ]

        with patch(
            "code_puppy.messaging.subagent_console.SubAgentConsoleManager.get_instance",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.messaging.get_session_context",
                return_value="session-123",
            ):
                with patch(
                    "code_puppy.agents.subagent_stream_handler._fire_callback"
                ) as mock_fire:
                    await subagent_stream_handler(
                        mock_ctx,
                        self._create_async_events(events),
                    )

                    # Should have multiple updates
                    assert mock_manager.update_agent.call_count > 0
                    # Should have fired callbacks for all events
                    assert mock_fire.call_count == len(events)
