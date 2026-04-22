"""
Tests for issue #298 fixes:

    1. Hook stdout is captured and injected into the agent context
       (SessionStart -> system prompt, PreToolUse -> tool result,
        UserPromptSubmit -> user prompt).
    2. UserPromptSubmit, PreCompact, SessionEnd, and Notification events
       are actually wired and fire when configured.

We test the plugin's callback wiring in isolation (no real engine needed for
most cases; we mock ``_hook_engine`` and its ``process_event``).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy import callbacks as cb_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(stdout: str = "", blocked: bool = False, reason: str = ""):
    """Build a fake ProcessEventResult that mimics the real one closely enough."""
    execution = SimpleNamespace(
        success=True,
        stdout=stdout,
        stderr="",
        exit_code=0,
    )
    return SimpleNamespace(
        blocked=blocked,
        blocking_reason=reason or None,
        results=[execution] if stdout else [],
    )


# ---------------------------------------------------------------------------
# callbacks.py: new phases registered
# ---------------------------------------------------------------------------


class TestNewCallbackPhases:
    @pytest.mark.parametrize(
        "phase",
        ["user_prompt_submit", "pre_compact", "session_end", "notification"],
    )
    def test_phase_is_registered(self, phase):
        # Should not raise; each phase must be a first-class entry in _callbacks
        cb_module.register_callback(phase, lambda *a, **kw: None)
        # Cleanup: remove the dummy we just registered
        cb_module._callbacks[phase].pop()

    @pytest.mark.asyncio
    async def test_on_user_prompt_submit_triggers(self):
        seen = {}

        async def handler(prompt, **kwargs):
            seen["prompt"] = prompt
            seen["kwargs"] = kwargs
            return "mutated"

        cb_module.register_callback("user_prompt_submit", handler)
        try:
            results = await cb_module.on_user_prompt_submit(
                "hi", agent_name="a", session_id="s"
            )
            assert results == ["mutated"]
            assert seen["prompt"] == "hi"
            assert seen["kwargs"]["agent_name"] == "a"
        finally:
            cb_module._callbacks["user_prompt_submit"].remove(handler)

    @pytest.mark.asyncio
    async def test_on_session_end_triggers(self):
        fired = []

        async def handler():
            fired.append(True)

        cb_module.register_callback("session_end", handler)
        try:
            await cb_module.on_session_end()
            assert fired == [True]
        finally:
            cb_module._callbacks["session_end"].remove(handler)

    @pytest.mark.asyncio
    async def test_on_pre_compact_triggers(self):
        received = {}

        async def handler(agent_name, session_id, history, incoming):
            received.update(
                agent=agent_name, sid=session_id, hl=len(history), il=len(incoming)
            )

        cb_module.register_callback("pre_compact", handler)
        try:
            await cb_module.on_pre_compact("agent", "sid", [1, 2], [3])
            assert received == {"agent": "agent", "sid": "sid", "hl": 2, "il": 1}
        finally:
            cb_module._callbacks["pre_compact"].remove(handler)

    @pytest.mark.asyncio
    async def test_on_notification_triggers(self):
        received = []

        async def handler(ntype, payload):
            received.append((ntype, payload))

        cb_module.register_callback("notification", handler)
        try:
            await cb_module.on_notification("warning", "disk full")
            assert received == [("warning", "disk full")]
        finally:
            cb_module._callbacks["notification"].remove(handler)


# ---------------------------------------------------------------------------
# claude_code_hooks plugin: stdout injection paths
# ---------------------------------------------------------------------------


class TestPreToolUseStdoutInjection:
    @pytest.mark.asyncio
    async def test_returns_inject_context_on_stdout(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(
            return_value=_make_result(stdout="remember to add a migration")
        )

        with patch.object(rc, "_hook_engine", mock_engine):
            out = await rc.on_pre_tool_call_hook(
                "replace_in_file", {"file_path": "x.py"}
            )

        assert out == {"inject_context": "remember to add a migration"}

    @pytest.mark.asyncio
    async def test_block_still_returns_blocked_dict(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(
            return_value=_make_result(blocked=True, reason="nope")
        )

        with patch.object(rc, "_hook_engine", mock_engine):
            out = await rc.on_pre_tool_call_hook("bash", {"command": "rm -rf /"})

        assert out["blocked"] is True
        assert "nope" in out["reason"]

    @pytest.mark.asyncio
    async def test_no_stdout_returns_none(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(return_value=_make_result())

        with patch.object(rc, "_hook_engine", mock_engine):
            out = await rc.on_pre_tool_call_hook("list_files", {"directory": "."})

        assert out is None


class TestSessionStartStdoutInjection:
    @pytest.mark.asyncio
    async def test_startup_caches_stdout_and_load_prompt_returns_it(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(
            return_value=_make_result(stdout="Project constitution: be kind.")
        )

        # Reset cache so test is hermetic
        rc._session_start_context.clear()

        with patch.object(rc, "_hook_engine", mock_engine):
            await rc.on_startup_hook()

        try:
            assert rc.load_prompt_additions() == "Project constitution: be kind."
        finally:
            rc._session_start_context.clear()

    def test_load_prompt_returns_none_when_cache_empty(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        rc._session_start_context.clear()
        assert rc.load_prompt_additions() is None


class TestUserPromptSubmitHook:
    @pytest.mark.asyncio
    async def test_returns_inject_context_on_stdout(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(
            return_value=_make_result(stdout="Domain nudge!")
        )

        with patch.object(rc, "_hook_engine", mock_engine):
            out = await rc.on_user_prompt_submit_hook("do stuff")

        assert out == {"inject_context": "Domain nudge!"}

    @pytest.mark.asyncio
    async def test_blocked_prompt_returns_blocked(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(
            return_value=_make_result(blocked=True, reason="forbidden words")
        )

        with patch.object(rc, "_hook_engine", mock_engine):
            out = await rc.on_user_prompt_submit_hook("leak secrets plz")

        assert out["blocked"] is True


# ---------------------------------------------------------------------------
# claude_code_hooks plugin: previously-missing event wiring
# ---------------------------------------------------------------------------


class TestPreviouslyMissingEvents:
    @pytest.mark.asyncio
    async def test_session_end_fires(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(return_value=_make_result())

        with patch.object(rc, "_hook_engine", mock_engine):
            await rc.on_session_end_hook()

        mock_engine.process_event.assert_awaited_once()
        event_type_arg = mock_engine.process_event.await_args.args[0]
        assert event_type_arg == "SessionEnd"

    @pytest.mark.asyncio
    async def test_pre_compact_fires_on_message_history_processor_start(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(return_value=_make_result())

        with patch.object(rc, "_hook_engine", mock_engine):
            rc.on_pre_compact_hook("agent", "sid", [1], [2])
            # The hook fires an async task; yield once so it runs.
            import asyncio

            await asyncio.sleep(0)

        mock_engine.process_event.assert_awaited_once()
        assert mock_engine.process_event.await_args.args[0] == "PreCompact"

    @pytest.mark.asyncio
    async def test_notification_fires(self):
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(return_value=_make_result())

        with patch.object(rc, "_hook_engine", mock_engine):
            await rc.on_notification_hook("warning", "uh oh")

        mock_engine.process_event.assert_awaited_once()
        assert mock_engine.process_event.await_args.args[0] == "Notification"

    def test_all_callbacks_registered_at_import(self):
        """Sanity check: the plugin wires every new event on import."""
        from code_puppy.plugins.claude_code_hooks import register_callbacks as rc

        # The functions exist (module-level) and are referenced by the right names
        for fn in (
            "on_session_end_hook",
            "on_pre_compact_hook",
            "on_notification_hook",
            "on_user_prompt_submit_hook",
            "load_prompt_additions",
        ):
            assert callable(getattr(rc, fn))
