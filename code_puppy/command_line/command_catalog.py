"""Enumerate every command /help can advertise.

Registry commands and callback-advertised plugin commands are listed apart
because /help renders them under different headings, even when a registry
command has category "plugin".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from code_puppy.command_line.help_catalog import _parse_custom_command_result
from code_puppy.error_logging import log_error


@dataclass(frozen=True)
class CommandEntry:
    name: str
    description: str
    usage: str
    hint: str
    aliases: tuple[str, ...]
    category: str
    interactive: bool


_ALTERNATIVE_SEPARATOR = re.compile(r",\s*(?=/)")


def _hint_from_usage(usage: str) -> str:
    """Return the argument hint of the first alternative that takes one."""
    for alternative in _ALTERNATIVE_SEPARATOR.split(usage):
        parts = alternative.strip().lstrip("/").split(maxsplit=1)
        remainder = parts[1].strip() if len(parts) == 2 else ""
        if remainder:
            return remainder
    return ""


def list_registry_commands() -> list[CommandEntry]:
    # Lazy so the built-in command modules register even when the CLI runs
    # headless; command_handler imports this module lazily for the same reason.
    import code_puppy.command_line.command_handler  # noqa: F401
    from code_puppy.command_line.command_registry import get_unique_commands

    return [
        CommandEntry(
            name=info.name,
            description=info.description,
            usage=info.usage,
            hint=_hint_from_usage(info.usage),
            aliases=tuple(info.aliases),
            category=info.category,
            interactive=info.interactive,
        )
        for info in sorted(get_unique_commands(), key=lambda c: c.name)
    ]


def list_plugin_commands() -> list[CommandEntry]:
    """Commands advertised through ``on_custom_command_help()``.

    Fail-soft to []: an unexpected failure is logged once; control-flow
    exceptions (``BaseException``) propagate.
    """
    try:
        from code_puppy import callbacks

        pairs = [
            pair
            for result in callbacks.on_custom_command_help()
            for pair in _parse_custom_command_result(result)
        ]
    except Exception as exc:
        try:
            log_error(
                exc, context="command_catalog::list_plugin_commands: callbacks failed"
            )
        except Exception:
            pass  # a failing logger must never change the fail-soft result
        return []
    return [
        CommandEntry(
            name=name,
            description=description,
            usage=f"/{name}",
            hint="",
            aliases=(),
            category="plugin",
            interactive=False,
        )
        for name, description in pairs
    ]


def list_commands() -> list[CommandEntry]:
    """Registry commands, then plugin commands; first entry per name wins.

    Plugins can advertise one command twice (a skill listed by two plugins).
    Registry-first, then callback order, matches the order dispatch tries them.
    """
    unique: dict[str, CommandEntry] = {}
    for entry in list_registry_commands() + list_plugin_commands():
        unique.setdefault(entry.name, entry)
    return list(unique.values())
