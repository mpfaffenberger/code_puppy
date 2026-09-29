"""Private, one-shot model inference without the conversational agent runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TypeVar

from pydantic_ai import Agent, UsageLimits

from code_puppy.model_factory import (
    ModelFactory,
    _is_anthropic_model,
    make_model_settings,
)

OutputT = TypeVar("OutputT")


def _disable_chat_template_thinking(model_settings: dict[str, object]) -> None:
    """Disable an already-configured vLLM/SGLang thinking switch in place.

    ``chat_template_kwargs`` is not part of the OpenAI API.  Only preserve and
    override it when model configuration already opted into that extension;
    injecting it for providers such as ChatGPT OAuth causes a 400 response.
    """
    configured_extra_body = model_settings.get("extra_body")
    if not isinstance(configured_extra_body, dict):
        return

    configured_chat_template = configured_extra_body.get("chat_template_kwargs")
    if not isinstance(configured_chat_template, dict):
        return

    extra_body = dict(configured_extra_body)
    chat_template_kwargs = dict(configured_chat_template)
    chat_template_kwargs["enable_thinking"] = False
    extra_body["chat_template_kwargs"] = chat_template_kwargs
    model_settings["extra_body"] = extra_body


def _disable_anthropic_thinking(
    model_name: str,
    model_config: dict[str, object],
    model_settings: dict[str, object],
) -> None:
    """Explicitly override thinking embedded in Anthropic model defaults."""
    if not _is_anthropic_model(model_name, model_config):
        return

    model_settings["anthropic_thinking"] = {"type": "disabled"}

    # Plugin-created Anthropic models carry their own default settings. Agent
    # settings are merged shallowly over those defaults, so explicitly replace
    # extra_body as well or a model-level output_config.effort survives after
    # thinking is disabled.
    extra_body = dict(model_settings.get("extra_body") or {})
    output_config = dict(extra_body.get("output_config") or {})
    output_config.pop("effort", None)
    if output_config:
        extra_body["output_config"] = output_config
    else:
        extra_body.pop("output_config", None)
    model_settings["extra_body"] = extra_body


async def run_private_prompt(
    *,
    model_name: str,
    instructions: str,
    prompt: str,
    output_type: type[OutputT],
    model_settings_overrides: Mapping[str, object] | None = None,
    max_tokens: int = 256,
    timeout_seconds: float = 30,
) -> OutputT:
    """Run one structured request without agent hooks, history, tools, or output.

    Callers own policy for failures: safety checks may fail closed while
    convenience classifiers may fail open.
    """
    models_config = ModelFactory.load_config()
    if model_name not in models_config:
        raise ValueError(f"Unknown private-inference model: {model_name}")

    model = ModelFactory.get_model(model_name, models_config)
    model_settings = make_model_settings(
        model_name,
        max_tokens=max_tokens,
        overrides=dict(model_settings_overrides or {}),
    )
    _disable_chat_template_thinking(model_settings)
    _disable_anthropic_thinking(
        model_name,
        models_config[model_name],
        model_settings,
    )
    agent = Agent(
        model=model,
        instructions=instructions,
        output_type=output_type,
        retries=0,
        toolsets=[],
        model_settings=model_settings,
    )
    async with asyncio.timeout(timeout_seconds):
        result = await agent.run(
            prompt,
            usage_limits=UsageLimits(request_limit=1),
        )
    return result.output


__all__ = ["run_private_prompt"]
