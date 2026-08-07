from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RequestUsage

from code_puppy.openai_prompt_cache import (
    CACHE_ANCHOR,
    CacheAwareChatModel,
    CacheAwareResponsesModel,
    add_cache_boundary,
    apply_cache_key,
    get_model_classes,
    get_request_path,
    preserve_openai_cache_tokens,
    supports_explicit_breakpoint,
)
from code_puppy.agents._builder import (
    _full_system_prompt_for_model,
    build_pydantic_agent,
)


@pytest.fixture
def openai_provider():
    client = AsyncOpenAI(
        api_key="test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None)),
    )
    return OpenAIProvider(openai_client=client)


@pytest.mark.asyncio
async def test_responses_preserves_instructions_and_marks_one_boundary(
    openai_provider,
):
    model = CacheAwareResponsesModel("gpt-5.6-sol", provider=openai_provider)
    messages = [
        ModelRequest(
            parts=[UserPromptPart(add_cache_boundary("current task"))],
            instructions="developer instructions",
        )
    ]

    instructions, mapped = await model._map_messages(
        messages, {}, ModelRequestParameters()
    )

    assert instructions == "developer instructions"
    content = mapped[0]["content"]
    assert content[0]["text"] == CACHE_ANCHOR
    assert content[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert content[1]["text"] == "current task"
    assert sum("prompt_cache_breakpoint" in item for item in content) == 1


@pytest.mark.asyncio
async def test_chat_preserves_system_message_and_attachment_order(openai_provider):
    model = CacheAwareChatModel("gpt-5.6", provider=openai_provider)
    attachment = SimpleNamespace(name="attachment")
    payload = add_cache_boundary(["current task", attachment])
    assert payload[:3] == [CACHE_ANCHOR, payload[1], "current task"]
    assert payload[3] is attachment

    # Use strings for the mapper request; attachment ordering itself is covered
    # above without constructing a provider-specific binary content object.
    messages = [
        ModelRequest(
            parts=[
                SystemPromptPart("system instructions"),
                UserPromptPart(add_cache_boundary("current task")),
            ]
        )
    ]
    mapped = await model._map_messages(messages, ModelRequestParameters())

    assert mapped[0] == {"role": "system", "content": "system instructions"}
    content = mapped[1]["content"]
    assert content[0]["text"] == CACHE_ANCHOR
    assert content[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert content[1]["text"] == "current task"


@pytest.mark.parametrize(
    ("details", "expected_read", "expected_write"),
    [
        (SimpleNamespace(cached_tokens=900, cache_write_tokens=250), 900, 250),
        (SimpleNamespace(cached_tokens=0, cache_write_tokens=0), 0, 0),
        (SimpleNamespace(), None, None),
    ],
)
def test_cache_usage_preserves_values_zero_and_missing(
    details, expected_read, expected_write
):
    mapped = RequestUsage()
    raw = SimpleNamespace(usage=SimpleNamespace(input_tokens_details=details))

    preserve_openai_cache_tokens(mapped, raw)

    if expected_read is None:
        assert "cache_read_tokens" not in mapped.details
    else:
        assert mapped.cache_read_tokens == expected_read
        assert mapped.details["cache_read_tokens"] == expected_read
    if expected_write is None:
        assert "cache_write_tokens" not in mapped.details
    else:
        assert mapped.cache_write_tokens == expected_write
        assert mapped.details["cache_write_tokens"] == expected_write


def test_cache_key_is_stable_opaque_and_scoped_by_provider_model():
    config = {"type": "openai", "name": "gpt-5.6-sol"}
    first, repeated, different, alias = {}, {}, {}, {}

    assert apply_cache_key(first, "fast", config, "primary-agent")
    assert apply_cache_key(repeated, "fast", config, "primary-agent")
    assert apply_cache_key(different, "fast", config, "reviewer")
    assert apply_cache_key(alias, "deep", config, "primary-agent")

    assert first["openai_prompt_cache_key"] == repeated["openai_prompt_cache_key"]
    assert first["openai_prompt_cache_key"] == alias["openai_prompt_cache_key"]
    assert first["openai_prompt_cache_key"] != different["openai_prompt_cache_key"]
    assert "primary-agent" not in first["openai_prompt_cache_key"]


def test_model_settings_apply_cache_key_for_provider_model_alias():
    from code_puppy.model_factory import make_model_settings

    config = {"fast": {"type": "custom_openai_responses", "name": "gpt-5.6-sol"}}
    with patch(
        "code_puppy.model_factory.ModelFactory.load_config", return_value=config
    ):
        settings = make_model_settings("fast", prompt_cache_scope="code-puppy")

    assert settings["openai_prompt_cache_key"].startswith("code-puppy:")
    assert "openai_prompt_cache_retention" not in settings


def test_model_class_selection_is_gpt_5_6_only():
    chat, responses = get_model_classes(
        "gpt-5.6-sol", {"type": "openai", "name": "gpt-5.6-sol"}
    )
    assert chat is CacheAwareChatModel
    assert responses is CacheAwareResponsesModel

    stock_chat, stock_responses = MagicMock(), MagicMock()
    assert get_model_classes(
        "gpt-5.5",
        {"type": "openai", "name": "gpt-5.5"},
        stock_chat,
        stock_responses,
    ) == (stock_chat, stock_responses)


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({"type": "openai", "name": "gpt-5.6-sol"}, True),
        ({"type": "chatgpt_oauth", "name": "gpt-5.6-sol"}, False),
        (
            {
                "type": "chatgpt_oauth",
                "name": "gpt-5.6-sol",
                "prompt_cache_breakpoint_enabled": True,
            },
            True,
        ),
    ],
)
def test_explicit_breakpoint_is_provider_gated(config, expected):
    assert supports_explicit_breakpoint("codex-gpt-5.6-sol", config) is expected


