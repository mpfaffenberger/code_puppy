"""Interrupted sub-agent records are filed per conversation root.

An ACP host runs several sessions in one process; a session's resume note must
never be injected into another session's history.
"""

import asyncio
from unittest.mock import patch

import pytest

# agent_tools must load first: importing subagent_invocation cold hits a cycle.
from code_puppy.tools import agent_tools  # noqa: F401
from code_puppy.tools import subagent_invocation as si
from code_puppy.tools.subagent_context import (
    reset_conversation_root_id,
    set_conversation_root_id,
)


@pytest.fixture(autouse=True)
def _isolate_interrupted_store():
    si._interrupted_subagents.clear()
    yield
    si._interrupted_subagents.clear()


def _record(agent_name: str, session_id: str, saved_count: int | None) -> None:
    si.record_interrupted_subagent(
        agent_name=agent_name, session_id=session_id, saved_count=saved_count
    )


class _Scope:
    """Set a conversation root for the current task and restore it on exit."""

    def __init__(self, root: str | None):
        self._root = root
        self._token = None

    def __enter__(self):
        self._token = set_conversation_root_id(self._root)
        return self

    def __exit__(self, *exc):
        reset_conversation_root_id(self._token)


class TestTerminalBucket:
    def test_record_then_drain_returns_record_once(self):
        _record("explore", "explore-1", 2)

        assert si.drain_interrupted_subagents() == [
            {"agent_name": "explore", "session_id": "explore-1", "saved_count": 2}
        ]
        assert si.drain_interrupted_subagents() == []

    def test_peek_returns_copies_and_does_not_clear(self):
        _record("explore", "explore-1", 2)

        peeked = si.peek_interrupted_subagents()
        peeked[0]["agent_name"] = "tampered"
        peeked.append({"agent_name": "extra"})

        assert si.peek_interrupted_subagents() == [
            {"agent_name": "explore", "session_id": "explore-1", "saved_count": 2}
        ]


class TestConcurrentSessions:
    @pytest.mark.asyncio
    async def test_each_session_drains_only_its_own_records(self):
        async def session(root: str, agent: str, saved: int | None):
            with _Scope(root):
                await asyncio.sleep(0)
                _record(agent, f"{agent}-session", saved)
                await asyncio.sleep(0)
                _record(f"{agent}-2", f"{agent}-session-2", None)
                await asyncio.sleep(0)
                return si.drain_interrupted_subagents()

        drained_a, drained_b = await asyncio.gather(
            session("A", "alpha", 3), session("B", "beta", None)
        )

        assert drained_a == [
            {"agent_name": "alpha", "session_id": "alpha-session", "saved_count": 3},
            {
                "agent_name": "alpha-2",
                "session_id": "alpha-session-2",
                "saved_count": None,
            },
        ]
        assert drained_b == [
            {"agent_name": "beta", "session_id": "beta-session", "saved_count": None},
            {
                "agent_name": "beta-2",
                "session_id": "beta-session-2",
                "saved_count": None,
            },
        ]

    @pytest.mark.asyncio
    async def test_terminal_bucket_is_isolated_from_sessions(self):
        _record("terminal-agent", "term-1", 1)

        async def session(root: str):
            with _Scope(root):
                await asyncio.sleep(0)
                _record(f"{root}-agent", f"{root}-session", 5)
                await asyncio.sleep(0)
                return si.drain_interrupted_subagents()

        await asyncio.gather(session("A"), session("B"))

        assert si.peek_interrupted_subagents(None) == [
            {"agent_name": "terminal-agent", "session_id": "term-1", "saved_count": 1}
        ]
        assert si.peek_interrupted_subagents("A") == []
        assert si.peek_interrupted_subagents("B") == []


class TestPeekKeys:
    def test_peek_by_explicit_key_works_from_other_scope(self):
        with _Scope("A"):
            _record("alpha", "alpha-session", 4)
        with _Scope("B"):
            _record("beta", "beta-session", None)

            assert si.peek_interrupted_subagents("A") == [
                {"agent_name": "alpha", "session_id": "alpha-session", "saved_count": 4}
            ]
            assert si.peek_interrupted_subagents() == [
                {
                    "agent_name": "beta",
                    "session_id": "beta-session",
                    "saved_count": None,
                }
            ]

    def test_peek_default_from_outside_any_scope_reads_terminal(self):
        with _Scope("A"):
            _record("alpha", "alpha-session", 4)

        assert si.peek_interrupted_subagents() == []


class TestClear:
    def test_clear_removes_only_the_named_key(self):
        with _Scope("A"):
            _record("alpha", "alpha-session", 1)
        with _Scope("B"):
            _record("beta", "beta-session", 2)

        si.clear_interrupted_subagents("A")

        assert si.peek_interrupted_subagents("A") == []
        assert si.peek_interrupted_subagents("B") == [
            {"agent_name": "beta", "session_id": "beta-session", "saved_count": 2}
        ]

    @pytest.mark.parametrize("key", ["unknown", None])
    def test_clear_absent_key_is_noop(self, key):
        with _Scope("A"):
            _record("alpha", "alpha-session", 1)

        si.clear_interrupted_subagents(key)

        assert si._interrupted_subagents.keys() == {"A"}

    def test_clear_none_clears_terminal_bucket_only(self):
        _record("terminal-agent", "term-1", 1)
        with _Scope("A"):
            _record("alpha", "alpha-session", 1)

        si.clear_interrupted_subagents(None)

        assert si.peek_interrupted_subagents(None) == []
        assert si.peek_interrupted_subagents("A") != []


class TestContextInheritance:
    @pytest.mark.asyncio
    async def test_child_task_files_under_spawner_root(self):
        with _Scope("A"):

            async def sub_agent():
                _record("alpha-sub", "alpha-sub-session", 0)

            await asyncio.create_task(sub_agent())

        assert si.peek_interrupted_subagents("A") == [
            {
                "agent_name": "alpha-sub",
                "session_id": "alpha-sub-session",
                "saved_count": 0,
            }
        ]
        assert si.peek_interrupted_subagents(None) == []


class _FakeAgent:
    def __init__(self):
        self._message_history: list = []


class TestInjectionIsScoped:
    def test_inject_emits_only_current_root_notes(self):
        from code_puppy.agents._run_signals import inject_interrupted_subagent_notes

        with _Scope("B"):
            _record("beta", "beta-session", 2)
        agent = _FakeAgent()

        with _Scope("A"), patch("code_puppy.agents._run_signals.emit_info"):
            _record("alpha", "alpha-session", 4)
            inject_interrupted_subagent_notes(agent)

        assert len(agent._message_history) == 1
        note = agent._message_history[0].parts[0].content
        assert "alpha-session" in note
        assert "beta-session" not in note
        assert si.drain_interrupted_subagents() == []  # already drained in A
        assert si.peek_interrupted_subagents("B") == [
            {"agent_name": "beta", "session_id": "beta-session", "saved_count": 2}
        ]
