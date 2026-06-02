"""Focused tests for WebSocket history utility helpers."""

from __future__ import annotations

from code_puppy.api.ws.history_utils import (
    build_enhanced_history,
    estimate_total_tokens,
    extract_message_timestamp,
)


class _MsgWithTimestamp:
    def __init__(self, timestamp):
        self.timestamp = timestamp


class _GoodAgent:
    def estimate_tokens_for_message(self, msg):
        return len(str(msg))


class _BadAgent:
    def estimate_tokens_for_message(self, msg):
        raise RuntimeError("boom")


def test_extract_message_timestamp_prefers_dict_timestamp_fields():
    assert (
        extract_message_timestamp({"timestamp": "2024-01-02T03:04:05"}, "fallback")
        == "2024-01-02T03:04:05"
    )
    assert (
        extract_message_timestamp({"ts": "2024-02-03T04:05:06"}, "fallback")
        == "2024-02-03T04:05:06"
    )


def test_extract_message_timestamp_uses_object_attribute_and_fallback():
    assert (
        extract_message_timestamp(_MsgWithTimestamp("2024-03-04T05:06:07"), "fallback")
        == "2024-03-04T05:06:07"
    )
    assert extract_message_timestamp(object(), "fallback") == "fallback"


def test_build_enhanced_history_backfills_attachment_metadata_on_user_message():
    history = [
        {"role": "user", "content": "expanded with file contents"},
        {"role": "assistant", "content": "done"},
    ]

    enhanced = build_enhanced_history(
        history,
        agent_name_meta="code-puppy",
        model_name_meta="gpt-test",
        original_user_message="clean user text",
        attachment_metadata=[{"name": "a.txt", "path": "/tmp/a.txt"}],
    )

    assert enhanced[0]["clean_content"] == "clean user text"
    assert enhanced[0]["attachments"] == [{"name": "a.txt", "path": "/tmp/a.txt"}]
    assert enhanced[1]["msg"] == {"role": "assistant", "content": "done"}


def test_build_enhanced_history_preserves_pre_wrapped_entries():
    wrapped = {
        "msg": {"role": "user", "content": "hi"},
        "agent": "existing-agent",
        "model": "existing-model",
        "ts": "2024-01-01T00:00:00",
    }

    enhanced = build_enhanced_history(
        [wrapped],
        agent_name_meta="new-agent",
        model_name_meta="new-model",
        original_user_message="ignored",
        attachment_metadata=[],
    )

    assert enhanced == [wrapped]


def test_estimate_total_tokens_sums_wrapped_messages():
    enhanced = [{"msg": "abc"}, {"msg": "de"}]
    assert estimate_total_tokens(enhanced, _GoodAgent()) == 5


def test_estimate_total_tokens_returns_zero_on_estimator_failure():
    enhanced = [{"msg": "abc"}]
    assert estimate_total_tokens(enhanced, _BadAgent()) == 0
