"""Tests for the scoped unattended-run system instruction."""

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
        assert full_prompt.index(_HEADLESS_AUTONOMY_PROMPT) < full_prompt.index(
            "Your ID is"
        )

    assert _HEADLESS_AUTONOMY_PROMPT not in agent.get_full_system_prompt()
