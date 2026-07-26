"""One-shot, history-free model query backing the `/btw` command.

Deliberately minimal (YAGNI): a throwaway pydantic_ai Agent with no
tools, no message history, and a tiny system prompt. The main agent's
context window never sees any of this — that's the whole point.

Threading note: ``handle_command`` executes synchronously *inside* the
already-running main event loop, so we can't ``asyncio.run`` on the
main thread. Same escape hatch as the ``steer_queue`` menu: hop to a
worker thread and give it its own loop.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging

logger = logging.getLogger(__name__)

QUERY_TIMEOUT_S = 180.0

_INSTRUCTIONS = (
    "You are answering a quick side question ('/btw') a developer asked "
    "mid-coding-session. Answer directly and concisely — a few sentences "
    "or a short snippet is ideal. No preamble, no follow-up questions."
)


def resolve_model_name() -> str | None:
    """Current agent's pinned model if any, else the global model."""
    try:
        from code_puppy.agents.agent_manager import get_current_agent

        pinned = get_current_agent().get_model_name()
        if pinned:
            return pinned
    except Exception:
        logger.debug("btw: agent model lookup failed", exc_info=True)
    try:
        from code_puppy.config import get_global_model_name

        return get_global_model_name()
    except Exception:
        logger.debug("btw: global model lookup failed", exc_info=True)
        return None


async def _ask(model_name: str, question: str) -> str:
    """Single-turn query against a fresh Agent. Raises on failure."""
    from pydantic_ai import Agent, UsageLimits

    from code_puppy.model_factory import ModelFactory, make_model_settings
    from code_puppy.model_utils import prepare_prompt_for_model

    models_config = ModelFactory.load_config()
    if model_name not in models_config:
        raise ValueError(f"model {model_name!r} not present in the model config")

    model = ModelFactory.get_model(model_name, models_config)
    prepared = prepare_prompt_for_model(
        model_name,
        _INSTRUCTIONS,
        question,
        prepend_system_to_user=True,
    )
    agent = Agent(
        model=model,
        instructions=prepared.instructions,
        retries=1,
        model_settings=make_model_settings(model_name),
    )
    result = await agent.run(
        prepared.user_prompt,
        usage_limits=UsageLimits(request_limit=3),
    )
    return str(result.output)


def ask_blocking(
    model_name: str,
    question: str,
    timeout_s: float = QUERY_TIMEOUT_S,
) -> str:
    """Run the one-shot query on a worker thread; block until answered."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(_ask(model_name, question)))
        return future.result(timeout=timeout_s)


__all__ = ["QUERY_TIMEOUT_S", "ask_blocking", "resolve_model_name"]
