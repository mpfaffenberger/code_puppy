"""Shared prompt and lifecycle handling for direct auxiliary model calls."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from code_puppy.callbacks import (
    auxiliary_agent_run_context,
    on_agent_run_end,
    on_agent_run_start,
)

logger = logging.getLogger(__name__)

ResultT = TypeVar("ResultT")


def _status_for_error(error: BaseException | None) -> str:
    if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)):
        return "cancelled"
    return "failed" if error is not None else "completed"


async def _finish_lifecycle(
    *,
    agent_name: str,
    model_name: str,
    session_id: str | None,
    response_text: str | None,
    error: BaseException | None,
) -> None:
    """Publish a terminal lifecycle event without changing call behavior."""
    try:
        with auxiliary_agent_run_context():
            await on_agent_run_end(
                agent_name=agent_name,
                model_name=model_name,
                session_id=session_id,
                success=error is None,
                error=error,  # type: ignore[arg-type]
                response_text=response_text,
                metadata={
                    "status": _status_for_error(error),
                    "auxiliary_model_call": True,
                },
            )
    except Exception:
        logger.exception("Auxiliary agent_run_end callback failed")


async def run_auxiliary_model_call(
    *,
    agent_name: str,
    model_name: str,
    session_id: str | None,
    prompt: str,
    call: Callable[[str], Awaitable[ResultT]],
    response_text: Callable[[ResultT], str | None],
    result_error: Callable[[ResultT], str | None] | None = None,
) -> ResultT:
    """Run one direct model entry point with prompt and lifecycle hooks."""
    from code_puppy.agents._runtime import apply_attachment_free_user_prompt_submit

    with auxiliary_agent_run_context():
        submitted_prompt = await apply_attachment_free_user_prompt_submit(
            prompt, session_id
        )
    try:
        with auxiliary_agent_run_context():
            await on_agent_run_start(
                agent_name=agent_name,
                model_name=model_name,
                session_id=session_id,
            )
    except Exception:
        logger.exception("Auxiliary agent_run_start callback failed")

    try:
        result = await call(submitted_prompt)
    except BaseException as exc:
        await _finish_lifecycle(
            agent_name=agent_name,
            model_name=model_name,
            session_id=session_id,
            response_text=None,
            error=exc,
        )
        raise

    reported_error = result_error(result) if result_error is not None else None
    error = RuntimeError(reported_error) if reported_error else None
    await _finish_lifecycle(
        agent_name=agent_name,
        model_name=model_name,
        session_id=session_id,
        response_text=response_text(result),
        error=error,
    )
    return result


__all__ = ["run_auxiliary_model_call"]
