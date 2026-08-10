"""UserPromptSubmit blocking + session-id propagation for the hooks bridge.

Covers two behaviours the bridge previously dropped on the floor:

1. A blocking ``UserPromptSubmit`` hook must keep the user's prompt away from
   the model.
2. Every event must carry the id of the run it belongs to, not the
   ``"codepuppy-session"`` placeholder.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from code_puppy.hook_engine.models import ProcessEventResult


def _engine(result: ProcessEventResult) -> MagicMock:
    engine = MagicMock()
    engine.process_event = AsyncMock(return_value=result)
    return engine


def _blocked(reason: str | None = "policy violation") -> ProcessEventResult:
    return ProcessEventResult(
        blocked=True, executed_hooks=1, results=[], blocking_reason=reason
    )


def _allowed() -> ProcessEventResult:
    return ProcessEventResult(blocked=False, executed_hooks=1, results=[])


# ---------------------------------------------------------------------------
# UserPromptSubmit blocking
# ---------------------------------------------------------------------------


class TestUserPromptSubmitBlocking:
    @pytest.mark.asyncio
    async def test_blocked_prompt_is_withheld_from_the_model(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        secret = "deploy with password hunter2"
        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = _engine(_blocked("no credentials in prompts"))
        try:
            result = await register_callbacks.on_user_prompt_submit_hook(secret)
        finally:
            register_callbacks._hook_engine = original

        assert result is not None
        # The whole point: the original text must not survive into the prompt.
        assert secret not in result
        assert "hunter2" not in result
        assert "BLOCKED BY HOOK" in result
        assert "no credentials in prompts" in result

    @pytest.mark.asyncio
    async def test_block_without_reason_still_blocks(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = _engine(_blocked(None))
        try:
            result = await register_callbacks.on_user_prompt_submit_hook("do a thing")
        finally:
            register_callbacks._hook_engine = original

        assert result is not None
        assert "do a thing" not in result
        assert "BLOCKED BY HOOK" in result

    @pytest.mark.asyncio
    async def test_allowed_prompt_is_passed_through_untouched(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = _engine(_allowed())
        try:
            result = await register_callbacks.on_user_prompt_submit_hook("list files")
        finally:
            register_callbacks._hook_engine = original

        # Nothing to add => None, and run_with_mcp keeps the original prompt.
        assert result is None

    @pytest.mark.asyncio
    async def test_block_preserves_pending_session_context_for_next_prompt(self):
        """A blocked prompt never runs, so its SessionStart context must survive."""
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = _engine(_blocked())
        register_callbacks._pending_session_context.clear()
        register_callbacks._pending_session_context.append("project constitution")
        try:
            await register_callbacks.on_user_prompt_submit_hook("blocked prompt")
            assert register_callbacks._pending_session_context == [
                "project constitution"
            ]

            # The next, allowed prompt picks it up.
            register_callbacks._hook_engine = _engine(_allowed())
            result = await register_callbacks.on_user_prompt_submit_hook("ok prompt")
            assert result is not None
            assert "project constitution" in result
            assert "ok prompt" in result
            assert register_callbacks._pending_session_context == []
        finally:
            register_callbacks._hook_engine = original
            register_callbacks._pending_session_context.clear()


# ---------------------------------------------------------------------------
# Session id propagation
# ---------------------------------------------------------------------------


class TestSessionIdPropagation:
    @pytest.mark.asyncio
    async def test_pre_tool_use_carries_the_current_run_id(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks
        from code_puppy.session_context import set_session_id

        engine = _engine(_allowed())
        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = engine
        set_session_id("run-abc")
        try:
            await register_callbacks.on_pre_tool_call_hook("Bash", {"command": "ls"})
        finally:
            register_callbacks._hook_engine = original
            set_session_id(None)

        event_data = engine.process_event.await_args.args[1]
        assert event_data.context["session_id"] == "run-abc"

    @pytest.mark.asyncio
    async def test_post_tool_use_carries_the_current_run_id(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks
        from code_puppy.session_context import set_session_id

        engine = _engine(_allowed())
        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = engine
        set_session_id("run-xyz")
        try:
            await register_callbacks.on_post_tool_call_hook(
                "Bash", {"command": "ls"}, "output", 12.5
            )
        finally:
            register_callbacks._hook_engine = original
            set_session_id(None)

        event_data = engine.process_event.await_args.args[1]
        assert event_data.context["session_id"] == "run-xyz"
        # Existing context keys must survive alongside it.
        assert event_data.context["result"] == "output"
        assert event_data.context["duration_ms"] == 12.5

    @pytest.mark.asyncio
    async def test_explicit_session_id_wins_over_the_context_var(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks
        from code_puppy.session_context import set_session_id

        engine = _engine(_allowed())
        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = engine
        set_session_id("from-contextvar")
        try:
            await register_callbacks.on_user_prompt_submit_hook(
                "hello", session_id="from-argument"
            )
        finally:
            register_callbacks._hook_engine = original
            set_session_id(None)

        event_data = engine.process_event.await_args.args[1]
        assert event_data.context["session_id"] == "from-argument"

    @pytest.mark.asyncio
    async def test_outside_a_run_the_placeholder_default_still_applies(self):
        """No id available => omit the key so the payload builder's default wins."""
        from code_puppy.hook_engine.executor import _build_stdin_payload
        from code_puppy.plugins.claude_code_hooks import register_callbacks
        from code_puppy.session_context import set_session_id

        engine = _engine(_allowed())
        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = engine
        set_session_id(None)
        try:
            await register_callbacks.on_pre_tool_call_hook("Bash", {"command": "ls"})
        finally:
            register_callbacks._hook_engine = original

        event_data = engine.process_event.await_args.args[1]
        assert "session_id" not in event_data.context

        import json

        payload = json.loads(_build_stdin_payload(event_data).decode())
        assert payload["session_id"] == "codepuppy-session"


class TestSessionContextVar:
    def test_defaults_to_none(self):
        from code_puppy.session_context import get_session_id, set_session_id

        set_session_id(None)
        assert get_session_id() is None

    def test_set_and_get_round_trip(self):
        from code_puppy.session_context import get_session_id, set_session_id

        set_session_id("abc123")
        try:
            assert get_session_id() == "abc123"
        finally:
            set_session_id(None)

    @pytest.mark.asyncio
    async def test_value_is_inherited_by_a_child_task(self):
        """create_task copies the context — this is what carries the id into the run."""
        import asyncio

        from code_puppy.session_context import get_session_id, set_session_id

        seen = []

        async def child():
            seen.append(get_session_id())

        set_session_id("parent-run")
        try:
            await asyncio.create_task(child())
        finally:
            set_session_id(None)

        assert seen == ["parent-run"]

    @pytest.mark.asyncio
    async def test_a_child_task_cannot_clobber_its_parent(self):
        """Nested-run isolation: a task's write stays local to that task."""
        import asyncio

        from code_puppy.session_context import get_session_id, set_session_id

        async def child():
            set_session_id("nested-run")

        set_session_id("outer-run")
        try:
            await asyncio.create_task(child())
            assert get_session_id() == "outer-run"
        finally:
            set_session_id(None)
