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
        from code_puppy.callbacks import PromptBlocked
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        secret = "deploy with password hunter2"
        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = _engine(_blocked("no credentials in prompts"))
        try:
            result = await register_callbacks.on_user_prompt_submit_hook(secret)
        finally:
            register_callbacks._hook_engine = original

        assert isinstance(result, PromptBlocked)
        assert result.reason == "no credentials in prompts"
        # The whole point: the original text must not survive anywhere.
        assert secret not in result.replacement
        assert "hunter2" not in result.replacement
        assert "BLOCKED BY HOOK" in result.replacement
        assert "no credentials in prompts" in result.replacement

    @pytest.mark.asyncio
    async def test_block_without_reason_still_blocks(self):
        from code_puppy.callbacks import PromptBlocked
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = _engine(_blocked(None))
        try:
            result = await register_callbacks.on_user_prompt_submit_hook("do a thing")
        finally:
            register_callbacks._hook_engine = original

        assert isinstance(result, PromptBlocked)
        assert result.reason == "No reason was provided by the hook."
        assert "do a thing" not in result.replacement
        assert "BLOCKED BY HOOK" in result.replacement

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
# run_with_mcp honors a block
# ---------------------------------------------------------------------------


class TestRuntimeHonorsPromptBlocked:
    @pytest.mark.asyncio
    async def test_top_level_run_is_cancelled_outright(self, monkeypatch):
        """No agent is built, no LLM call is made, and the run returns None."""
        from code_puppy.agents import _runtime
        from code_puppy.callbacks import PromptBlocked

        blocked = PromptBlocked(reason="secrets policy", replacement="[BLOCKED] ...")

        async def _submit(prompt, session_id=None):
            return [blocked]

        warnings = []

        def _must_not_run(agent, prompt):
            raise AssertionError(
                "run continued past the block — the prompt would have been sent"
            )

        monkeypatch.setattr(_runtime, "on_user_prompt_submit", _submit)
        monkeypatch.setattr(_runtime, "emit_warning", lambda msg: warnings.append(msg))
        # Anything downstream of the block firing is a failure. This is the
        # last thing touched before the prompt payload is built.
        monkeypatch.setattr(_runtime, "_should_prepend_system_prompt", _must_not_run)

        result = await _runtime.run_with_mcp(MagicMock(), "leak the prod password")

        assert result is None
        assert any("secrets policy" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_nested_run_falls_back_to_substitution(self, monkeypatch):
        """A nested caller dereferences the result, so None would break it."""
        from code_puppy.agents import _runtime
        from code_puppy.callbacks import PromptBlocked

        blocked = PromptBlocked(
            reason="secrets policy", replacement="[BLOCKED] withheld"
        )

        async def _submit(prompt, session_id=None):
            return [blocked]

        seen_prompts = []

        class _Stop(Exception):
            pass

        def _capture(agent, prompt):
            seen_prompts.append(prompt)
            raise _Stop()

        monkeypatch.setattr(_runtime, "on_user_prompt_submit", _submit)
        monkeypatch.setattr(_runtime, "_should_prepend_system_prompt", _capture)

        # Simulate being inside an outer run.
        monkeypatch.setattr(_runtime, "_active_run_depth", 1)

        with pytest.raises(_Stop):
            await _runtime.run_with_mcp(MagicMock(), "leak the prod password")

        # Got past the block (not cancelled) but on the replacement text.
        assert seen_prompts == ["[BLOCKED] withheld"]
        assert "leak the prod password" not in seen_prompts[0]

    @pytest.mark.asyncio
    async def test_plain_string_result_still_replaces_the_prompt(self, monkeypatch):
        """The pre-existing additional-context contract is unchanged."""
        from code_puppy.agents import _runtime

        async def _submit(prompt, session_id=None):
            return ["[hook context]\nbe careful\n\noriginal prompt"]

        seen_prompts = []

        class _Stop(Exception):
            pass

        def _capture(agent, prompt):
            seen_prompts.append(prompt)
            raise _Stop()

        monkeypatch.setattr(_runtime, "on_user_prompt_submit", _submit)
        monkeypatch.setattr(_runtime, "_should_prepend_system_prompt", _capture)

        with pytest.raises(_Stop):
            await _runtime.run_with_mcp(MagicMock(), "original prompt")

        assert seen_prompts == ["[hook context]\nbe careful\n\noriginal prompt"]


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
