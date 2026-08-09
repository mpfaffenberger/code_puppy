"""Shared OAuth paste-back parser tests."""

import pytest

from code_puppy.plugins.oauth_pasteback import parse_oauth_callback_input


@pytest.mark.parametrize(
    "raw, expected_code, expected_state",
    [
        (
            "http://localhost:1455/auth/callback?"
            "code=abc123&scope=openid+profile+email+offline_access&state=state456",
            "abc123",
            "state456",
        ),
        (
            "http://localhost:8765/callback?code=claude_code&state=claude_state",
            "claude_code",
            "claude_state",
        ),
        ("code=query_code&state=query_state", "query_code", "query_state"),
        ("CODE123#STATE456", "CODE123", "STATE456"),
        ("CODE123 STATE456", "CODE123", "STATE456"),
        ("CODE123", "CODE123", None),
    ],
    ids=[
        "full_openai_callback_url",
        "full_claude_callback_url",
        "raw_query_string",
        "claude_hash_format",
        "space_separated",
        "bare_code",
    ],
)
def test_parse_successful_inputs(raw, expected_code, expected_state):
    parsed = parse_oauth_callback_input(raw)

    assert parsed.code == expected_code
    assert parsed.state == expected_state
    assert parsed.error is None


def test_parse_oauth_error_url():
    parsed = parse_oauth_callback_input(
        "http://localhost:1455/auth/callback?"
        "error=access_denied&error_description=User%20denied"
    )

    assert parsed.error == "access_denied"
    assert parsed.error_message == "access_denied: User denied"


def test_empty_input_raises():
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_oauth_callback_input("")
