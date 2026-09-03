"""One identity, held as a field rather than recovered from prose.

Freezing the WHOLE prompt on resume put the identity inside the frozen
string, which left two representations of one fact: the id rendered into
that text, and ``self.id``. They could disagree, and nothing noticed.

Recovering the id by regexing the rendered sentence would close the gap and
create worse problems: the round trip is lossy (the line shows six
characters of a uuid), and the wording of an English sentence becomes
load-bearing, so translating or rewording it silently breaks identity.

The fix is to not put it there. ``get_identity_prompt`` is appended LAST and
is a pure function of ``self.id``, so the cached part is the prompt BODY and
the identity line is rendered fresh each turn from the one field that holds
it. Same bytes when the id is the same, and no parsing anywhere.

The body is what actually needs freezing: it carries the timestamps and the
growing recall block that made the prefix drift. The identity line is stable
by construction once the id is.
"""

from __future__ import annotations

import re

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


class _Request:
    def __init__(self, instructions: str | None) -> None:
        self.instructions = instructions
        self.kind = "request"


def _rendered_id(prompt: str) -> str | None:
    found = re.search(r"test-agent-[0-9a-f]+", prompt)
    return found.group() if found else None


def test_an_agent_always_reports_the_identity_it_is_sending():
    # The invariant, stated once: whoever asks, one answer. It holds because
    # both sides read `self.id`, not because two copies were kept in step.
    agent = _Agent()
    assert agent.get_identity() == _rendered_id(agent.get_full_system_prompt())


def test_that_invariant_survives_a_resume():
    first = _Agent()
    opening = first.get_full_system_prompt()

    resumed = _Agent()
    resumed.set_message_history([_Request(opening)], agent_id=first.id)

    assert resumed.get_identity() == _rendered_id(resumed.get_full_system_prompt())
    assert resumed.get_full_system_prompt() == opening


def test_the_full_uuid_survives_not_just_its_first_six_characters():
    # What a lossy round trip through the rendered line would have cost.
    first = _Agent()
    resumed = _Agent()
    resumed.set_message_history(
        [_Request(first.get_full_system_prompt())], agent_id=first.id
    )
    assert resumed.id == first.id


def test_resuming_without_an_id_keeps_the_prompt_and_stays_consistent():
    # Any caller that does not pass an id -- an older front end, or one
    # whose store has none yet. The
    # agent introduces itself under its own name -- what it must NOT do is
    # send one name and report another.
    first = _Agent()
    opening = first.get_full_system_prompt()

    resumed = _Agent()
    resumed.set_message_history([_Request(opening)])

    assert resumed.get_identity() == _rendered_id(resumed.get_full_system_prompt())


def test_the_cached_body_is_reused_across_turns():
    # The reason any of this is frozen: the body drifts, and drift costs a
    # cache miss on every turn of a long conversation.
    calls: list[int] = []

    class _Drifting(_Agent):
        def get_system_prompt(self) -> str:
            calls.append(len(calls))
            return f"SYSTEM v{len(calls)}"

    first = _Drifting()
    opening = first.get_full_system_prompt()

    resumed = _Drifting()
    resumed.set_message_history([_Request(opening)], agent_id=first.id)

    assert resumed.get_full_system_prompt() == opening
    assert resumed.get_full_system_prompt() == opening


def test_the_identity_sentence_can_be_reworded_without_breaking_identity():
    # The property lost by parsing prose: this text is presentation, and
    # editing it must not corrupt a field.
    class _Reworded(_Agent):
        def get_identity_prompt(self) -> str:
            return f"\n\n[[agent={self.get_identity()}]]"

    agent = _Reworded()
    assert agent.get_identity() in agent.get_full_system_prompt()

    resumed = _Reworded()
    resumed.set_message_history(
        [_Request(agent.get_full_system_prompt())], agent_id=agent.id
    )
    assert resumed.id == agent.id
    assert resumed.get_identity() in resumed.get_full_system_prompt()


def test_two_fresh_agents_still_differ():
    assert _Agent().id != _Agent().id
