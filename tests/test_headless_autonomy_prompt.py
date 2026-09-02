"""Tests for the scoped unattended-run system instruction."""

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from code_puppy.agents.base_agent import BaseAgent
from code_puppy.cli_runner import _HEADLESS_AUTONOMY_PROMPT


class _TestAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "test-agent"

    @property
    def display_name(self) -> str:
        return "Test Agent"

    @property
    def description(self) -> str:
        return "Test agent"

    def get_system_prompt(self) -> str:
        return "Authored prompt."

    def get_available_tools(self) -> list[str]:
        return []


def _resumed_from(agent: _TestAgent, prompt: str) -> _TestAgent:
    """A fresh agent resuming the conversation ``agent`` was running.

    Mirrors the headless loop: the history carries the prompt the turn was
    sent under, and the caller passes the id its own store already holds.

    Real ``ModelRequest``/``ModelResponse`` objects rather than a stand-in
    with an ``instructions`` attribute. A stand-in cannot drift when
    pydantic-ai changes shape, which is precisely the blind spot that let an
    earlier fix pass its tests while every real front end was unchanged.
    """
    resumed = _TestAgent()
    resumed.set_message_history(
        [
            ModelRequest(
                parts=[UserPromptPart(content="continue")], instructions=prompt
            ),
            ModelResponse(parts=[TextPart(content="ok")]),
        ],
        agent_id=agent.id,
    )
    return resumed


def test_headless_autonomy_prompt_is_scoped_to_the_run(monkeypatch):
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])
    agent = _TestAgent()

    assert _HEADLESS_AUTONOMY_PROMPT not in agent.get_full_system_prompt()

    with agent.temporary_system_prompt_addition(_HEADLESS_AUTONOMY_PROMPT):
        full_prompt = agent.get_full_system_prompt()
        assert _HEADLESS_AUTONOMY_PROMPT in full_prompt
        assert full_prompt.index("Authored prompt.") < full_prompt.index(
            _HEADLESS_AUTONOMY_PROMPT
        )
        # Scoped text sits AFTER the identity line, not before it. That is
        # what makes it unadoptable on resume: the durable part is everything
        # up to the identity marker, so an ephemeral addition cannot be
        # mistaken for part of the conversation's cached prefix.
        assert full_prompt.index("Your ID is") < full_prompt.index(
            _HEADLESS_AUTONOMY_PROMPT
        )

    assert _HEADLESS_AUTONOMY_PROMPT not in agent.get_full_system_prompt()


def test_runtime_addition_applies_to_a_resumed_conversation(monkeypatch):
    """A resume adopts the cached BODY; it does not opt out of runtime additions.

    ``code-puppy -p`` on an existing session is the live path: the run is
    wrapped in ``temporary_system_prompt_addition`` but the agent is resuming,
    so an adopted body that short-circuits the assembly drops the instruction
    that tells the agent it is unattended.
    """
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])

    interactive = _TestAgent()
    turn_one = interactive.get_full_system_prompt()
    assert _HEADLESS_AUTONOMY_PROMPT not in turn_one

    resumed = _resumed_from(interactive, turn_one)
    with resumed.temporary_system_prompt_addition(_HEADLESS_AUTONOMY_PROMPT):
        assert _HEADLESS_AUTONOMY_PROMPT in resumed.get_full_system_prompt()

    assert _HEADLESS_AUTONOMY_PROMPT not in resumed.get_full_system_prompt()


def test_runtime_addition_does_not_survive_into_a_resume(monkeypatch):
    """The scoped addition must not be frozen into the next turn's prefix.

    The headless loop calls ``set_message_history`` AFTER the ``with`` block
    exits (cli_runner.py), so the addition is already popped from the list --
    but the history it adopts was sent under a prompt that still contains it.
    Adopting that verbatim re-introduces the instruction permanently, where no
    ``finally`` can pop it, and welds it into the provider's cache prefix.
    """
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])

    headless = _TestAgent()
    with headless.temporary_system_prompt_addition(_HEADLESS_AUTONOMY_PROMPT):
        turn_one = headless.get_full_system_prompt()
    assert _HEADLESS_AUTONOMY_PROMPT in turn_one

    resumed = _resumed_from(headless, turn_one)
    assert _HEADLESS_AUTONOMY_PROMPT not in resumed.get_full_system_prompt()


