"""Unit tests for code_puppy.api.ws.background_save.

Covers every edge case identified in the Phase 3 plan:

1.  fire_and_track GC protection (task registered + deregistered).
2.  None agent_task → early return, write never called.
3.  Cancelled agent task → early return, write never called.
4.  Failed agent task → early return, write never called.
5.  None result from task → early return, write never called.
6.  Empty history → early return, write never called.
7.  Session deleted during run → write skipped (resurrection guard).
8.  session_exists check failure → write proceeds (fail-safe).
9.  ctx without created_at attribute → now_iso fallback used.
10. ctx is None → now_iso fallback used.
11. Pre-wrapped dict history entries pass through unchanged.
12. Bare ModelMessage-like objects get wrapped with agent/model/ts.
13. Token computation is called per message (not 0 as before).
14. write_turn_to_sqlite receives correct keyword arguments.
"""

from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(history=None, token_per_msg=10):
    """Return a minimal agent mock."""
    agent = MagicMock()
    agent.get_message_history.return_value = history or []
    agent.set_message_history.return_value = None
    agent.estimate_tokens_for_message.return_value = token_per_msg
    return agent


def _make_result(messages=None):
    """Return a minimal agent-run result mock."""
    result = MagicMock()
    result.all_messages.return_value = messages or []
    return result


def _bare_msg(content="hello"):
    """Simulate a bare ModelMessage-like object (has .parts attribute)."""
    msg = MagicMock()
    msg.__class__.__name__ = "ModelRequest"
    # Make isinstance(msg, dict) == False (default for MagicMock)
    return msg


def _wrapped_msg(content="wrapped"):
    """Simulate an already-wrapped history dict entry."""
    return {"msg": MagicMock(), "agent": "code-puppy", "model": "gpt-4", "ts": "ts"}


# ---------------------------------------------------------------------------
# fire_and_track
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_and_track_registers_and_deregisters_task():
    """Task should be in _BACKGROUND_TASKS while running and removed after."""
    from code_puppy.api.ws.background_save import _BACKGROUND_TASKS, fire_and_track

    async def _noop():
        await asyncio.sleep(0)

    task = fire_and_track(_noop())
    assert task in _BACKGROUND_TASKS

    await task
    # done_callback fires synchronously when the task finishes
    assert task not in _BACKGROUND_TASKS


