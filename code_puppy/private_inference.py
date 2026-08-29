"""Private, one-shot model inference without the conversational agent runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TypeVar

from pydantic_ai import Agent, UsageLimits

from code_puppy.model_factory import ModelFactory, make_model_settings

OutputT = TypeVar("OutputT")


def _disable_chat_template_thinking(model_settings: dict[str, object]) -> None:
    """Force the vLLM/SGLang chat-template thinking switch off in place."""
    extra_body = dict(model_settings.get("extra_body") or {})
    chat_template_kwargs = dict(extra_body.get("chat_template_kwargs") or {})
    chat_template_kwargs["enable_thinking"] = False
    extra_body["chat_template_kwargs"] = chat_template_kwargs
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
