"""Content assembly for the Tab-toggled help overlay (see help_overlay.py).

This module is an ASSEMBLER, not a new source of truth: it pulls content
from the registries/callbacks that already exist (command registry, plugin
callbacks, agent manager) plus a handful of static, curated sections for
things that have no dynamic registry of their own (keybindings, input
modes). Deliberately NOT a new command-registration framework -- see
PUP-352's PLAN.md for why.

Deliberately NOT documented here: environment variables, and any setting
reachable only as an argument to a command (e.g. a specific ``/set <key>``).
Those are second-layer detail -- the goal of this cheat sheet is a
discoverable first layer of *commands* (``/set`` itself, not every key it
accepts); most commands are self-explanatory once you're inside them.
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

#: Registry category folded into the callback-sourced plugin section (see
#: _builtin_command_sections / _plugin_command_section) rather than getting
#: its own titled section -- installed plugins that register commands via
#: category="plugin" would otherwise render a bare "PLUGIN" heading sitting
#: directly above "Plugin / Private Commands", two near-identical adjacent
#: headings being exactly the confusion PUP-352 exists to remove (confirmed
#: live against the private fork's installed plugin set).
_PLUGIN_REGISTRY_CATEGORY = "plugin"


def _normalize_custom_command_entries() -> List[Tuple[str, str]]:
    """Flatten the several return shapes ``on_custom_command_help()`` allows.

    Mirrors (and slightly hardens -- always strips a leading "/" so a
    slash-prefixed name can never produce a "//name" label) the tolerant
    parsing already done ad hoc in ``command_handler.get_commands_help()``
    and ``SlashCompleter.get_completions()`` -- kept local and small rather
    than unifying all three call sites, which would widen this ticket's
    diff well beyond startup/help UX (see PLAN.md non-goals).
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

    Returns ``(sections, plugin_category_entries)`` -- commands registered
    with ``category="plugin"`` are pulled out separately rather than given
    their own titled section, so the caller can fold them into the same
    "Plugin / Private Commands" section that ``_plugin_command_section()``
    builds from ``on_custom_command_help()`` (see ``_PLUGIN_REGISTRY_CATEGORY``
    docstring for why: two near-identical adjacent headings is exactly the
    confusion PUP-352 exists to remove).
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
    """One merged section for BOTH plugin-command sources.

    Combines callback-advertised commands (``on_custom_command_help()``)
    with any registry commands filed under ``category="plugin"`` --
    deliberately one section, not two, even though they come from two
    different registries (see ``_builtin_command_sections()``).
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
    # cancel_key defaults to "Ctrl+C" everywhere; only show a second row when
    # it's been remapped (e.g. to Ctrl+K) -- plain Ctrl+C independently keeps
    # its own "clear the line" meaning even then, which is worth surfacing,
    # but showing it unconditionally would just re-create the exact
    # same-label-twice confusion this replaces (see PUP-352 review notes).
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
    # Ctrl+K is normally "kill to end of line" (line_editor.py), but when
    # it's the configured cancel key it's fully intercepted before reaching
    # the editor and kill-to-EOL becomes unreachable -- showing both
    # meanings would recreate the exact Ctrl+C double-meaning bug this
    # section was just fixed for (see PUP-352 puppy-review validation).
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
            HelpEntry("/diff", "Configure diff highlighting colors"),
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

    Sections are built independently, then sorted into the fixed
    ``_SECTION_ORDER`` above -- a curated display order, not a reflection
    of build order or importance. Any section whose title isn't in that
    tuple (e.g. an unexpected new command category) sorts after the named
    ones rather than vanishing or raising -- ``list.sort`` is stable, so
    unranked sections keep their relative build order among themselves.

    Note: agent-switching is documented via the ``/agent`` entry that
    ``_builtin_command_sections()`` already surfaces from the core command
    registry (usage \"/agent <name>, /a <name>\", aliases included) --
    deliberately NOT a separate per-agent listing here. A full roster of
    every installed agent belongs to ``/agent`` itself (it already prints
    one when run with no argument), not to a cheat sheet whose job is
    pointing at the *command*, not duplicating its live output.
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
