"""The system prompt must not drift between turns of one conversation.

``get_full_system_prompt`` appends every ``load_prompt`` plugin fragment on
every call, and pydantic-ai puts the result in ``instructions`` on EVERY
request message -- verified on a real thread, where messages 0/2 carried
5571 chars and 4/6 carried 6129.

``instructions`` is the provider's cache prefix. A fragment that grows as the
conversation proceeds -- a memory/recall plugin is the live example, since
it recalls what earlier turns just wrote -- therefore invalidates the prefix on
every turn. The user pays full uncached input for context that has not
changed, and pays more of it the longer they talk.

The fix is not to disable recall. It is that recall is CONTEXT, which belongs
in the conversation, and the system prompt is the CONTRACT, which does not
change mid-conversation. So volatile fragments are gathered once, when the
conversation begins, and a resumed turn keeps the prefix it already has.

"Begins" is read from the message history rather than a flag: an agent with
no history has nothing to resume, and an agent with history does. That needs
no new hook signature, no per-turn config, and cannot get out of sync with
the thing it describes.
"""

from __future__ import annotations

from typing import List

import pytest

from code_puppy.agents.base_agent import BaseAgent


class _Agent(BaseAgent):
    @property
    def name(self) -> str:
        return "test-agent"

    @property
    def display_name(self) -> str:
        return "Test Agent"

    @property
    def description(self) -> str:
        return "fixture"

    def get_system_prompt(self) -> str:
        return "SYSTEM"

    def get_available_tools(self):
        return []


@pytest.fixture
def growing_fragment(monkeypatch):
    """A plugin whose fragment grows every call, like kennel recall."""
    calls: List[int] = []

    def fake_on_load_prompt():
        calls.append(len(calls))
        return [f"MEMORY{'!' * len(calls)}"]

    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", fake_on_load_prompt)
    return calls


def test_first_turn_still_gets_its_fragments(growing_fragment):
    # The fix must not amount to switching recall off.
    agent = _Agent()
    assert "MEMORY" in agent.get_full_system_prompt()


def test_prompt_does_not_drift_before_the_first_turn(growing_fragment):
    # Setup calls this more than once before any history exists --
    # `_estimate_context_overhead` is one such caller -- so keying the cache
    # on "history is empty" would still re-poll and still drift, just
    # earlier. Reported by Copilot; measured at 2 polls and a changed prompt
    # before turn one had run.
    agent = _Agent()
    first = agent.get_full_system_prompt()
    second = agent.get_full_system_prompt()

    assert second == first
    assert len(growing_fragment) == 1


def test_prompt_is_byte_identical_once_the_conversation_has_started(
    growing_fragment,
):
    agent = _Agent()
    first = agent.get_full_system_prompt()

    # A turn happened: there is now history to resume from.
    agent.set_message_history([{"role": "user", "content": "hi"}])
    second = agent.get_full_system_prompt()
    third = agent.get_full_system_prompt()

    assert second == first, "the cache prefix changed on the second turn"
    assert third == first, "the cache prefix kept drifting"


def test_volatile_plugins_are_not_polled_once_started(growing_fragment):
    # Not just the same answer -- the fragments are not gathered at all.
    # A plugin that reaches a database or a network on every turn is latency
    # on the critical path of a turn that cannot use the result.
    agent = _Agent()
    agent.get_full_system_prompt()
    polls_after_first = len(growing_fragment)

    agent.set_message_history([{"role": "user", "content": "hi"}])
    agent.get_full_system_prompt()
    agent.get_full_system_prompt()

    assert len(growing_fragment) == polls_after_first


def test_clearing_history_starts_a_new_conversation(growing_fragment):
    # /clear means a new conversation, so recall is gathered afresh: the
    # prefix is allowed to change exactly when the conversation does.
    agent = _Agent()
    agent.get_full_system_prompt()
    agent.set_message_history([{"role": "user", "content": "hi"}])
    agent.get_full_system_prompt()

    before = len(growing_fragment)
    agent.clear_message_history()
    agent.get_full_system_prompt()
    assert len(growing_fragment) == before + 1


def test_identity_still_rides_at_the_end(growing_fragment):
    agent = _Agent()
    agent.set_message_history([{"role": "user", "content": "hi"}])
    assert agent.get_full_system_prompt().endswith(agent.get_identity_prompt())
