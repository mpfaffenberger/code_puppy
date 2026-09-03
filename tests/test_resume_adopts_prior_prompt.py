"""A resume adopts the prompt and identity the conversation already had.

``set_message_history`` is the real resume door. Every front door that
continues a conversation goes through it -- the CLI via
``restore_named_session``, an embedding runner by calling it directly, a
headless loop rebuilding an agent per turn. Hanging resume behaviour off
``restore_named_session`` alone fixes exactly one of those callers, which is
how a previous attempt at this passed its tests while every other front end
was unchanged.

Two things must survive, and the history already carries both:

``instructions``
    pydantic-ai stamps the system prompt onto every request message, so a
    restored history knows the prompt it was built with. That string is the
    provider's cache prefix. Recomputing it in a fresh process yields a
    different one -- a live timestamp, a grown recall block -- and the cache
    misses on every turn of a long conversation, which is precisely when it
    was worth having.

``agent_id``
    ...is not in the history, so it is passed in. The prompt tells the agent
    to use its id "for claiming task ownership or coordination with other
    agents"; an id minted per process cannot own anything.

The conversation is the authority here, not the process. Measured on a real
thread before this: three turns, three identities, and the instructions
block moving 5571 -> 6175 characters.
"""

from __future__ import annotations

from typing import Any, Dict, List

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


def _request(instructions: str | None) -> Dict[str, Any]:
    """A restored request message, shaped like pydantic-ai's wire format."""
    return {"kind": "request", "instructions": instructions, "parts": []}


@pytest.fixture
def drifting(monkeypatch):
    """A load_prompt fragment that differs every call, like kennel recall."""
    calls: List[int] = []

    def fake_on_load_prompt():
        calls.append(len(calls))
        return [f"MEMORY{'!' * len(calls)}"]

    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", fake_on_load_prompt)
    return calls


def test_a_resumed_agent_keeps_the_prompt_the_history_was_built_with(drifting):
    # The whole point: a fresh process resuming a conversation must present
    # the SAME prefix, not a freshly computed one.
    #
    # The id is passed because identity is NOT part of the frozen body -- it
    # is rendered each turn from `self.id`, so that there is one
    # representation of it rather than a field and a copy inside a string.
    # A caller that wants the identical prefix therefore has to supply the
    # conversation's id, which every real resume path already stores.
    first = _Agent()
    opening = first.get_full_system_prompt()

    resumed = _Agent()  # new process, new uuid, fragments would differ
    resumed.set_message_history([_request(opening)], agent_id=first.id)

    assert resumed.get_full_system_prompt() == opening


def test_identity_is_restored_when_the_caller_knows_it(drifting):
    # An embedding runner stores the id beside its thread; the CLI reads it
    # from the session sidecar. Either way the caller passes it in, because
    # the history does not carry it.
    original = _Agent()
    resumed = _Agent()
    assert resumed.id != original.id

    resumed.set_message_history([_request(None)], agent_id=original.id)
    assert resumed.id == original.id


def test_a_fresh_conversation_is_unaffected(drifting):
    # Setting an EMPTY history is not a resume. Nothing to adopt, so the
    # agent keeps its own identity and computes its own prompt.
    agent = _Agent()
    before = agent.id
    agent.set_message_history([])

    assert agent.id == before
    assert "MEMORY" in agent.get_full_system_prompt()


def test_history_without_instructions_falls_back_to_computing_one(drifting):
    # Histories written before instructions were recorded, or by a caller
    # that strips them. A resume must still work; it just cannot inherit a
    # prefix that was never stored.
    agent = _Agent()
    agent.set_message_history([_request(None)])
    assert "MEMORY" in agent.get_full_system_prompt()


def test_the_adopted_prompt_does_not_drift_across_later_turns(drifting):
    # Adopting once is not enough if the next call recomputes.
    first = _Agent()
    opening = first.get_full_system_prompt()
    resumed = _Agent()
    resumed.set_message_history([_request(opening)], agent_id=first.id)

    assert resumed.get_full_system_prompt() == opening
    assert resumed.get_full_system_prompt() == opening


def test_clearing_history_starts_over(drifting):
    # /clear ends the conversation, so its prompt and cached fragments go
    # with it: the prefix is allowed to change exactly when the conversation
    # does.
    first = _Agent()
    opening = first.get_full_system_prompt()
    agent = _Agent()
    agent.set_message_history([_request(opening)], agent_id=first.id)
    assert agent.get_full_system_prompt() == opening

    agent.clear_message_history()
    assert agent.get_full_system_prompt() != opening
