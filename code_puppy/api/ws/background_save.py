"""Background agent result persistence for WebSocket chat sessions.

When a user switches sessions or disconnects while the agent is running, the
agent is allowed to finish in the background.  This module provides a single
reusable coroutine — ``save_agent_result_in_background`` — that:

1. Awaits the agent task.
2. Syncs completed messages onto the agent instance.
3. Checks the session still exists (guards against resurrecting deleted sessions).
4. Persists the result to SQLite via ``write_turn_to_sqlite``.

All three original call-sites (switch, disconnect, runtime-error) are
collapsed here, eliminating ~363 lines of duplicated closure code.

Usage
-----
::

    from code_puppy.api.ws.background_save import (
        fire_and_track,
        save_agent_result_in_background,
    )

    fire_and_track(
        save_agent_result_in_background(
            agent_task=active_agent_task,
            session_id=session_id,
            ctx=ctx,
            agent=agent,
            agent_name=agent_name,
            model_name=model_name,
            title=session_title,
            working_directory=session_working_directory,
            pinned=session_pinned,
            label="switch",  # "switch" | "disconnect" | "runtime"
        )
    )
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

from code_puppy.api.db.queries import session_exists, write_turn_to_sqlite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Task registry — prevents fire-and-forget tasks from being GC'd mid-flight.
# ---------------------------------------------------------------------------

_BACKGROUND_TASKS: set[asyncio.Task] = set()


def fire_and_track(coro: Any) -> asyncio.Task:
    """Spawn *coro* as a tracked background Task.

    The task is kept alive in ``_BACKGROUND_TASKS`` until it completes,
    preventing it from being garbage-collected before it finishes.
    """
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


# ---------------------------------------------------------------------------
# Core background-save coroutine
# ---------------------------------------------------------------------------


async def save_agent_result_in_background(
    *,
    agent_task: asyncio.Task | None,
    session_id: str,
    ctx: Any,  # SessionContext | None
    agent: Any,  # code_puppy Agent instance
    agent_name: str,
    model_name: str,
    title: str,
    working_directory: str,
    pinned: bool,
    label: str = "bg",
) -> None:
    """Await *agent_task*, then persist the result to SQLite.

    Parameters
    ----------
    agent_task:
        The running ``run_with_mcp`` asyncio Task.  ``None`` is a safe no-op.
    session_id:
        The session whose messages should be persisted.
    ctx:
        The ``SessionContext`` snapshot at time of the switch/disconnect.
        May be ``None``; used for ``created_at`` and token estimation.
    agent:
        Agent instance attached to the session.
    agent_name / model_name / title / working_directory / pinned:
        Session metadata — snapshotted by the caller before state changes.
    label:
        Short string used in log messages: ``"switch"``, ``"disconnect"``,
        or ``"runtime"``.
    """
    if agent_task is None:
        return

    try:
        # ------------------------------------------------------------------
        # 1. Await the in-flight agent task.
        # ------------------------------------------------------------------
        try:
            result = await agent_task
        except asyncio.CancelledError:
            logger.debug("[BG:%s] Agent task was cancelled (%s)", session_id, label)
            return
        except Exception as exc:
            logger.warning("[BG:%s] Agent task failed (%s): %s", session_id, label, exc)
            return

        if result is None:
            return

        # ------------------------------------------------------------------
        # 2. Sync completed messages back onto the agent instance.
        # ------------------------------------------------------------------
        try:
            all_msgs = result.all_messages()
            agent.set_message_history(all_msgs)
        except Exception as exc:
            logger.warning(
                "[BG:%s] Could not extract messages from result (%s): %s",
                session_id,
                label,
                exc,
            )
            # Don't bail — get_message_history() may still hold a partial history.

        history = agent.get_message_history()
        if not history:
            logger.debug(
                "[BG:%s] Empty history after completion (%s) — nothing to save",
                session_id,
                label,
            )
            return

        # ------------------------------------------------------------------
        # 3. Guard: skip write if the session was deleted between task start
        #    and completion (avoids resurrecting a deliberately deleted session).
        # ------------------------------------------------------------------
        try:
            if not await session_exists(session_id):
                logger.info(
                    "[BG:%s] Session deleted before background save (%s) — skipping",
                    session_id,
                    label,
                )
                return
        except Exception as exc:
            logger.warning(
                "[BG:%s] session_exists check failed (%s): %s — proceeding anyway",
                session_id,
                label,
                exc,
            )

        # ------------------------------------------------------------------
        # 4. Build enhanced history wrappers.
        #    Pre-wrapped dicts (legacy or in-memory system-message injections)
        #    pass through unchanged; bare ModelMessage objects get wrapped.
        # ------------------------------------------------------------------
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        enhanced_history: list[dict[str, Any]] = []
        for msg in history:
            if isinstance(msg, dict) and "msg" in msg:
                enhanced_history.append(msg)
            else:
                enhanced_history.append(
                    {
                        "msg": msg,
                        "agent": agent_name,
                        "model": model_name,
                        "ts": now_iso,
                    }
                )

        # ------------------------------------------------------------------
        # 5. Compute token count from the completed history.
        #    The three old closures hard-coded 0; we compute it properly here.
        # ------------------------------------------------------------------
        total_tokens = 0
        try:
            for item in enhanced_history:
                msg_obj = (
                    item["msg"] if isinstance(item, dict) and "msg" in item else item
                )
                total_tokens += agent.estimate_tokens_for_message(msg_obj)
        except Exception:
            total_tokens = 0

        # ------------------------------------------------------------------
        # 6. Resolve created_at safely — ctx may lack the attribute in tests.
        # ------------------------------------------------------------------
        ctx_created_at = getattr(ctx, "created_at", None)
        created_at = (
            ctx_created_at.isoformat() if ctx_created_at is not None else now_iso
        )

        # ------------------------------------------------------------------
        # 7. Persist to SQLite.
        # ------------------------------------------------------------------
        await write_turn_to_sqlite(
            session_id=session_id,
            enhanced_history=enhanced_history,
            title=title,
            working_directory=working_directory,
            pinned=pinned,
            agent_name=agent_name,
            model_name=model_name,
            total_tokens=total_tokens,
            updated_at=now_iso,
            created_at=created_at,
            ctx=ctx,
        )
        logger.info(
            "[BG:%s] Background save complete (%s): %d messages, %d tokens",
            session_id,
            label,
            len(enhanced_history),
            total_tokens,
        )

    except Exception as exc:
        logger.error(
            "[BG:%s] Background save failed (%s): %s",
            session_id,
            label,
            exc,
            exc_info=True,
        )
