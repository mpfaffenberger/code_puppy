"""Code Puppy's personality: the built-in ``personality`` plugin.

The runtime's coding instructions are plain. This plugin adds who the agent
*is*: its name, its owner's name, its tone and its few strong opinions. The
text is the persona part of the 0.0.x system prompt; the tool and workflow
rules that used to follow it are the runtime's job now.

* **Main agent only.** Delegated sub-agents do the work they are handed and
  report back; they get no persona. A sub-agent's run starts inside the main
  agent's run, which is how it is told apart.
* **Stable text.** The instructions are built once when the plugin loads, so
  they are identical on every request and stay in the prompt cache.
* **Off switch.** ``/plugins disable personality`` gives a plain agent.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, AgentCapability, WrapRunHandler
from pydantic_ai.run import AgentRunResult
from pydantic_ai_pax.plugins import Plugin, PluginHost
from pydantic_ai_pax.plugins.menus import FieldRow, SettingsMenu

PLUGIN_ID = "personality"
FACTORY = "code_puppy.personality:Personality"
DEFAULT_PUPPY_NAME = "Puppy"
DEFAULT_OWNER_NAME = "Master"


class PersonalitySettings(BaseModel):
    """What the agent calls itself and the person it works for."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    puppy_name: str = Field(
        default=DEFAULT_PUPPY_NAME,
        min_length=1,
        max_length=80,
        description="What the agent calls itself.",
    )
    owner_name: str = Field(
        default=DEFAULT_OWNER_NAME,
        min_length=1,
        max_length=80,
        description="What the agent calls you.",
    )


def default_name(key: str) -> str:
    """The name a setting has until somebody chooses one."""
    return str(PersonalitySettings.model_fields[key].default)


def name_problem(key: str, text: str) -> str | None:
    """Why ``text`` cannot be this name, in the settings model's words; ``None`` when it can."""
    try:
        PersonalitySettings.model_validate({key: text})
    except ValueError as exc:
        return str(exc).splitlines()[-1].strip()
    return None


def persona(puppy_name: str, owner_name: str) -> str:
    """The persona instructions for one puppy and one owner."""
    return f"""\
You are {puppy_name}, the most loyal digital puppy, helping your owner {owner_name} get coding stuff done!

Be super informal - we're here to have fun. Don't be scared of being a little bit sarcastic too.
Be very pedantic about code principles like DRY, YAGNI, and SOLID.
Be fun and playful. Don't be too serious.

Keep files under 600 lines. If a file grows beyond that, consider splitting into smaller subcomponents—but don't split purely to hit a line count if it hurts cohesion.
Always obey the Zen of Python, even if you are not writing Python code.

If asked about your origins: 'I am {puppy_name}, authored on a rainy weekend in May 2025.'
If asked 'what is code puppy': 'I am {puppy_name}! \N{DOG FACE} A sassy, open-source AI code agent—no bloated IDEs, or closed-source vendor traps needed.'"""


_run_depth: ContextVar[int] = ContextVar("code_puppy_persona_run_depth", default=0)
"""How many runs carrying the persona enclose the current code: 1 in the main agent's run."""


def is_delegated_run() -> bool:
    """Whether the current run was started from inside another run that has the persona."""
    return _run_depth.get() > 1


@dataclass
class Persona(AbstractCapability[Any]):
    """The persona as instructions for the outermost run only.

    A delegated sub-agent runs inside a tool call of the run that delegated to
    it, so it inherits that run's context. Counting the enclosing runs in a
    context variable tells the two apart without asking the delegation
    machinery, whichever way the delegation was started.
    """

    text: str

    def get_instructions(self) -> Callable[[RunContext[Any]], str | None]:
        def instructions(ctx: RunContext[Any]) -> str | None:
            return None if is_delegated_run() else self.text

        return instructions

    async def wrap_run(
        self, ctx: RunContext[Any], *, handler: WrapRunHandler
    ) -> AgentRunResult[Any]:
        # Set before `handler()`: instruction resolution and tool tasks see it.
        token = _run_depth.set(_run_depth.get() + 1)
        try:
            return await handler()
        finally:
            _run_depth.reset(token)


ROW_LABELS = {"puppy_name": "Puppy name", "owner_name": "Owner name"}


class PersonalitySource:
    """The two names as menu rows, saved through the validated settings model."""

    title = "Personality"

    def __init__(self, host: PluginHost[Any]) -> None:
        self.host = host

    def rows(self) -> tuple[FieldRow, ...]:
        fields = PersonalitySettings.model_fields
        return tuple(
            FieldRow(
                key=key,
                label=label,
                description=fields[key].description or "",
                default=default_name(key),
            )
            for key, label in ROW_LABELS.items()
        )

    def current(self, row: FieldRow) -> str:
        return str(getattr(self.host.settings(PersonalitySettings), row.key))

    def _updated(self, row: FieldRow, raw: str) -> PersonalitySettings:
        data = self.host.settings(PersonalitySettings).model_dump()
        data[row.key] = raw.strip()
        return PersonalitySettings.model_validate(data)

    def problem(self, row: FieldRow, text: str) -> str | None:
        return name_problem(row.key, text.strip())

    def apply(self, row: FieldRow, raw: str) -> str:
        self.host.save_settings(self._updated(row, raw))
        return f"Saved {row.label}."

    def reset(self, row: FieldRow) -> str:
        self.host.save_settings(self._updated(row, default_name(row.key)))
        return f"Reset {row.label}."


class Personality(Plugin[PersonalitySettings, Any]):
    """Gives the main agent Code Puppy's name, tone and opinions."""

    def get_capabilities(self) -> Sequence[AgentCapability[Any]]:
        text = persona(self.settings.puppy_name, self.settings.owner_name)
        return (Persona(text=text),)

    def settings_menu(self) -> SettingsMenu:
        return SettingsMenu(source=PersonalitySource(self.host))
