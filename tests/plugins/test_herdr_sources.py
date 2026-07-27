"""Tests for the herdr ``sources`` adapter (code-puppy -> report payloads).

These cover the fail-soft contract: every adapter returns a safe fallback
(never raises) and produces static-keyed, string-valued, length-capped
payloads suitable for herdr.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import code_puppy.plugins.herdr.sources as sources


# --- compact token formatting ---------------------------------------------


def test_compact_tokens_small_medium_large():
    assert sources._compact_tokens(0) == "0"
    assert sources._compact_tokens(999) == "999"
    assert sources._compact_tokens(48_200) == "48k"
    assert sources._compact_tokens(200_000) == "200k"
    assert sources._compact_tokens(2_500_000) == "2M"


def test_clip_caps_value_length():
    assert sources._clip("x" * 500) == "x" * sources._MAX_VALUE_LEN
    assert sources._clip(42) == "42"


# --- current_tokens_payload -----------------------------------------------


def _fake_usage(percent, total, capacity):
    u = MagicMock()
    u.percent = percent
    u.total_tokens = total
    u.capacity = capacity
    return u


def test_tokens_payload_has_static_string_keys():
    with (
        patch(
            "code_puppy.token_usage.get_current_usage",
            return_value=_fake_usage(42.4, 48_200, 200_000),
        ),
        patch.object(sources, "_current_model", return_value="claude-sonnet-4-5"),
    ):
        payload = sources.current_tokens_payload()
    assert payload == {
        "context": "42%",
        "tokens": "48k/200k",
        "model": "claude-sonnet-4-5",
    }
    assert all(isinstance(v, str) for v in payload.values())


def test_tokens_payload_omits_model_when_unknown():
    with (
        patch(
            "code_puppy.token_usage.get_current_usage",
            return_value=_fake_usage(1.0, 1000, 200_000),
        ),
        patch.object(sources, "_current_model", return_value=None),
    ):
        payload = sources.current_tokens_payload()
    assert "model" not in payload
    assert payload["context"] == "1%"
    assert payload["tokens"] == "1k/200k"


def test_tokens_payload_none_when_usage_unavailable():
    with patch("code_puppy.token_usage.get_current_usage", return_value=None):
        assert sources.current_tokens_payload() is None


def test_tokens_payload_swallows_exceptions():
    with patch(
        "code_puppy.token_usage.get_current_usage",
        side_effect=RuntimeError("boom"),
    ):
        assert sources.current_tokens_payload() is None


def test_tokens_payload_clips_absurd_model_name():
    with (
        patch(
            "code_puppy.token_usage.get_current_usage",
            return_value=_fake_usage(50.0, 100_000, 200_000),
        ),
        patch.object(sources, "_current_model", return_value="m" * 999),
    ):
        payload = sources.current_tokens_payload()
    assert len(payload["model"]) == sources._MAX_VALUE_LEN


# --- current_session_ref --------------------------------------------------


def test_session_ref_returns_name_and_path():
    with (
        patch(
            "code_puppy.config.get_current_session_name",
            return_value="auto_session_x",
        ),
        patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/autosaves"),
    ):
        ref = sources.current_session_ref()
    assert ref is not None
    name, path = ref
    assert name == "auto_session_x"
    assert path.endswith("auto_session_x.pkl")


def test_session_ref_none_when_name_empty():
    with patch("code_puppy.config.get_current_session_name", return_value=""):
        assert sources.current_session_ref() is None


def test_session_ref_swallows_exceptions():
    with patch(
        "code_puppy.config.get_current_session_name",
        side_effect=RuntimeError("nope"),
    ):
        assert sources.current_session_ref() is None


# --- activity_message -----------------------------------------------------


def test_activity_message_humanizes_tool_name():
    assert sources.activity_message("read_file") == "running read file"
    assert sources.activity_message("agent_run_shell_command") == (
        "running agent run shell command"
    )


def test_activity_message_falls_back_on_empty():
    assert sources.activity_message("") == "running tool"
    assert sources.activity_message("   ") == "running tool"
