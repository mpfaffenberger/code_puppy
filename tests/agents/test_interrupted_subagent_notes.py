"""Parent-agent awareness of interrupted sub-agents.

When Ctrl-C cancels a delegated sub-agent, the parent run is torn down and its
return-less ``invoke_agent`` tool call is pruned from history -- so without an
explicit breadcrumb the model forgets it ever delegated. ``_invoke_agent_impl``
records each interruption; ``inject_interrupted_subagent_notes`` drains those
records at the next run start and appends a plain user-message note so the
model learns the run was stopped and exactly how to resume it.
"""

from types import SimpleNamespace
from unittest.mock import patch

from pydantic_ai.messages import ModelRequest, UserPromptPart

from code_puppy.agents._run_signals import inject_interrupted_subagent_notes
from code_puppy.tools.subagent_invocation import (
    drain_interrupted_subagents,
    record_interrupted_subagent,
)


def _note_text(message: ModelRequest) -> str:
    part = message.parts[0]
    assert isinstance(part, UserPromptPart)
    return part.content


def setup_function(_func):
    # Isolate the process-wide queue before every test.
    drain_interrupted_subagents()


def test_records_are_drained_and_injected_as_notes():
    record_interrupted_subagent(
        agent_name="code-reviewer",
        session_id="code-reviewer-session-a3f2b1",
        saved_count=18,
    )
    agent = SimpleNamespace(_message_history=["prior"])

    with patch("code_puppy.agents._run_signals.emit_info"):
        inject_interrupted_subagent_notes(agent)

    assert len(agent._message_history) == 2
    note = _note_text(agent._message_history[1])
    assert "code-reviewer" in note
    assert "code-reviewer-session-a3f2b1" in note
    assert "18 message(s)" in note
    # Queue is emptied so the note is injected exactly once.
    assert drain_interrupted_subagents() == []


def test_zero_saved_count_uses_no_completed_work_phrasing():
    record_interrupted_subagent(
        agent_name="researcher",
        session_id="researcher-session-xyz",
        saved_count=None,
    )
    agent = SimpleNamespace(_message_history=[])

    with patch("code_puppy.agents._run_signals.emit_info"):
        inject_interrupted_subagent_notes(agent)

    note = _note_text(agent._message_history[0])
    assert "no completed messages" in note
    assert "researcher-session-xyz" in note


def test_multiple_interruptions_each_get_a_note():
    for i in range(3):
        record_interrupted_subagent(
            agent_name=f"agent-{i}",
            session_id=f"agent-{i}-session",
            saved_count=i,
        )
    agent = SimpleNamespace(_message_history=[])

    with patch("code_puppy.agents._run_signals.emit_info"):
        inject_interrupted_subagent_notes(agent)

    assert len(agent._message_history) == 3
    assert all(isinstance(m, ModelRequest) for m in agent._message_history)


def test_empty_queue_is_a_noop():
    agent = SimpleNamespace(_message_history=["prior"])
    inject_interrupted_subagent_notes(agent)
    assert agent._message_history == ["prior"]


def test_agent_without_history_does_not_crash():
    record_interrupted_subagent(agent_name="a", session_id="a-session", saved_count=1)
    agent = SimpleNamespace()  # no _message_history attribute

    with patch("code_puppy.agents._run_signals.emit_info"):
        inject_interrupted_subagent_notes(agent)  # must not raise

    # Records are only consumed when there is somewhere to put them.
    assert not hasattr(agent, "_message_history")
