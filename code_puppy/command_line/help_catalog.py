"""Content assembly for the Tab-toggled help overlay (see help_overlay.py).

An assembler, not a source of truth: content comes from the existing
command registry and plugin callbacks, plus static sections for things
with no registry of their own (keybindings, input modes).

Scope is deliberately the first layer -- commands themselves, not their
arguments. ``/set`` gets a row; its individual config keys and the
environment variables behind them do not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from code_puppy.keymap import get_cancel_agent_display_name


@dataclass(frozen=True)
class HelpEntry:
    """One row in a help section: a short left-hand label + description."""

    left: str
    right: str = ""


@dataclass(frozen=True)
class HelpSection:
    """A titled group of :class:`HelpEntry` rows."""

    title: str
    entries: List[HelpEntry] = field(default_factory=list)


_CATEGORY_TITLES: Dict[str, str] = {
    "core": "Core Commands",
    "config": "Configuration Commands",
    "session": "Session Commands",
    "tools": "Tool Commands",
}

#: Folded into the callback-sourced "Plugin / Private Commands" section
#: rather than getting its own, which would render a bare "PLUGIN" heading
#: directly above it.
_PLUGIN_REGISTRY_CATEGORY = "plugin"


def _normalize_custom_command_entries() -> List[Tuple[str, str]]:
    """Flatten the several return shapes ``on_custom_command_help()`` allows.

    Mirrors the tolerant parsing in ``command_handler.get_commands_help()``
    and ``SlashCompleter.get_completions()``, and additionally strips a
    leading "/" so a slash-prefixed name can't render as "//name".
    """
    entries: List[Tuple[str, str]] = []
    try:
        from code_puppy import callbacks, plugins

        plugins.load_plugin_callbacks()
        for res in callbacks.on_custom_command_help():
            entries.extend(_parse_custom_command_result(res))
    except Exception:
        # Cheat sheet content must never crash the Tab key.
        pass
    return entries


def _parse_custom_command_result(res) -> List[Tuple[str, str]]:
    """Parse one plugin's ``on_custom_command_help()`` return value.

    Tolerates every shape the callback contract allows: a bare
    ``(name, description)`` tuple, a list of such tuples, or the legacy
    list-of-strings form (``"/name - Description"``).
    """
    if not res:
        return []
    if isinstance(res, tuple) and len(res) == 2:
        return [(_strip_leading_slash(res[0]), str(res[1]))]
    if isinstance(res, list):
        parsed: List[Tuple[str, str]] = []
        for item in res:
            if isinstance(item, tuple) and len(item) == 2:
                parsed.append((_strip_leading_slash(item[0]), str(item[1])))
            elif isinstance(item, str) and item.startswith("/") and " - " in item:
                name, _, description = item.partition(" - ")
                parsed.append((_strip_leading_slash(name), description.strip()))
        return parsed
    return []


def _strip_leading_slash(name) -> str:
    return str(name).lstrip("/").strip()


def _builtin_command_sections() -> Tuple[List[HelpSection], List[HelpEntry]]:
    """Group registered commands into titled sections.

    Returns ``(sections, plugin_category_entries)``. Commands registered
    with ``category="plugin"`` come back separately so the caller can merge
    them into the single section built by ``_plugin_command_section()``.
    """
    from code_puppy.command_line.command_registry import get_unique_commands

    try:
        commands = get_unique_commands()
    except Exception:
        return [], []

    by_category: Dict[str, List[HelpEntry]] = {}
    for cmd in sorted(commands, key=lambda c: c.name):
        label = cmd.usage or f"/{cmd.name}"
        if cmd.aliases:
            alias_list = ", ".join("/" + a for a in cmd.aliases)
            label += f" (aliases: {alias_list})"
        by_category.setdefault(cmd.category, []).append(
            HelpEntry(label, cmd.description)
        )

    plugin_category_entries = by_category.pop(_PLUGIN_REGISTRY_CATEGORY, [])

    sections = []
    # Stable, curated order first; anything unexpected still shows up.
    for category in ("core", "config", "session", "tools"):
        entries = by_category.pop(category, None)
        if entries:
            title = _CATEGORY_TITLES.get(category, category.title())
            sections.append(HelpSection(title, entries))
    for category, entries in by_category.items():
        sections.append(
            HelpSection(_CATEGORY_TITLES.get(category, category.title()), entries)
        )
    return sections, plugin_category_entries


def _plugin_command_section(
    builtin_plugin_entries: List[HelpEntry],
) -> List[HelpSection]:
    """One merged section for both plugin-command sources.

    Combines callback-advertised commands (``on_custom_command_help()``)
    with registry commands filed under ``category="plugin"``.
    """
    callback_entries = _normalize_custom_command_entries()
    callback_rows = [HelpEntry(f"/{name}", desc) for name, desc in callback_entries]
    all_rows = list(builtin_plugin_entries) + callback_rows
    if not all_rows:
        return []
    all_rows.sort(key=lambda e: e.left)
    return [HelpSection("Plugin / Private Commands", all_rows)]


def _keybinding_section() -> HelpSection:
    cancel_key = get_cancel_agent_display_name()
    entries = [
        HelpEntry("Tab (empty line)", "Toggle this help overlay"),
        HelpEntry("Tab (mid-word)", "Complete / cycle completions forward"),
        HelpEntry("Shift+Tab (mid-word)", "Cycle completions backward"),
        HelpEntry("/exit, /quit, Ctrl+D", "Exit interactive mode"),
        HelpEntry(
            cancel_key,
            "Clear input if composing; cancel task if empty",
        ),
    ]
    # Only meaningful once the cancel key has been remapped: plain Ctrl+C
    # keeps its own separate clear-the-line behavior in that case.
    if cancel_key != "Ctrl+C":
        entries.append(HelpEntry("Ctrl+C", "Clear the current input buffer"))
    entries.append(
        HelpEntry(
            "Alt+Enter",
            "Submit as a queued turn (after current, or now if idle)",
        )
    )
    entries.extend(
        [
            HelpEntry("Alt+M or F2", "Toggle multiline input"),
            HelpEntry(
                "Ctrl+J, Shift+Enter, or Ctrl+Enter",
                "Insert a newline (Ctrl+J is most reliable across terminals)",
            ),
            HelpEntry("Ctrl+V / F3", "Paste an image (Ctrl+V works on macOS too)"),
            HelpEntry("Ctrl+X Ctrl+E", "Edit the prompt in $EDITOR"),
            HelpEntry("Ctrl+X Ctrl+B", "Background a running shell command"),
            HelpEntry("Ctrl+X Ctrl+X", "Kill a running shell command"),
            HelpEntry("@", "Path completion / attach a file"),
            HelpEntry("Ctrl+A / Ctrl+E", "Jump to the start / end of the line"),
            HelpEntry("Ctrl+U", "Clear the whole input buffer"),
            HelpEntry("Ctrl+W", "Delete the word before the cursor"),
            HelpEntry("Ctrl+R", "Start a reverse history search"),
            HelpEntry(
                "Ctrl+Left/Right, Option+Left/Right, or Meta-b/f",
                "Jump the cursor by one word",
            ),
        ]
    )
    # Ctrl+K is kill-to-end-of-line (line_editor.py), but when it's the
    # configured cancel key it never reaches the editor, so documenting
    # that binding would be a lie.
    if cancel_key != "Ctrl+K":
        entries.append(
            HelpEntry("Ctrl+K", "Kill (delete) from the cursor to the end of the line")
        )
    return HelpSection("Keybindings", entries)


def _modes_section() -> HelpSection:
    return HelpSection(
        "Modes & Passthrough",
        [
            HelpEntry("Multiline mode", "Alt+M / F2 toggles; Enter inserts a newline"),
            HelpEntry("YOLO mode", "/set yolo_mode on -- skip confirmation prompts"),
            HelpEntry("!<command>", "Run a shell command directly (e.g. !git status)"),
            HelpEntry("/autosave_load", "Resume a previous autosave session"),
            HelpEntry("/tutorial", "Re-run the onboarding tutorial"),
        ],
    )


def _mcp_plugins_section() -> HelpSection:
    return HelpSection(
        "MCP & Plugins",
        [
            HelpEntry("/mcp", "List, add, and manage MCP servers"),
            HelpEntry(
                "Plugins",
                "Loaded automatically at startup; extend commands, models, and callbacks",
            ),
        ],
    )


_SECTION_ORDER: Tuple[str, ...] = (
    "Session Commands",
    "Keybindings",
    "Core Commands",
    "Modes & Passthrough",
    "Configuration Commands",
    "MCP & Plugins",
    "Plugin / Private Commands",
    "Tool Commands",
)


def build_help_sections() -> List[HelpSection]:
    """Assemble every section shown in the Tab-toggled help overlay.

    Sections are sorted into ``_SECTION_ORDER``, a curated display order.
    Titles missing from that tuple (e.g. a new command category) sort to
    the end rather than vanishing or raising.

    Agent switching is covered by the ``/agent`` row the command registry
    already provides; listing every installed agent here would duplicate
    what ``/agent`` prints on its own.
    """
    sections: List[HelpSection] = []
    builtin_sections, builtin_plugin_entries = _builtin_command_sections()
    sections.extend(builtin_sections)
    sections.extend(_plugin_command_section(builtin_plugin_entries))
    sections.append(_keybinding_section())
    sections.append(_modes_section())
    sections.append(_mcp_plugins_section())

    order_index = {title: i for i, title in enumerate(_SECTION_ORDER)}
    sections.sort(key=lambda s: order_index.get(s.title, len(_SECTION_ORDER)))
    return sections
