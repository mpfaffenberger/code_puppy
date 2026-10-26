"""Provider identity: model-key prefixes and Anthropic-family provider naming."""

from __future__ import annotations

import pytest

from code_puppy.provider_identity import (
    make_anthropic_provider,
    resolve_provider_identity,
)


@pytest.mark.parametrize(
    "key, provider",
    [
        ("claude-code-claude-opus-4-7", "claude_code"),
        ("codex-gpt-5", "chatgpt"),
        ("chatgpt-gpt-5", "chatgpt"),
        ("azure-openai-gpt-4o", "azure_openai"),
        ("openrouter-some-model", "openrouter"),
    ],
)
def test_plugin_model_key_prefixes_map_to_their_provider(key, provider):
    assert resolve_provider_identity(key, {}) == provider


def test_non_anthropic_name_gets_an_aliased_anthropic_provider():
    plain = make_anthropic_provider("anthropic", api_key="k")
    aliased = make_anthropic_provider("claude_code", api_key="k")
    assert plain.name == "anthropic"
    assert aliased.name == "claude_code"
