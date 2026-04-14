"""Tests for ChatGPT Codex request payload normalization."""

import json

from code_puppy.chatgpt_codex_client import ChatGPTCodexAsyncClient


def _encode(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _decode(payload: bytes) -> dict:
    return json.loads(payload.decode("utf-8"))


def test_inject_codex_fields_maps_openai_reasoning_effort_alias():
    body = _encode(
        {
            "model": "gpt-5-codex",
            "input": "hello",
            "openai_reasoning_effort": "high",
        }
    )

    updated, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
    assert updated is not None

    payload = _decode(updated)
    assert payload["reasoning"]["effort"] == "high"
    assert payload["reasoning"].get("summary") == "auto"
    assert "openai_reasoning_effort" not in payload


def test_inject_codex_fields_maps_reasoning_effort_alias():
    body = _encode(
        {
            "model": "gpt-5-codex",
            "input": "hello",
            "reasoning_effort": "xhigh",
        }
    )

    updated, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
    assert updated is not None

    payload = _decode(updated)
    assert payload["reasoning"]["effort"] == "xhigh"
    assert "reasoning_effort" not in payload


def test_inject_codex_fields_defaults_reasoning_effort_to_medium():
    body = _encode({"model": "gpt-5-codex", "input": "hello"})

    updated, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
    assert updated is not None

    payload = _decode(updated)
    assert payload["reasoning"]["effort"] == "medium"


def test_inject_codex_fields_preserves_existing_reasoning_summary():
    body = _encode(
        {
            "model": "gpt-5-codex",
            "input": "hello",
            "openai_reasoning_effort": "low",
            "reasoning": {"summary": "detailed"},
        }
    )

    updated, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
    assert updated is not None

    payload = _decode(updated)
    assert payload["reasoning"]["effort"] == "low"
    assert payload["reasoning"]["summary"] == "detailed"


def test_inject_codex_fields_preserves_existing_reasoning_effort_without_alias():
    body = _encode(
        {
            "model": "gpt-5-codex",
            "input": "hello",
            "reasoning": {"effort": "high", "summary": "auto"},
        }
    )

    updated, _ = ChatGPTCodexAsyncClient._inject_codex_fields(body)
    assert updated is not None

    payload = _decode(updated)
    assert payload["reasoning"]["effort"] == "high"
    assert payload["reasoning"]["summary"] == "auto"
