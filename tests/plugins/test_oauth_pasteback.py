"""Shared OAuth paste-back parser tests."""

import pytest

from code_puppy.plugins.oauth_pasteback import parse_oauth_callback_input


def test_parse_full_openai_callback_url():
    parsed = parse_oauth_callback_input(
        "http://localhost:1455/auth/callback?"
        "code=abc123&scope=openid+profile+email+offline_access&state=state456"
    )

    assert parsed.code == "abc123"
    assert parsed.state == "state456"
    assert parsed.error is None


def test_parse_full_claude_callback_url():
    parsed = parse_oauth_callback_input(
        "http://localhost:8765/callback?code=claude_code&state=claude_state"
    )

    assert parsed.code == "claude_code"
    assert parsed.state == "claude_state"


def test_parse_raw_query_string():
    parsed = parse_oauth_callback_input("code=query_code&state=query_state")

    assert parsed.code == "query_code"
    assert parsed.state == "query_state"


def test_parse_claude_hash_format():
    parsed = parse_oauth_callback_input("CODE123#STATE456")

    assert parsed.code == "CODE123"
    assert parsed.state == "STATE456"


def test_parse_space_separated_code_and_state():
    parsed = parse_oauth_callback_input("CODE123 STATE456")

    assert parsed.code == "CODE123"
    assert parsed.state == "STATE456"


def test_parse_bare_code():
    parsed = parse_oauth_callback_input("CODE123")

    assert parsed.code == "CODE123"
    assert parsed.state is None


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
