from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from code_puppy.private_inference import (
    _disable_anthropic_thinking,
    _disable_chat_template_thinking,
    run_private_prompt,
)


class _Output:
    pass


def test_chat_template_thinking_is_not_injected_for_standard_providers():
    settings = {"max_tokens": 64}

    _disable_chat_template_thinking(settings)

    assert settings == {"max_tokens": 64}


def test_anthropic_thinking_is_explicitly_disabled():
    settings = {
        "anthropic_thinking": {"type": "adaptive"},
        "extra_body": {
            "output_config": {"effort": "high"},
            "provider_option": "preserved",
        },
    }

    _disable_anthropic_thinking(
        "private-claude",
        {"type": "claude_code", "name": "claude-opus-5"},
        settings,
    )

    assert settings == {
        "anthropic_thinking": {"type": "disabled"},
        "extra_body": {"provider_option": "preserved"},
    }


@pytest.mark.asyncio
async def test_private_prompt_builds_one_toolless_request():
    output = _Output()
    run = AsyncMock(return_value=SimpleNamespace(output=output))
    pydantic_agent = Mock(run=run)
    agent_factory = Mock(return_value=pydantic_agent)
    model = object()
    settings = {
        "extra_body": {
            "chat_template_kwargs": {
                "custom_option": "preserved",
                "enable_thinking": True,
            },
        }
    }

    with (
        patch(
            "code_puppy.private_inference.ModelFactory.load_config",
            return_value={"private-model": {}},
        ),
        patch(
            "code_puppy.private_inference.ModelFactory.get_model",
            return_value=model,
        ) as get_model,
        patch(
            "code_puppy.private_inference.make_model_settings",
            return_value=settings,
        ) as make_settings,
        patch("code_puppy.private_inference.Agent", agent_factory),
    ):
        result = await run_private_prompt(
            model_name="private-model",
            instructions="classify",
            prompt="payload",
            output_type=_Output,
            model_settings_overrides={"reasoning_effort": "none"},
            max_tokens=32,
        )

    assert result is output
    get_model.assert_called_once_with("private-model", {"private-model": {}})
    make_settings.assert_called_once_with(
        "private-model",
        max_tokens=32,
        overrides={"reasoning_effort": "none"},
    )
    agent_factory.assert_called_once_with(
        model=model,
        instructions="classify",
        output_type=_Output,
        retries=0,
        toolsets=[],
        model_settings={
            "extra_body": {
                "chat_template_kwargs": {
                    "custom_option": "preserved",
                    "enable_thinking": False,
                }
            }
        },
    )
    run.assert_awaited_once()
    assert run.await_args.args == ("payload",)
    assert run.await_args.kwargs["usage_limits"].request_limit == 1


@pytest.mark.asyncio
async def test_private_prompt_rejects_unknown_model_before_agent_creation():
    with (
        patch("code_puppy.private_inference.ModelFactory.load_config", return_value={}),
        patch("code_puppy.private_inference.Agent") as agent_factory,
        pytest.raises(ValueError, match="Unknown private-inference model"),
    ):
        await run_private_prompt(
            model_name="missing",
            instructions="classify",
            prompt="payload",
            output_type=_Output,
        )

    agent_factory.assert_not_called()