# ---------------------------------------------------------------------------
# Early-exit guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_none_task_returns_immediately():
    """agent_task=None should be a safe no-op."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    with patch("code_puppy.api.ws.background_save.write_turn_to_sqlite") as mock_write:
        # patch is not needed since we never reach the write, but kept for safety
        await save_agent_result_in_background(
            agent_task=None,
            session_id="sess-1",
            ctx=None,
            agent=_make_agent(),
            agent_name="puppy",
            model_name="gpt-4",
            title="Test",
            working_directory="/tmp",
            pinned=False,
        )
    mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_task_returns_early():
    """CancelledError from the agent task should be swallowed — no write."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    async def _cancelled():
        raise asyncio.CancelledError()

    task = asyncio.ensure_future(_cancelled())
    with pytest.raises(asyncio.CancelledError):
        await task  # drain so it's actually cancelled

    # Create a new cancelled-style task via a Future
    cancelled_task = asyncio.get_event_loop().create_future()
    cancelled_task.cancel()

    with patch("code_puppy.api.ws.background_save.write_turn_to_sqlite") as mock_write:
        await save_agent_result_in_background(
            agent_task=cancelled_task,
            session_id="sess-cancel",
            ctx=None,
            agent=_make_agent(),
            agent_name="puppy",
            model_name="gpt-4",
            title="T",
            working_directory="/",
            pinned=False,
        )
    mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_failed_task_returns_early():
    """An exception from the agent task should be swallowed — no write."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    async def _fail():
        raise RuntimeError("boom")

    task = asyncio.ensure_future(_fail())
    try:
        await task
    except RuntimeError:
        pass

    # Create a fresh failed future
    failed_task = asyncio.get_event_loop().create_future()
    failed_task.set_exception(RuntimeError("agent boom"))

    with patch("code_puppy.api.ws.background_save.write_turn_to_sqlite") as mock_write:
        await save_agent_result_in_background(
            agent_task=failed_task,
            session_id="sess-fail",
            ctx=None,
            agent=_make_agent(),
            agent_name="puppy",
            model_name="gpt-4",
            title="T",
            working_directory="/",
            pinned=False,
        )
    mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_none_result_returns_early():
    """result=None from await agent_task should skip the write."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    task_future = asyncio.get_event_loop().create_future()
    task_future.set_result(None)  # agent returned None

    with patch("code_puppy.api.ws.background_save.write_turn_to_sqlite") as mock_write:
        await save_agent_result_in_background(
            agent_task=task_future,
            session_id="sess-none-result",
            ctx=None,
            agent=_make_agent(),
            agent_name="puppy",
            model_name="gpt-4",
            title="T",
            working_directory="/",
            pinned=False,
        )
    mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_empty_history_returns_early():
    """Empty message history should skip the write."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    task_future = asyncio.get_event_loop().create_future()
    task_future.set_result(_make_result(messages=[]))

    agent = _make_agent(history=[])  # empty history after sync

    with (
        patch(
            "code_puppy.api.ws.background_save.session_exists", new_callable=AsyncMock
        ) as mock_exists,
        patch("code_puppy.api.ws.background_save.write_turn_to_sqlite") as mock_write,
    ):
        mock_exists.return_value = True
        await save_agent_result_in_background(
            agent_task=task_future,
            session_id="sess-empty",
            ctx=None,
            agent=agent,
            agent_name="puppy",
            model_name="gpt-4",
            title="T",
            working_directory="/",
            pinned=False,
        )
    mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# Session-deleted resurrection guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deleted_session_skips_write():
    """If session_exists returns False, write_turn_to_sqlite must NOT be called."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    msg = _bare_msg()
    task_future = asyncio.get_event_loop().create_future()
    task_future.set_result(_make_result(messages=[msg]))
    agent = _make_agent(history=[msg])

    with (
        patch(
            "code_puppy.api.ws.background_save.session_exists", new_callable=AsyncMock
        ) as mock_exists,
        patch("code_puppy.api.ws.background_save.write_turn_to_sqlite") as mock_write,
    ):
        mock_exists.return_value = False  # session was deleted
        await save_agent_result_in_background(
            agent_task=task_future,
            session_id="sess-deleted",
            ctx=None,
            agent=agent,
            agent_name="puppy",
            model_name="gpt-4",
            title="T",
            working_directory="/",
            pinned=False,
        )
    mock_exists.assert_awaited_once_with("sess-deleted")
    mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_session_exists_failure_proceeds_anyway():
    """If session_exists raises, we log a warning but still write (fail-safe)."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    msg = _bare_msg()
    task_future = asyncio.get_event_loop().create_future()
    task_future.set_result(_make_result(messages=[msg]))
    agent = _make_agent(history=[msg])

    with (
        patch(
            "code_puppy.api.ws.background_save.session_exists",
            new_callable=AsyncMock,
            side_effect=Exception("db gone"),
        ),
        patch(
            "code_puppy.api.ws.background_save.write_turn_to_sqlite",
            new_callable=AsyncMock,
        ) as mock_write,
    ):
        await save_agent_result_in_background(
            agent_task=task_future,
            session_id="sess-db-gone",
            ctx=None,
            agent=agent,
            agent_name="puppy",
            model_name="gpt-4",
            title="T",
            working_directory="/",
            pinned=False,
        )
    mock_write.assert_awaited_once()


# ---------------------------------------------------------------------------
# created_at edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ctx_without_created_at_uses_now_iso():
    """ctx that lacks created_at should fall back to now_iso without crashing."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    ctx_no_attr = SimpleNamespace()  # no created_at attribute
    msg = _bare_msg()
    task_future = asyncio.get_event_loop().create_future()
    task_future.set_result(_make_result(messages=[msg]))
    agent = _make_agent(history=[msg])

    with (
        patch(
            "code_puppy.api.ws.background_save.session_exists", new_callable=AsyncMock
        ) as mock_exists,
        patch(
            "code_puppy.api.ws.background_save.write_turn_to_sqlite",
            new_callable=AsyncMock,
        ) as mock_write,
    ):
        mock_exists.return_value = True
        await save_agent_result_in_background(
            agent_task=task_future,
            session_id="sess-no-attr",
            ctx=ctx_no_attr,
            agent=agent,
            agent_name="puppy",
            model_name="gpt-4",
            title="T",
            working_directory="/",
            pinned=False,
        )

    call_kwargs = mock_write.call_args.kwargs
    # created_at should be an ISO datetime string, not an error
    created_at = call_kwargs["created_at"]
    assert isinstance(created_at, str)
    datetime.datetime.fromisoformat(created_at)  # must be valid ISO


@pytest.mark.asyncio
async def test_ctx_none_uses_now_iso():
    """ctx=None should fall back to now_iso for created_at."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    msg = _bare_msg()
    task_future = asyncio.get_event_loop().create_future()
    task_future.set_result(_make_result(messages=[msg]))
    agent = _make_agent(history=[msg])

    with (
        patch(
            "code_puppy.api.ws.background_save.session_exists", new_callable=AsyncMock
        ) as mock_exists,
        patch(
            "code_puppy.api.ws.background_save.write_turn_to_sqlite",
            new_callable=AsyncMock,
        ) as mock_write,
    ):
        mock_exists.return_value = True
        await save_agent_result_in_background(
            agent_task=task_future,
            session_id="sess-ctx-none",
            ctx=None,
            agent=agent,
            agent_name="puppy",
            model_name="gpt-4",
            title="T",
            working_directory="/",
            pinned=False,
        )

    call_kwargs = mock_write.call_args.kwargs
    created_at = call_kwargs["created_at"]
    assert isinstance(created_at, str)
    datetime.datetime.fromisoformat(created_at)


# ---------------------------------------------------------------------------
# History wrapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pre_wrapped_dict_entries_pass_through():
    """Dicts with 'msg' key must not be double-wrapped."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    wrapped = _wrapped_msg()
    task_future = asyncio.get_event_loop().create_future()
    task_future.set_result(_make_result(messages=[wrapped]))
    agent = _make_agent(history=[wrapped])

    with (
        patch(
            "code_puppy.api.ws.background_save.session_exists", new_callable=AsyncMock
        ) as mock_exists,
        patch(
            "code_puppy.api.ws.background_save.write_turn_to_sqlite",
            new_callable=AsyncMock,
        ) as mock_write,
    ):
        mock_exists.return_value = True
        await save_agent_result_in_background(
            agent_task=task_future,
            session_id="sess-wrapped",
            ctx=None,
            agent=agent,
            agent_name="puppy",
            model_name="gpt-4",
            title="T",
            working_directory="/",
            pinned=False,
        )

    eh = mock_write.call_args.kwargs["enhanced_history"]
    assert len(eh) == 1
    assert eh[0] is wrapped  # same object, not a new wrapper


