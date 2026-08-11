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
# PostToolUse can withhold a tool's output
# ---------------------------------------------------------------------------


class TestPostToolUseWithholding:
    @pytest.mark.asyncio
    async def test_bridge_returns_a_block_verdict(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = _engine(_blocked("secret in output"))
        try:
            verdict = await register_callbacks.on_post_tool_call_hook(
                "Bash", {"command": "cat s.txt"}, "AKIAIOSFODNN7EXAMPLE", 5.0
            )
        finally:
            register_callbacks._hook_engine = original

        assert verdict == {
            "blocked": True,
            "reason": "secret in output",
            "error_message": "secret in output",
        }

    @pytest.mark.asyncio
    async def test_bridge_passes_output_through_when_allowed(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = _engine(_allowed())
        try:
            verdict = await register_callbacks.on_post_tool_call_hook(
                "Bash", {"command": "echo hi"}, "hi", 5.0
            )
        finally:
            register_callbacks._hook_engine = original

        assert verdict is None

    @pytest.mark.asyncio
    async def test_runtime_replaces_the_result_on_a_block(self, monkeypatch):
        """The secret must not survive into what pydantic-ai receives."""
        from code_puppy import callbacks as cb_module
        from code_puppy.pydantic_patches import _run_post_tool_call as run

        async def _fire(tool_name, tool_args, result, duration_ms):
            return [{"blocked": True, "reason": "secret in output"}]

        monkeypatch.setattr(cb_module, "on_post_tool_call", _fire)

        out = await run("Bash", {"command": "cat s.txt"}, "AKIAIOSFODNN7EXAMPLE", 1.0)

        assert "AKIAIOSFODNN7EXAMPLE" not in out
        assert "withheld" in out
        assert "secret in output" in out

    @pytest.mark.asyncio
    async def test_runtime_passes_the_result_through_when_allowed(self, monkeypatch):
        from code_puppy import callbacks as cb_module
        from code_puppy.pydantic_patches import _run_post_tool_call as run

        async def _fire(tool_name, tool_args, result, duration_ms):
            return [None]

        monkeypatch.setattr(cb_module, "on_post_tool_call", _fire)

        assert await run("Bash", {}, "untouched output", 1.0) == "untouched output"

    @pytest.mark.asyncio
    async def test_a_failing_hook_leaves_the_result_alone(self, monkeypatch):
        from code_puppy import callbacks as cb_module
        from code_puppy.pydantic_patches import _run_post_tool_call as run

        async def _boom(tool_name, tool_args, result, duration_ms):
            raise RuntimeError("hook exploded")

        monkeypatch.setattr(cb_module, "on_post_tool_call", _boom)

        assert await run("Bash", {}, "untouched output", 1.0) == "untouched output"


# ---------------------------------------------------------------------------
# Stop vs SubagentStop, and the end-of-turn payload
# ---------------------------------------------------------------------------


class TestStopClassification:
    @pytest.mark.asyncio
    async def test_default_agent_ending_a_turn_fires_stop(self):
        """``code-puppy`` is the DEFAULT agent — a top-level turn is a Stop."""
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        engine = _engine(_allowed())
        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = engine
        try:
            await register_callbacks.on_agent_run_end_hook(
                agent_name="code-puppy",
                model_name="some-model",
                response_text="all done",
            )
        finally:
            register_callbacks._hook_engine = original

        assert engine.process_event.await_args.args[0] == "Stop"

    @pytest.mark.asyncio
    async def test_run_inside_subagent_context_fires_subagent_stop(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks
        from code_puppy.tools.subagent_context import subagent_context

        engine = _engine(_allowed())
        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = engine
        try:
            with subagent_context("retriever"):
                await register_callbacks.on_agent_run_end_hook(
                    agent_name="code-puppy",
                    model_name="some-model",
                    response_text="all done",
                )
        finally:
            register_callbacks._hook_engine = original

        assert engine.process_event.await_args.args[0] == "SubagentStop"

    @pytest.mark.asyncio
    async def test_known_subagent_name_still_fires_subagent_stop(self):
        """Fallback for a run ended outside the context manager."""
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        engine = _engine(_allowed())
        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = engine
        try:
            await register_callbacks.on_agent_run_end_hook(
                agent_name="bloodhound",
                model_name="some-model",
                response_text="all done",
            )
        finally:
            register_callbacks._hook_engine = original

        assert engine.process_event.await_args.args[0] == "SubagentStop"


class TestEndOfTurnPayload:
    def test_stop_payload_carries_the_agents_final_response(self):
        """Without this a Stop hook has nothing to review."""
        import json

        from code_puppy.hook_engine.executor import _build_stdin_payload
        from code_puppy.hook_engine.models import EventData

        event = EventData(
            event_type="Stop",
            tool_name="code-puppy",
            tool_args={},
            context={"session_id": "run-1", "response_text": "the final answer"},
        )
        payload = json.loads(_build_stdin_payload(event).decode())

        assert payload["response_text"] == "the final answer"
        assert payload["hook_event_name"] == "Stop"
        assert payload["session_id"] == "run-1"

    def test_absent_response_text_adds_no_key(self):
        import json

        from code_puppy.hook_engine.executor import _build_stdin_payload
        from code_puppy.hook_engine.models import EventData

        event = EventData(event_type="PreToolUse", tool_name="Bash", tool_args={})
        payload = json.loads(_build_stdin_payload(event).decode())

        assert "response_text" not in payload


class TestBlockReasonIsHumanFacing:
    """The reason shown to a user must not be the internal diagnostic string."""

    @pytest.mark.asyncio
    async def test_hook_stderr_is_preferred_over_the_diagnostic_string(self):
        from code_puppy.callbacks import PromptBlocked
        from code_puppy.hook_engine.models import ExecutionResult, ProcessEventResult
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        execution = ExecutionResult(
            blocked=True,
            hook_command="python3 /very/long/path/to/guard.py",
            stderr="Onyx AI Guard: blocked by policy.",
            exit_code=1,
        )
        result = ProcessEventResult(
            blocked=True,
            executed_hooks=1,
            results=[execution],
            blocking_reason=(
                "Hook 'python3 /very/long/path/to/guard.py' failed: "
                "Onyx AI Guard: blocked by policy."
            ),
        )

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = _engine(result)
        try:
            blocked = await register_callbacks.on_user_prompt_submit_hook("hi")
        finally:
            register_callbacks._hook_engine = original

        assert isinstance(blocked, PromptBlocked)
        assert blocked.reason == "Onyx AI Guard: blocked by policy."
        assert "/very/long/path" not in blocked.reason
        assert "failed" not in blocked.reason

    @pytest.mark.asyncio
    async def test_falls_back_to_blocking_reason_when_no_stderr(self):
        from code_puppy.callbacks import PromptBlocked
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = _engine(_blocked("terse reason"))
        try:
            blocked = await register_callbacks.on_user_prompt_submit_hook("hi")
        finally:
            register_callbacks._hook_engine = original

        assert isinstance(blocked, PromptBlocked)
        assert blocked.reason == "terse reason"


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
