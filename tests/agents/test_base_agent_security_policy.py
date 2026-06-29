"""Security-policy guarantees for ``BaseAgent.get_full_system_prompt``.

The security policy text must reach every agent's runtime system prompt
regardless of which concrete subclass produced it (built-in agents,
user-defined ``JSONAgent``s, fork-only agents, …) and regardless of which
plugins happen to be loaded. These tests pin that guarantee at the chokepoint
so a future refactor can't silently regress it.
"""

from __future__ import annotations

import json
from typing import List

from code_puppy.agents.base_agent import SECURITY_POLICY_PROMPT, BaseAgent
from code_puppy.agents.json_agent import JSONAgent


class _StubAgent(BaseAgent):
    """Minimal concrete BaseAgent so we can exercise the chokepoint directly.

    All five abstract members are stubbed with the smallest possible values.
    ``get_system_prompt`` returns an empty string on purpose so any text in
    the assembled prompt has to come from layers under test (load_prompt
    fragments, security policy, identity).
    """

    @property
    def name(self) -> str:
        return "stub"

    @property
    def display_name(self) -> str:
        return "Stub"

    @property
    def description(self) -> str:
        return "stub agent for security-policy tests"

    def get_system_prompt(self) -> str:
        return ""

    def get_available_tools(self) -> List[str]:
        return []


def test_security_policy_reaches_base_agent_chokepoint() -> None:
    """Direct BaseAgent path: the policy must always be appended."""
    full_prompt = _StubAgent().get_full_system_prompt()
    assert SECURITY_POLICY_PROMPT in full_prompt


def test_security_policy_reaches_json_agent(tmp_path) -> None:
    """User-defined JSON agents must also get the policy. This is the path
    most likely to be forgotten in a future refactor, so pin it explicitly."""
    config = {
        "name": "test_agent",
        "description": "A test agent",
        "system_prompt": "You are a test agent",
        "tools": ["list_files"],
    }
    agent_file = tmp_path / "test_agent.json"
    agent_file.write_text(json.dumps(config))

    full_prompt = JSONAgent(str(agent_file)).get_full_system_prompt()
    assert SECURITY_POLICY_PROMPT in full_prompt


def test_security_policy_mentions_real_remediation_paths() -> None:
    """Guard against a well-meaning future revision that strips the
    "real fix / escalate to security" escape valve and leaves only the
    prohibition. Without the escape valve the LLM has no fallback when no
    patch exists and tends to produce bad advice. Keep both halves."""
    assert "Snyk" in SECURITY_POLICY_PROMPT
    assert "real fix" in SECURITY_POLICY_PROMPT
    assert "escalate" in SECURITY_POLICY_PROMPT
