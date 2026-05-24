"""Regression tests for CPUP-a4a: main agent must classify as Stop, not SubagentStop.

The ``_SUBAGENT_NAMES`` frozenset in
``code_puppy/plugins/claude_code_hooks/register_callbacks.py`` previously
included ``"code-puppy"`` and ``"code_puppy"`` — the main agent's own names.
As a result, ``on_agent_run_end_hook`` classified every top-level turn-end
as ``SubagentStop`` instead of ``Stop``, which caused any ``hooks.json``
integration wired to the ``Stop`` matcher (e.g. cmux desktop notifications,
cmux iMessage Mode, Reorder on Notification) to silently never fire on the
main agent's reply.

These tests pin the corrected classification so the bug can't sneak back in.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestSubagentNamesSet:
    """The frozenset must NOT mark the main agent's own names as sub-agents."""

    def test_main_agent_names_excluded(self):
        from code_puppy.plugins.claude_code_hooks.register_callbacks import (
            _SUBAGENT_NAMES,
        )

        assert "code-puppy" not in _SUBAGENT_NAMES
        assert "code_puppy" not in _SUBAGENT_NAMES

    def test_real_subagents_still_included(self):
        """Real sub-agent names must keep their SubagentStop classification."""
        from code_puppy.plugins.claude_code_hooks.register_callbacks import (
            _SUBAGENT_NAMES,
        )

        expected = {
            "pack_leader",
            "bloodhound",
            "retriever",
            "shepherd",
            "terrier",
            "watchdog",
            "subagent",
            "sub_agent",
        }
        # Using >= rather than == so adding new real sub-agents later
        # doesn't regress this test.
        assert _SUBAGENT_NAMES >= expected


class TestOnAgentRunEndClassification:
    """End-to-end check that the callback emits the right hook event_type."""

    @pytest.mark.asyncio
    async def test_main_agent_fires_stop(self):
        from code_puppy.hook_engine.models import ProcessEventResult
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(
            return_value=ProcessEventResult(blocked=False, executed_hooks=1, results=[])
        )

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = mock_engine
        try:
            await register_callbacks.on_agent_run_end_hook(
                agent_name="code-puppy",
                model_name="claude-4-7-opus",
                session_id="sess-1",
                success=True,
            )
            event_type_arg = mock_engine.process_event.call_args[0][0]
            event_data_arg = mock_engine.process_event.call_args[0][1]
            assert event_type_arg == "Stop"
            assert event_data_arg.event_type == "Stop"
        finally:
            register_callbacks._hook_engine = original

    @pytest.mark.asyncio
    async def test_underscore_main_agent_fires_stop(self):
        """The underscore spelling ``code_puppy`` must also fire Stop."""
        from code_puppy.hook_engine.models import ProcessEventResult
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(
            return_value=ProcessEventResult(blocked=False, executed_hooks=1, results=[])
        )

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = mock_engine
        try:
            await register_callbacks.on_agent_run_end_hook(
                agent_name="code_puppy",
                model_name="claude-4-7-opus",
            )
            event_type_arg = mock_engine.process_event.call_args[0][0]
            assert event_type_arg == "Stop"
        finally:
            register_callbacks._hook_engine = original

    @pytest.mark.asyncio
    async def test_real_subagent_fires_subagent_stop(self):
        from code_puppy.hook_engine.models import ProcessEventResult
        from code_puppy.plugins.claude_code_hooks import register_callbacks

        mock_engine = MagicMock()
        mock_engine.process_event = AsyncMock(
            return_value=ProcessEventResult(blocked=False, executed_hooks=1, results=[])
        )

        original = register_callbacks._hook_engine
        register_callbacks._hook_engine = mock_engine
        try:
            await register_callbacks.on_agent_run_end_hook(
                agent_name="bloodhound",
                model_name="claude-4-7-opus",
            )
            event_type_arg = mock_engine.process_event.call_args[0][0]
            assert event_type_arg == "SubagentStop"
        finally:
            register_callbacks._hook_engine = original