@pytest.mark.asyncio
async def test_bare_message_gets_wrapped():
    """Bare ModelMessage objects must be wrapped with agent/model/ts metadata."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    bare = _bare_msg()
    task_future = asyncio.get_event_loop().create_future()
    task_future.set_result(_make_result(messages=[bare]))
    agent = _make_agent(history=[bare])

    with (
        patch(
            "code_puppy.api.ws.background_save.session_exists", new_callable=AsyncMock
        ) as mock_exists,
        patch(
            "code_puppy.api.ws.background_save.write_turn_to_sqlite",
            new_callable=AsyncMock,
        ) as mock_write,
    ):
        mock_exists.return_value = True
        await save_agent_result_in_background(
            agent_task=task_future,
            session_id="sess-bare",
            ctx=None,
            agent=agent,
            agent_name="my-agent",
            model_name="gpt-4o",
            title="T",
            working_directory="/",
            pinned=False,
        )

    eh = mock_write.call_args.kwargs["enhanced_history"]
    assert len(eh) == 1
    wrapper = eh[0]
    assert wrapper["msg"] is bare
    assert wrapper["agent"] == "my-agent"
    assert wrapper["model"] == "gpt-4o"
    assert "ts" in wrapper


# ---------------------------------------------------------------------------
# Token computation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_count_computed_not_zero():
    """total_tokens must reflect the actual estimate, not hard-coded 0."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    bare = _bare_msg()
    task_future = asyncio.get_event_loop().create_future()
    task_future.set_result(_make_result(messages=[bare]))
    agent = _make_agent(history=[bare], token_per_msg=42)

    with (
        patch(
            "code_puppy.api.ws.background_save.session_exists", new_callable=AsyncMock
        ) as mock_exists,
        patch(
            "code_puppy.api.ws.background_save.write_turn_to_sqlite",
            new_callable=AsyncMock,
        ) as mock_write,
    ):
        mock_exists.return_value = True
        await save_agent_result_in_background(
            agent_task=task_future,
            session_id="sess-tokens",
            ctx=None,
            agent=agent,
            agent_name="puppy",
            model_name="gpt-4",
            title="T",
            working_directory="/",
            pinned=False,
        )

    total_tokens = mock_write.call_args.kwargs["total_tokens"]
    assert total_tokens == 42  # 1 message × 42 tokens each
    agent.estimate_tokens_for_message.assert_called_once()


# ---------------------------------------------------------------------------
# Happy-path write args
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_write_kwargs():
    """write_turn_to_sqlite must receive the correct session metadata."""
    from code_puppy.api.ws.background_save import save_agent_result_in_background

    created = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    ctx = SimpleNamespace(created_at=created)

    bare = _bare_msg()
    task_future = asyncio.get_event_loop().create_future()
    task_future.set_result(_make_result(messages=[bare]))
    agent = _make_agent(history=[bare], token_per_msg=5)

    with (
        patch(
            "code_puppy.api.ws.background_save.session_exists", new_callable=AsyncMock
        ) as mock_exists,
        patch(
            "code_puppy.api.ws.background_save.write_turn_to_sqlite",
            new_callable=AsyncMock,
        ) as mock_write,
    ):
        mock_exists.return_value = True
        await save_agent_result_in_background(
            agent_task=task_future,
            session_id="sess-happy",
            ctx=ctx,
            agent=agent,
            agent_name="code-puppy",
            model_name="claude-3",
            title="My Session",
            working_directory="/home/user",
            pinned=True,
            label="switch",
        )

    kw = mock_write.call_args.kwargs
    assert kw["session_id"] == "sess-happy"
    assert kw["agent_name"] == "code-puppy"
    assert kw["model_name"] == "claude-3"
    assert kw["title"] == "My Session"
    assert kw["working_directory"] == "/home/user"
    assert kw["pinned"] is True
    assert kw["created_at"] == created.isoformat()
    assert kw["total_tokens"] == 5
    assert kw["ctx"] is ctx
