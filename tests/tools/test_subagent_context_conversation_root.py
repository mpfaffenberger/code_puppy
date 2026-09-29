"""Direct coverage of ``subagent_context.py``'s conversation-root ContextVar.

This is the primitive ``load_model_with_fallback``'s ``conversation_scope``
(see ``_builder.py`` / ``subagent_invocation.py``) is built on, replacing an
earlier attempt that read ``code_puppy.messaging.bus.get_session_context()``
-- a plain, lock-protected instance attribute on a process-wide singleton,
NOT a ``contextvars.ContextVar``, and therefore unsafe for anything
correctness-sensitive under concurrent asyncio tasks.

These tests exercise the exact two properties a shared-mutable-global cannot
give you, using the REAL contextvar machinery (no mocking of
``get_conversation_root_id``/``set_conversation_root_id`` here -- that would
just prove the mocks agree with themselves):

1. Concurrent sibling tasks (parallel tool calls, or concurrent ACP
   sessions) never see each other's root id, even when they overlap in
   wall-clock time on the same event loop.
2. Nested calls (a coroutine invoked without its own
   ``set_conversation_root_id`` call) inherit the root id already active in
   their task, rather than seeing ``None`` or a stale value.
"""

import asyncio

import pytest

from code_puppy.tools.subagent_context import (
    get_conversation_root_id,
    reset_conversation_root_id,
    set_conversation_root_id,
)


def test_defaults_to_none_outside_any_scope():
    assert get_conversation_root_id() is None


def test_set_and_reset_round_trips():
    token = set_conversation_root_id("session-a")
    try:
        assert get_conversation_root_id() == "session-a"
    finally:
        reset_conversation_root_id(token)
    assert get_conversation_root_id() is None


async def _nested_reader() -> str | None:
    """Simulate a sub-agent invocation nested inside a conversation's root
    scope: it never calls ``set_conversation_root_id`` itself, it just reads
    whatever's already active -- exactly what ``_invoke_agent_impl`` does.
    """
    await asyncio.sleep(0)  # force a real scheduling point
    return get_conversation_root_id()


async def _run_conversation(root_id: str, delay_before_read: float) -> str | None:
    """Stand in for one ACP session's ``prompt()`` handler: set the root id
    once, await something (so a sibling conversation's task can interleave),
    then read it back through a nested call -- mirroring
    ``session.py``/``subagent_invocation.py``'s real call shape.
    """
    token = set_conversation_root_id(root_id)
    try:
        await asyncio.sleep(delay_before_read)
        return await _nested_reader()
    finally:
        reset_conversation_root_id(token)


class TestConcurrentConversationsDoNotLeak:
    """The property Finding 0 (round 3 adversarial review) demanded actual
    proof of: two conversations running as concurrent asyncio tasks on the
    SAME event loop must never see each other's root id, regardless of how
    their awaits interleave.
    """

    @pytest.mark.asyncio
    async def test_two_concurrent_tasks_never_cross_contaminate(self):
        # Deliberately staggered delays so the two tasks' internal awaits
        # interleave rather than running strictly back-to-back.
        results = await asyncio.gather(
            _run_conversation("session-a", delay_before_read=0.02),
            _run_conversation("session-b", delay_before_read=0.01),
        )
        assert results == ["session-a", "session-b"]

    @pytest.mark.asyncio
    async def test_many_concurrent_tasks_each_keep_their_own_root(self):
        n = 20
        results = await asyncio.gather(
            *[
                _run_conversation(f"session-{i}", delay_before_read=0.001 * (i % 5))
                for i in range(n)
            ]
        )
        assert results == [f"session-{i}" for i in range(n)]

    @pytest.mark.asyncio
    async def test_outer_scope_unaffected_by_a_concurrent_sibling(self):
        """Setting a root id in one task must not leak into a completely
        separate task that never set one at all (e.g. the CLI's top-level
        conversation, which never calls ``set_conversation_root_id``).
        """

        async def _bystander() -> str | None:
            await asyncio.sleep(0.015)
            return get_conversation_root_id()

        results = await asyncio.gather(
            _run_conversation("session-a", delay_before_read=0.01),
            _bystander(),
        )
        assert results == ["session-a", None]


class TestNestedInvocationsInheritTheSameRoot:
    """Finding 1 (round 3): nested sub-agent invocations (A invokes B invokes
    C) must all see the SAME root id, not a fresh one per nesting level --
    otherwise the once-per-conversation warning dedup degrades to
    once-per-invocation.
    """

    @pytest.mark.asyncio
    async def test_two_levels_of_nesting_see_the_same_root(self):
        async def _level_two() -> str | None:
            return await _nested_reader()

        async def _level_one() -> str | None:
            return await _level_two()

        token = set_conversation_root_id("root-conversation")
        try:
            result = await _level_one()
        finally:
            reset_conversation_root_id(token)

        assert result == "root-conversation"

    @pytest.mark.asyncio
    async def test_nested_call_does_not_need_to_set_its_own_root(self):
        """A sub-agent invocation never calls ``set_conversation_root_id``
        itself (only the true conversation entrypoint does) -- confirm a
        plain read-only nested call still resolves correctly.
        """
        token = set_conversation_root_id("root-conversation")
        try:
            assert await _nested_reader() == "root-conversation"
        finally:
            reset_conversation_root_id(token)
