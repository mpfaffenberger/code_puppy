"""The personality plugin: who the main agent is, and only the main agent."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai_harness.subagents import SELF_AGENT_NAME, SubAgents

from code_puppy import personality
from code_puppy.personality import Personality, PersonalitySettings, PersonalitySource

BOODLER = PersonalitySettings(puppy_name="Boodler", owner_name="Mike")


class Host:
    """The parts of a ``PluginHost`` the plugin and its menu use."""

    def __init__(self, settings: PersonalitySettings = BOODLER) -> None:
        self.saved = settings

    def settings(self, model: type[PersonalitySettings]) -> PersonalitySettings:
        return self.saved

    def save_settings(self, settings: PersonalitySettings) -> None:
        self.saved = settings


def plugin(settings: PersonalitySettings = BOODLER) -> Personality:
    return Personality(Host(settings), settings)  # type: ignore[arg-type]


def instructions_of(messages: list[ModelMessage]) -> str:
    request = messages[-1]
    assert isinstance(request, ModelRequest)
    return request.instructions or ""


def test_persona_names_the_puppy_and_the_owner() -> None:
    text = personality.persona("Boodler", "Mike")
    assert text.startswith(
        "You are Boodler, the most loyal digital puppy, helping your owner Mike"
    )
    assert "DRY, YAGNI, and SOLID" in text and "Zen of Python" in text
    assert "'I am Boodler, authored on a rainy weekend in May 2025.'" in text
    assert "I am Boodler! \N{DOG FACE} A sassy" in text
    # Persona only: the tool and workflow rules belong to the runtime now.
    assert "MUST use the provided tools" not in text
    assert "{" not in text


def test_names_are_inserted_literally() -> None:
    assert "You are {x}, the most" in personality.persona("{x}", "Mike")


def test_settings_have_the_0_0_x_defaults_and_reject_empty_names() -> None:
    defaults = PersonalitySettings()
    assert (defaults.puppy_name, defaults.owner_name) == ("Puppy", "Master")
    with pytest.raises(ValidationError):
        PersonalitySettings(puppy_name="")
    with pytest.raises(ValidationError):
        PersonalitySettings(nickname="x")  # type: ignore[call-arg]


async def test_the_main_agent_is_told_who_it_is() -> None:
    seen: list[str] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(instructions_of(messages))
        return ModelResponse(parts=[TextPart("woof")])

    agent = Agent(FunctionModel(model), capabilities=list(plugin().get_capabilities()))
    await agent.run("hi")
    await agent.run("hi again")
    assert "You are Boodler" in seen[0]
    assert seen[0] == seen[1]  # identical on every request, so it stays cached


async def test_the_run_counter_does_not_leak_between_turns() -> None:
    """A leak would make every turn after the first look delegated, and lose the persona."""
    seen: list[str] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(instructions_of(messages))
        if len(seen) == 3:
            raise RuntimeError("model failed")
        return ModelResponse(parts=[TextPart("woof")])

    agent = Agent(FunctionModel(model), capabilities=list(plugin().get_capabilities()))
    async with agent.iter("streamed turn") as run:
        async for _ in run:
            pass
    await agent.run("plain turn")
    with pytest.raises(RuntimeError, match="model failed"):
        await agent.run("failing turn")
    await agent.run("turn after a failure")

    assert len(seen) == 4 and all("You are Boodler" in text for text in seen)
    assert personality.is_delegated_run() is False


async def test_delegated_sub_agents_get_no_persona() -> None:
    seen: dict[str, str] = {}

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        first = messages[0]
        assert isinstance(first, ModelRequest)
        prompt = str(first.parts[-1].content)  # type: ignore[union-attr]
        role = "child" if "fetch the bone" in prompt else "parent"
        seen.setdefault(role, instructions_of(messages))
        if role == "parent" and len(messages) == 1:
            call = ToolCallPart(
                tool_name="delegate_task",
                args={"agent_name": SELF_AGENT_NAME, "task": "fetch the bone"},
            )
            return ModelResponse(parts=[call])
        return ModelResponse(parts=[TextPart(f"{role} done")])

    capabilities: list[Any] = [
        SubAgents(include_self=True),
        *plugin().get_capabilities(),
    ]
    agent = Agent(FunctionModel(model), capabilities=capabilities)
    result = await agent.run("please delegate")

    assert result.output == "parent done"
    assert set(seen) == {"parent", "child"}, "the delegation did not run"
    assert "You are Boodler" in seen["parent"]
    assert "Boodler" not in seen["child"] and "digital puppy" not in seen["child"]


def test_settings_menu_edits_validates_and_resets() -> None:
    host = Host()
    source = PersonalitySource(host)  # type: ignore[arg-type]
    puppy, owner = source.rows()
    assert (puppy.key, puppy.label, puppy.default) == (
        "puppy_name",
        "Puppy name",
        "Puppy",
    )
    assert source.current(puppy) == "Boodler" and source.current(owner) == "Mike"

    assert source.problem(puppy, "   ") is not None
    assert source.problem(puppy, "Rex") is None
    assert source.apply(puppy, "  Rex ") == "Saved Puppy name."
    assert host.saved == PersonalitySettings(puppy_name="Rex", owner_name="Mike")
    assert source.reset(owner) == "Reset Owner name."
    assert host.saved.owner_name == "Master"


def test_plugin_declares_a_menu() -> None:
    menu = plugin().settings_menu()
    assert menu.source.title == "Personality"
