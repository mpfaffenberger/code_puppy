import json
from unittest.mock import patch

from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.claude_cache_client import (
    ClaudeCacheAsyncClient,
    _inject_cache_control_in_payload,
)
from code_puppy.prompt_composition import (
    DYNAMIC_PROMPT_BOUNDARY,
    PromptSections,
    split_prompt_sections,
)


def test_prompt_sections_round_trip():
    rendered = PromptSections("stable", "volatile").render()

    assert DYNAMIC_PROMPT_BOUNDARY in rendered
    assert split_prompt_sections(rendered) == PromptSections("stable", "volatile")


def test_dynamic_fragments_are_cached_until_invalidated():
    agent = CodePuppyAgent()
    with patch(
        "code_puppy.callbacks.on_load_prompt", side_effect=[["first"], ["second"]]
    ) as loader:
        first = agent.get_full_system_prompt()
        second = agent.get_full_system_prompt()
        agent.invalidate_dynamic_prompt()
        third = agent.get_full_system_prompt()

    assert "first" in first
    assert second == first
    assert "second" in third
    assert loader.call_count == 2


def test_clear_history_invalidates_dynamic_prompt():
    agent = CodePuppyAgent()
    agent._dynamic_prompt_cache = "cached"
    agent._dynamic_prompt_cwd = "cwd"

    agent.clear_message_history()

    assert agent._dynamic_prompt_cache is None
    assert agent._dynamic_prompt_cwd is None


def test_anthropic_payload_caches_only_stable_system_prefix():
    prompt = PromptSections("stable instructions", "cwd=/tmp").render()
    payload = {"system": prompt}

    _inject_cache_control_in_payload(payload)

    assert payload["system"] == [
        {
            "type": "text",
            "text": "stable instructions",
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": "cwd=/tmp"},
    ]


def test_raw_http_payload_removes_boundary_marker():
    prompt = PromptSections("stable", "dynamic").render()
    body = json.dumps({"system": prompt}).encode()

    result = ClaudeCacheAsyncClient._inject_cache_control(body)

    assert result is not None
    decoded = json.loads(result)
    assert DYNAMIC_PROMPT_BOUNDARY not in json.dumps(decoded)
    assert "cache_control" in decoded["system"][0]
    assert "cache_control" not in decoded["system"][1]