@pytest.mark.parametrize(
    ("alias", "config", "expected"),
    [
        ("codex-gpt-5.6-sol", {"type": "openai"}, "responses"),
        ("gpt-5.6-sol", {"type": "openai"}, "chat_completions"),
        ("alias", {"type": "chatgpt_oauth"}, "responses"),
        ("alias", {"type": "anthropic"}, "provider_default"),
    ],
)
def test_request_path_is_centralized(alias, config, expected):
    assert get_request_path(alias, config) == expected


def test_gpt_5_6_instructions_replace_only_the_runtime_identity():
    def agent(instance_id: str):
        runtime_id = f"code-puppy-{instance_id}"
        identity = f"\n\nYour ID is `{runtime_id}`."
        return SimpleNamespace(
            name="code-puppy",
            get_identity=lambda: runtime_id,
            get_full_system_prompt=lambda: "authored instructions" + identity,
            get_identity_prompt=lambda: identity,
        )

    first = _full_system_prompt_for_model(agent("random-one"), "gpt-5.6-sol")
    second = _full_system_prompt_for_model(agent("random-two"), "gpt-5.6-sol")

    assert first == second == "authored instructions\n\nYour ID is `code-puppy`."


def test_two_agent_builds_use_same_logical_cache_scope():
    def agent():
        value = MagicMock()
        value.name = "code-puppy"
        value.get_model_name.return_value = "codex-gpt-5.6-sol"
        value.get_available_tools.return_value = []
        return value

    built = [SimpleNamespace(_tools={}) for _ in range(4)]
    with (
        patch("code_puppy.agents._builder.ModelFactory.load_config", return_value={}),
        patch(
            "code_puppy.agents._builder.load_model_with_fallback",
            return_value=(MagicMock(), "codex-gpt-5.6-sol"),
        ),
        patch(
            "code_puppy.agents._builder._assemble_instructions",
            return_value="instructions",
        ),
        patch("code_puppy.agents._builder.load_mcp_servers", return_value=[]),
        patch("code_puppy.agents._builder.make_model_settings") as settings,
        patch("code_puppy.agents._builder.make_history_processor"),
        patch("code_puppy.agents._builder.make_steer_history_processor"),
        patch("code_puppy.agents._builder.PydanticAgent", side_effect=built),
        patch("code_puppy.tools.register_tools_for_agent"),
        patch(
            "code_puppy.agents._builder.on_wrap_pydantic_agent",
            side_effect=lambda _agent, pydantic_agent, **_kwargs: pydantic_agent,
        ),
    ):
        build_pydantic_agent(agent())
        build_pydantic_agent(agent())

    assert settings.call_args_list == [
        call("codex-gpt-5.6-sol", prompt_cache_scope="code-puppy"),
        call("codex-gpt-5.6-sol", prompt_cache_scope="code-puppy"),
    ]