def test_resume_still_adopts_the_cached_body(monkeypatch):
    """The fix must not cost the cache prefix it was written to protect.

    Guards the obvious over-correction: refusing to adopt whenever a runtime
    addition was present would trade a scoping bug for a cache miss on every
    turn of every headless conversation.
    """
    calls = []

    def _drifting():
        calls.append(len(calls))
        return [f"RECALL-BLOCK-{len(calls)}"]

    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", _drifting)

    first = _TestAgent()
    turn_one = first.get_full_system_prompt()
    assert "RECALL-BLOCK-1" in turn_one

    resumed = _resumed_from(first, turn_one)
    turn_two = resumed.get_full_system_prompt()

    assert turn_two == turn_one, "resumed prefix drifted; provider cache misses"
    assert "RECALL-BLOCK-2" not in turn_two


def test_the_cached_prefix_is_stable_across_headless_turns(monkeypatch):
    """The cache pin for the path this fix actually changed.

    ``test_resume_still_adopts_the_cached_body`` never enters the scoped
    block, so it cannot see drift on headless turns -- it passes even on the
    unfixed code. This one resumes WITH the addition applied, which is what
    ``code-puppy -p`` against an existing session does.
    """
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])

    first = _TestAgent()
    with first.temporary_system_prompt_addition(_HEADLESS_AUTONOMY_PROMPT):
        turn_one = first.get_full_system_prompt()

    resumed = _resumed_from(first, turn_one)
    with resumed.temporary_system_prompt_addition(_HEADLESS_AUTONOMY_PROMPT):
        turn_two = resumed.get_full_system_prompt()

    assert turn_two == turn_one, "headless prefix drifted between turns"


def test_a_session_from_an_older_build_is_healed(monkeypatch):
    """Earlier builds stored the addition inside the durable body.

    The ordering fix cannot reach it there, so without healing the
    instruction is re-applied to every later turn of a resumed session --
    including interactive ones, telling a user's own session never to ask
    them for confirmation. ``/clear`` was the only escape.
    """
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])

    original = _TestAgent()
    legacy_prompt = (
        "Authored prompt.\n"
        + _HEADLESS_AUTONOMY_PROMPT
        + original.get_identity_prompt()
    )

    resumed = _resumed_from(original, legacy_prompt)
    healed = resumed.get_full_system_prompt()

    assert _HEADLESS_AUTONOMY_PROMPT not in healed
    assert "Authored prompt." in healed
    assert "Your ID is" in healed

    # And it stays healed: the poison must not creep back turn over turn.
    again = _resumed_from(resumed, healed)
    assert _HEADLESS_AUTONOMY_PROMPT not in again.get_full_system_prompt()


def test_identity_is_split_on_the_last_marker(monkeypatch):
    """``_strip_identity_prompt`` uses ``rpartition``, and that is load-bearing.

    Downstream code appends after the identity line (``_builder`` adds
    AGENTS.md rules and model guards), so the LAST marker is the correct
    split point. A refactor to ``partition`` or ``split`` would silently
    adopt a truncated body and drift the prefix; nothing pinned that before.
    """
    monkeypatch.setattr("code_puppy.callbacks.on_load_prompt", lambda: [])

    agent = _TestAgent()
    body = "Authored prompt."
    # A prompt that mentions the marker text before the real identity line.
    prior = body + "\n\nYour ID is `quoted-elsewhere`." + agent.get_identity_prompt()

    resumed = _resumed_from(agent, prior)
    assert resumed._adopted_prompt_body == body + "\n\nYour ID is `quoted-elsewhere`."
