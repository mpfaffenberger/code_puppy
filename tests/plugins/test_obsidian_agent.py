"""Tests for the built-in Obsidian Agent plugin."""

from code_puppy.plugins.obsidian_agent.agent_obsidian import ObsidianAgent
from code_puppy.plugins.obsidian_agent.register_callbacks import register_agents


PRIVATE_DEFAULT_MARKERS = [
    "/" + "users/",
    "c:" + "\\users\\",
    "library/" + "mobile" + " documents",
    "daily reports",
    "example-vault-that-should-not-be-hard-coded",
]


def test_obsidian_agent_metadata_and_tools() -> None:
    agent = ObsidianAgent()

    assert agent.name == "obsidian-agent"
    assert agent.display_name == "Obsidian Agent 🪨"
    assert "Obsidian" in agent.description
    assert agent.get_available_tools() == [
        "agent_run_shell_command",
        "ask_user_question",
    ]


def test_obsidian_agent_prompt_includes_safety_guidance() -> None:
    prompt = ObsidianAgent().get_system_prompt()

    assert "official `obsidian` CLI" in prompt
    assert "Discover before modifying" in prompt
    assert "Ask for explicit confirmation" in prompt
    assert "Never run arbitrary JavaScript" in prompt
    assert "agent_run_shell_command" in prompt


def test_obsidian_agent_prompt_has_no_personal_defaults() -> None:
    agent = ObsidianAgent()
    searchable = "\n".join(
        [
            agent.description,
            agent.get_user_prompt(),
            agent.get_system_prompt(),
        ]
    ).lower()

    for marker in PRIVATE_DEFAULT_MARKERS:
        assert marker not in searchable


def test_obsidian_agent_registers_with_plugin_hook() -> None:
    registrations = register_agents()

    assert registrations == [{"name": "obsidian-agent", "class": ObsidianAgent}]
