"""Tests for frontend_emitter plugin - register_callbacks.py and emitter.py."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

# ── emitter.py ──────────────────────────────────────────────────────────


class TestEmitEvent:
    def test_disabled_returns_early(self):
        from code_puppy.plugins.frontend_emitter.emitter import (
            _recent_events,
            _subscribers,
            emit_event,
        )

        _recent_events.clear()
        _subscribers.clear()
        with patch(
            "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_enabled",
            return_value=False,
        ):
            emit_event("test_event", {"foo": 1})
        assert len(_recent_events) == 0

    def test_enabled_stores_and_broadcasts(self):
        from code_puppy.plugins.frontend_emitter.emitter import (
            _recent_events,
            _subscribers,
            emit_event,
        )

        _recent_events.clear()
        _subscribers.clear()

        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        _subscribers.add(q)

        with (
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_max_recent_events",
                return_value=5,
            ),
        ):
            emit_event("my_type", {"k": "v"})

        assert len(_recent_events) == 1
        assert _recent_events[0]["type"] == "my_type"
        assert not q.empty()
        evt = q.get_nowait()
        assert evt["type"] == "my_type"
        _subscribers.clear()
        _recent_events.clear()

    def test_data_defaults_to_empty_dict(self):
        from code_puppy.plugins.frontend_emitter.emitter import (
            _recent_events,
            _subscribers,
            emit_event,
        )

        _recent_events.clear()
        _subscribers.clear()
        with (
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_max_recent_events",
                return_value=5,
            ),
        ):
            emit_event("evt")
        assert _recent_events[0]["data"] == {}
        _recent_events.clear()

    def test_recent_events_capped(self):
        from code_puppy.plugins.frontend_emitter.emitter import (
            _recent_events,
            _subscribers,
            emit_event,
        )

        _recent_events.clear()
        _subscribers.clear()
        with (
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_max_recent_events",
                return_value=2,
            ),
        ):
            for i in range(5):
                emit_event(f"e{i}")
        assert len(_recent_events) == 2
        _recent_events.clear()

    def test_queue_full_doesnt_raise(self):
        from code_puppy.plugins.frontend_emitter.emitter import (
            _recent_events,
            _subscribers,
            emit_event,
        )

        _recent_events.clear()
        _subscribers.clear()
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        q.put_nowait({"dummy": True})  # fill it
        _subscribers.add(q)
        with (
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_max_recent_events",
                return_value=10,
            ),
        ):
            emit_event("overflow")  # should not raise
        _subscribers.clear()
        _recent_events.clear()

    def test_subscriber_exception_doesnt_raise(self):
        from code_puppy.plugins.frontend_emitter.emitter import (
            _recent_events,
            _subscribers,
            emit_event,
        )

        _recent_events.clear()
        _subscribers.clear()
        bad_q = MagicMock()
        bad_q.put_nowait.side_effect = RuntimeError("boom")
        _subscribers.add(bad_q)
        with (
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_max_recent_events",
                return_value=10,
            ),
        ):
            emit_event("err_event")
        _subscribers.clear()
        _recent_events.clear()


class TestSubscribeUnsubscribe:
    def test_subscribe_and_unsubscribe(self):
        from code_puppy.plugins.frontend_emitter.emitter import (
            _subscribers,
            get_subscriber_count,
            subscribe,
            unsubscribe,
        )

        _subscribers.clear()
        with patch(
            "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_queue_size",
            return_value=10,
        ):
            q = subscribe()
        assert get_subscriber_count() == 1
        unsubscribe(q)
        assert get_subscriber_count() == 0

    def test_unsubscribe_nonexistent(self):
        from code_puppy.plugins.frontend_emitter.emitter import (
            _subscribers,
            unsubscribe,
        )

        _subscribers.clear()
        q: asyncio.Queue = asyncio.Queue()
        unsubscribe(q)  # should not raise


class TestGetRecentAndClear:
    def test_get_recent_events(self):
        from code_puppy.plugins.frontend_emitter.emitter import (
            _recent_events,
            _subscribers,
            emit_event,
            get_recent_events,
        )

        _recent_events.clear()
        _subscribers.clear()
        with (
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_max_recent_events",
                return_value=10,
            ),
        ):
            emit_event("a")
        evts = get_recent_events()
        assert len(evts) == 1
        assert evts is not _recent_events  # copy
        _recent_events.clear()

    def test_clear_recent_events(self):
        from code_puppy.plugins.frontend_emitter.emitter import (
            _recent_events,
            _subscribers,
            clear_recent_events,
            emit_event,
        )

        _recent_events.clear()
        _subscribers.clear()
        with (
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_enabled",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_max_recent_events",
                return_value=10,
            ),
        ):
            emit_event("x")
        clear_recent_events()
        assert len(_recent_events) == 0


# ── register_callbacks.py ───────────────────────────────────────────────


class TestSanitizeArgs:
    def test_non_dict(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_args,
        )

        assert _sanitize_args("not a dict") == {}

    def test_string_truncation(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_args,
        )

        result = _sanitize_args({"long": "x" * 1000})
        assert len(result["long"]) <= 503

    def test_primitives(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_args,
        )

        result = _sanitize_args({"i": 1, "f": 2.0, "b": True, "n": None})
        assert result == {"i": 1, "f": 2.0, "b": True, "n": None}

    def test_complex_types(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_args,
        )

        result = _sanitize_args({"lst": [1, 2], "dct": {"a": 1}})
        assert "list[2]" in result["lst"]
        assert "dict[1]" in result["dct"]

    def test_other_types(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_args,
        )

        result = _sanitize_args({"obj": object()})
        assert "object" in result["obj"]


class TestSanitizeEventData:
    def test_none(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_event_data,
        )

        assert _sanitize_event_data(None) is None

    def test_string(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_event_data,
        )

        assert _sanitize_event_data("hello") == "hello"

    def test_string_truncation(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_event_data,
        )

        result = _sanitize_event_data("x" * 2000)
        assert len(result) <= 1003

    def test_int_float_bool(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_event_data,
        )

        assert _sanitize_event_data(42) == 42
        assert _sanitize_event_data(3.14) == 3.14
        assert _sanitize_event_data(True) is True

    def test_dict(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_event_data,
        )

        result = _sanitize_event_data({"a": 1})
        assert result == {"a": 1}

    def test_list(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_event_data,
        )

        result = _sanitize_event_data([1, 2])
        assert result == [1, 2]

    def test_tuple(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_event_data,
        )

        result = _sanitize_event_data((1, 2))
        assert result == [1, 2]

    def test_other(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _sanitize_event_data,
        )

        result = _sanitize_event_data(object())
        assert "object" in result


class TestIsSuccessfulResult:
    def test_none(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _is_successful_result,
        )

        assert _is_successful_result(None) is True

    def test_dict_with_error(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _is_successful_result,
        )

        assert _is_successful_result({"error": "oops"}) is False

    def test_dict_success_false(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _is_successful_result,
        )

        assert _is_successful_result({"success": False}) is False

    def test_dict_ok(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _is_successful_result,
        )

        assert _is_successful_result({"data": 1}) is True

    def test_bool_true(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _is_successful_result,
        )

        assert _is_successful_result(True) is True

    def test_bool_false(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _is_successful_result,
        )

        assert _is_successful_result(False) is False

    def test_other(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _is_successful_result,
        )

        assert _is_successful_result("anything") is True


class TestSummarizeResult:
    def test_none(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _summarize_result,
        )

        assert _summarize_result(None) == "<no result>"

    def test_string(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _summarize_result,
        )

        assert _summarize_result("hello") == "hello"

    def test_dict_with_error(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _summarize_result,
        )

        result = _summarize_result({"error": "bad"})
        assert "Error" in result

    def test_dict_with_message(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _summarize_result,
        )

        assert _summarize_result({"message": "ok"}) == "ok"

    def test_dict_generic(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _summarize_result,
        )

        result = _summarize_result({"a": 1, "b": 2})
        assert "2 keys" in result

    def test_list(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _summarize_result,
        )

        result = _summarize_result([1, 2, 3])
        assert "list[3]" in result

    def test_other(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _summarize_result,
        )

        result = _summarize_result(42)
        assert "42" in result


class TestTruncateString:
    def test_none(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _truncate_string,
        )

        assert _truncate_string(None) is None

    def test_short(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _truncate_string,
        )

        assert _truncate_string("hi", 10) == "hi"

    def test_long(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _truncate_string,
        )

        result = _truncate_string("x" * 20, 10)
        assert len(result) == 10
        assert result.endswith("...")

    def test_non_string(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            _truncate_string,
        )

        assert _truncate_string(123, 100) == "123"


class TestAsyncCallbacks:
    @pytest.mark.asyncio
    async def test_on_pre_tool_call(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            on_pre_tool_call,
        )

        with patch(
            "code_puppy.plugins.frontend_emitter.register_callbacks.emit_event"
        ) as mock_emit:
            await on_pre_tool_call("my_tool", {"arg": "val"})
            mock_emit.assert_called_once()
            assert mock_emit.call_args[0][0] == "tool_call_start"

    @pytest.mark.asyncio
    async def test_on_pre_tool_call_exception(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            on_pre_tool_call,
        )

        with patch(
            "code_puppy.plugins.frontend_emitter.register_callbacks.emit_event",
            side_effect=RuntimeError("boom"),
        ):
            await on_pre_tool_call("t", {})  # should not raise

    @pytest.mark.asyncio
    async def test_on_post_tool_call(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            on_post_tool_call,
        )

        with patch(
            "code_puppy.plugins.frontend_emitter.register_callbacks.emit_event"
        ) as mock_emit:
            await on_post_tool_call("t", {"a": 1}, "result", 100.0)
            mock_emit.assert_called_once()
            assert mock_emit.call_args[0][0] == "tool_call_complete"

    @pytest.mark.asyncio
    async def test_on_post_tool_call_exception(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            on_post_tool_call,
        )

        with patch(
            "code_puppy.plugins.frontend_emitter.register_callbacks.emit_event",
            side_effect=RuntimeError,
        ):
            await on_post_tool_call("t", {}, None, 0.0)

    @pytest.mark.asyncio
    async def test_on_stream_event(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            on_stream_event,
        )

        with patch(
            "code_puppy.plugins.frontend_emitter.register_callbacks.emit_event"
        ) as mock_emit:
            await on_stream_event("text_delta", "hello", "sess-1")
            mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_stream_event_exception(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            on_stream_event,
        )

        with patch(
            "code_puppy.plugins.frontend_emitter.register_callbacks.emit_event",
            side_effect=RuntimeError,
        ):
            await on_stream_event("x", "y")

    @pytest.mark.asyncio
    async def test_on_invoke_agent_with_kwargs(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            on_invoke_agent,
        )

        with patch(
            "code_puppy.plugins.frontend_emitter.register_callbacks.emit_event"
        ) as mock_emit:
            await on_invoke_agent(agent_name="test", session_id="s1", prompt="hi")
            mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_invoke_agent_with_args(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            on_invoke_agent,
        )

        with patch(
            "code_puppy.plugins.frontend_emitter.register_callbacks.emit_event"
        ) as mock_emit:
            await on_invoke_agent("agent_name", "prompt_text")
            mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_invoke_agent_exception(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import (
            on_invoke_agent,
        )

        with patch(
            "code_puppy.plugins.frontend_emitter.register_callbacks.emit_event",
            side_effect=RuntimeError,
        ):
            await on_invoke_agent()


class TestRegister:
    def test_register_function(self):
        from code_puppy.plugins.frontend_emitter.register_callbacks import register

        with patch(
            "code_puppy.plugins.frontend_emitter.register_callbacks.register_callback"
        ):
            register()  # should not raise
