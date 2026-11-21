"""The first-launch ritual: name the puppy and tell it who its owner is.

0.0.x asked two questions before its first prompt. 1.0 asks the same two, once,
and saves the answers as the ``personality`` plugin's settings, so ``/plugins
configure personality`` edits the very same values afterwards.

There is no separate "already asked" flag. A name is unanswered while it is
missing from the plugin's saved settings, and every way out of the questions
(an answer, a bare Enter, Ctrl-C) saves a value for each of them. A setup
carried over from 0.0.x arrives with both names, so it is never asked.

Only a person at a terminal is asked. ``pup -p``, ``--web`` and subcommands
never reach :func:`welcome`, and piped input is turned away by
:func:`at_a_terminal`; those launches run with the defaults and leave the
questions for the next interactive one.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from code_puppy import identity
from code_puppy.personality import (
    FACTORY,
    PLUGIN_ID,
    PersonalitySettings,
    default_name,
    name_problem,
)

if TYPE_CHECKING:
    from pydantic_ai_pax.config import PluginSettings
    from pydantic_ai_pax.config.settings_store import SettingsStore

QUESTIONS = {
    "puppy_name": "What should we name the puppy?",
    "owner_name": f"What's your name (so {identity.DISPLAY_NAME} knows its owner)?",
}
"""The 0.0.x questions, by the setting each one fills in. Asked in this order."""

INTRO = f"Welcome to {identity.DISPLAY_NAME}! First things first (Enter keeps the name in brackets)."
CONFIGURE = f"/plugins configure {PLUGIN_ID}"

Read = Callable[[str], str | None]
"""Show a question and return the typed line, or ``None`` when the user backed out."""
Write = Callable[[str], None]


def at_a_terminal() -> bool:
    """Whether a person can be asked: both ends of the conversation are a terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def read_line(question: str) -> str | None:
    """Ask on stdout and read one line; ``None`` on Ctrl-C or end of input.

    Not ``input(question)``: it writes its prompt to stderr, which the terminal
    UI relays elsewhere while a session starts.
    """
    print(question, end=" ", flush=True)
    try:
        line = sys.stdin.readline()
    except KeyboardInterrupt:
        line = ""
    if not line.endswith("\n"):
        print()  # Ctrl-C and Ctrl-D leave the cursor on the question's line.
        return None
    return line


def declaration(store: SettingsStore) -> PluginSettings | None:
    """The saved ``personality`` declaration, or ``None`` when nothing was ever saved for it."""
    return next((p for p in store.plugins() if p.id == PLUGIN_ID), None)


def unanswered(store: SettingsStore) -> tuple[str, ...]:
    """The names nobody has chosen yet; none when the plugin that uses them is off."""
    saved = declaration(store)
    if saved is None:
        return tuple(QUESTIONS)
    if not saved.enabled:
        return ()
    return tuple(key for key in QUESTIONS if key not in saved.settings)


def ask(keys: Sequence[str], *, read: Read, write: Write) -> dict[str, str]:
    """A name for every key: the answer, or the default for a bare Enter.

    Backing out of one question keeps the defaults for it and the rest.
    """
    answers: dict[str, str] = {}
    backed_out = False
    for key in keys:
        answers[key] = default_name(key)
        while not backed_out:
            line = read(f"{QUESTIONS[key]} [{default_name(key)}]")
            if line is None:
                backed_out = True
            elif not (text := line.strip()):
                break
            elif (why := name_problem(key, text)) is None:
                answers[key] = text
                break
            else:
                write(f"That will not work: {why}")
    return answers


def save(store: SettingsStore, answers: dict[str, str]) -> PersonalitySettings:
    """Add the answers to the plugin's saved settings; return the names now in effect."""
    from pydantic_ai_pax.config import PluginSettings

    saved = declaration(store) or PluginSettings(id=PLUGIN_ID, factory=FACTORY)
    settings = {**saved.settings, **answers}
    names = PersonalitySettings.model_validate(settings)
    store.save_plugin(saved.model_copy(update={"settings": settings}))
    return names


def welcome(
    store: SettingsStore, *, read: Read = read_line, write: Write = print
) -> PersonalitySettings | None:
    """Ask for the names still unanswered and save them; ``None`` when there were none."""
    keys = unanswered(store)
    if not keys:
        return None
    write(INTRO)
    names = save(store, ask(keys, read=read, write=write))
    write(
        f"Meet {names.puppy_name}, {names.owner_name}'s puppy. "
        f"Change either name any time with {CONFIGURE}."
    )
    return names
