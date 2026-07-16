"""Rendering for the /plugins TUI — split off so ``plugins_menu`` stays small.

These are pure-ish view functions: they take a :class:`PluginsMenu` (or a
plain plugin entry) and return ``(style, text)`` fragment tuples for
prompt_toolkit. No I/O, no key handling, no app state mutation. Keeping
them out of the menu class also makes the file split sustainable as more
detail sections get added.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple

from code_puppy.command_line.pagination import get_page_bounds, get_total_pages
from code_puppy.plugins.plugin_list.plugin_text_utils import (
    Fragments,
    count_lines,
    pad_lines_to_cells,
    strip_emojis_from_fragments,
    wrap_text,
)

if TYPE_CHECKING:  # pragma: no cover - import-cycle guard
    from code_puppy.plugins.plugin_list.plugins_menu import PluginsMenu, _PluginEntry

# Display order + labels for the "Contributes" section, keyed by the
# ``CATEGORY_*`` constants from ``plugin_contributions``.
_CONTRIB_LABELS: List[Tuple[str, str]] = [
    ("tools", "Tools"),
    ("commands", "Slash Commands"),
    ("agents", "Agents"),
    ("skills", "Skills"),
    ("model_types", "Model Types"),
    ("model_providers", "Model Providers"),
    ("mcp_servers", "MCP Servers"),
    ("browser_types", "Browser Types"),
    ("agent_tools", "Agent Tools"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _registers_command_handler(name: str) -> bool:
    """Whether *name* registered a ``custom_command`` hook.

    Such a plugin has a command handler but may lack ``custom_command_help``,
    so we know one exists without its name (hence the placeholder we surface).
    """
    from code_puppy.plugins.plugin_list import plugin_meta

    try:
        return "custom_command" in plugin_meta.get_hooks(name)
    except Exception:
        return False


def _append_wrapped(
    lines: Fragments, style: str, prefix: str, body: str, inner_width: int
) -> None:
    """Append *body* (wrapped to *inner_width*) under *prefix* with *style*."""
    for piece in wrap_text(body, inner_width):
        lines.append((style, f"{prefix}{piece}"))
        lines.append(("", "\n"))


# ---------------------------------------------------------------------------
# List pane (left)
# ---------------------------------------------------------------------------
def render_list(menu: "PluginsMenu") -> Fragments:
    lines: Fragments = []

    lines.append(("bold", " Plugins"))
    lines.append(("", "\n\n"))

    if menu.lock_builtin and menu.hidden_builtin_count:
        lines.append(
            (
                "class:tui.muted",
                f"  {menu.hidden_builtin_count} builtin plugins are "
                f"managed and hidden.",
            )
        )
        lines.append(("", "\n\n"))

    if not menu.plugins:
        if menu.lock_builtin and menu.hidden_builtin_count:
            lines.append(("class:tui.warning", "  No user or project plugins loaded."))
        else:
            lines.append(("class:tui.warning", "  No plugins loaded."))
        lines.append(("", "\n"))
        _render_hints(lines)
        return lines

    total_pages = get_total_pages(len(menu.plugins), menu.page_size)
    start_idx, end_idx = get_page_bounds(
        menu.current_page, len(menu.plugins), menu.page_size
    )

    for i in range(start_idx, end_idx):
        entry = menu.plugins[i]
        is_selected = i == menu.selected_idx
        is_disabled = entry.name in menu.disabled

        if entry.status == "loaded":
            icon = "x" if is_disabled else "+"
            icon_style = "class:tui.error" if is_disabled else "class:tui.success"
        else:
            # Trust-gated project plugin: discovered but never imported.
            icon = "!"
            icon_style = (
                "class:tui.error" if entry.status == "error" else "class:tui.warning"
            )
        prefix = " > " if is_selected else "   "

        if is_selected:
            lines.append(("class:tui.selected", prefix))
            lines.append(("class:tui.selected", icon))
            lines.append(("class:tui.selected", f" {entry.name}"))
        else:
            lines.append(("", prefix))
            lines.append((icon_style, icon))
            lines.append(("class:tui.muted", f" {entry.name}"))

        lines.append(("", "\n"))

    lines.append(("", "\n"))
    lines.append(("class:tui.muted", f" Page {menu.current_page + 1}/{total_pages}"))
    lines.append(("", "\n"))

    _render_hints(lines)
    return lines


def _render_hints(lines: Fragments) -> None:
    # Keys mirror the inspect_history plugin so muscle memory carries over
    # across both split-pane inspectors. See _build_key_bindings docstring
    # for the full mental model.
    hints: List[Tuple[str, str, str]] = [
        ("class:tui.help-key", "  up/down or j/k ", "Navigate"),
        ("class:tui.help-key", "  PgUp/PgDn      ", "Page"),
        ("class:tui.help-key", "  g / G          ", "First / Last"),
        ("class:tui.help-key", "  h/l or \u2190/\u2192    ", "Scroll details"),
        ("class:tui.help-key", "  Enter          ", "Toggle / Enable"),
        ("class:tui.help-key", "  q / Esc        ", "Exit"),
    ]
    lines.append(("", "\n"))
    for i, (style, key_text, label) in enumerate(hints):
        lines.append((style, key_text))
        lines.append(("", label if i == len(hints) - 1 else f"{label}\n"))


# ---------------------------------------------------------------------------
# Detail pane (right)
# ---------------------------------------------------------------------------

# Status line + explanation for project plugins the trust gate held back.
# ``{name}`` is substituted with the plugin name in the hint text.
_GATE_STATUS_DETAILS = {
    "untrusted": (
        "class:tui.warning",
        "Not enabled (project plugins are disabled by default)",
        "Press Enter to review its files and enable it.",
    ),
    "changed": (
        "class:tui.warning",
        "Changed since you accepted it",
        "Its files were modified after you trusted it, so trust was "
        "revoked. Press Enter to re-review and re-enable.",
    ),
    "disabled": (
        "class:tui.error",
        "Disabled (trusted, but not loaded)",
        "Press Enter to load it.",
    ),
    "error": (
        "class:tui.error",
        "Failed to load",
        "Check the logs, then press Enter to retry.",
    ),
}


def _render_gate_status(lines: Fragments, menu: "PluginsMenu", entry) -> None:
    """Status + hint for a project plugin that was never imported."""
    style, label, hint = _GATE_STATUS_DETAILS.get(
        entry.status,
        ("class:tui.warning", entry.status, "See '/plugins list' for details."),
    )
    lines.append(("bold", "  Status: "))
    lines.append((style, label))
    lines.append(("", "\n"))
    inner = max(20, menu._detail_cols - 4)
    _append_wrapped(lines, "class:tui.muted", "  ", hint.format(name=entry.name), inner)
    lines.append(("", "\n"))


def render_trust_modal(menu: "PluginsMenu") -> Fragments:
    """Body of the trust popup (the input box is a separate widget below).

    Kept deliberately stark: this is the security decision point, so it
    restates the risk and lists the files about to be executed.
    """
    from code_puppy.plugins.plugin_list.project_trust_flow import (
        ACCEPT_WORD,
        plugin_file_listing,
    )

    entry = menu.trust_target
    lines: Fragments = []
    if entry is None:
        return lines
    inner = 58  # popup is width-capped at 64; leave room for the frame

    reason = (
        "has CHANGED since you last accepted it"
        if entry.status == "changed"
        else "has never been enabled for this project"
    )
    _append_wrapped(lines, "class:tui.warning", " ", f"'{entry.name}' {reason}.", inner)
    lines.append(("", "\n"))
    _append_wrapped(
        lines,
        "",
        " ",
        "Project plugins run arbitrary code with YOUR permissions the "
        "moment they load. Only enable plugins you have reviewed.",
        inner,
    )
    lines.append(("", "\n"))

    if menu.project_dir:
        lines.append(("bold", " Files:"))
        lines.append(("", "\n"))
        from pathlib import Path

        listing = plugin_file_listing(Path(menu.project_dir) / entry.name, limit=8)
        for row in listing.splitlines():
            for piece in wrap_text(row.strip(), inner - 2):
                lines.append(("class:tui.header", f"   {piece}"))
                lines.append(("", "\n"))
        lines.append(("", "\n"))

    if menu.trust_error:
        _append_wrapped(lines, "class:tui.error", " ", menu.trust_error, inner)
        lines.append(("", "\n"))

    _append_wrapped(
        lines,
        "bold",
        " ",
        f"Type '{ACCEPT_WORD}' and press Enter to accept the risk — Esc cancels:",
        inner,
    )
    return lines


def render_detail(menu: "PluginsMenu") -> Fragments:
    lines: Fragments = []

    lines.append(("class:tui.title dim", " PLUGIN DETAILS"))
    lines.append(("", "\n\n"))

    # Outcome of the most recent enable/activate action, if any.
    if menu.trust_feedback:
        inner = max(20, menu._detail_cols - 4)
        _append_wrapped(lines, "class:tui.success", "  ", menu.trust_feedback, inner)
        lines.append(("", "\n"))

    entry = menu._current()
    if not entry:
        lines.append(("class:tui.warning", "  No plugin selected."))
        return lines

    from code_puppy.plugins.plugin_list import plugin_meta

    is_disabled = entry.name in menu.disabled

    lines.append(("bold", f"  {entry.name}"))
    lines.append(("", "\n\n"))

    # Pre-wrap to pane width: the Window runs wrap_lines=False (auto-wrap
    # bled chars into the divider column).
    description = plugin_meta.get_description(entry.name, entry.tier)
    if description:
        inner = max(20, menu._detail_cols - 4)  # -2 indent, -2 frame border
        _append_wrapped(lines, "", "  ", description, inner)
        lines.append(("", "\n"))

    lines.append(("bold", "  Tier: "))
    lines.append(("", entry.tier))
    lines.append(("", "\n\n"))

    # Trust is scoped per project path — always show which project this is.
    if entry.tier == "project" and menu.project_dir:
        lines.append(("bold", "  Project:"))
        lines.append(("", "\n"))
        inner = max(20, menu._detail_cols - 6)
        _append_wrapped(lines, "class:tui.muted", "    ", menu.project_dir, inner)
        lines.append(("", "\n"))

    if entry.status != "loaded":
        # Trust-gated: never imported, so hooks/contributions don't exist.
        _render_gate_status(lines, menu, entry)
        path = f"{menu.project_dir}/{entry.name}/" if menu.project_dir else None
        if path:
            lines.append(("bold", "  Path:"))
            lines.append(("", "\n"))
            inner = max(20, menu._detail_cols - 6)
            _append_wrapped(lines, "class:tui.muted", "    ", path, inner)
        return lines

    lines.append(("bold", "  Status: "))
    if is_disabled:
        lines.append(("class:tui.error", "Disabled"))
        lines.append(("", "\n"))
        lines.append(("class:tui.muted", "  Callbacks are skipped at dispatch time."))
    else:
        lines.append(("class:tui.success", "Enabled"))
        lines.append(("", "\n"))
        lines.append(("class:tui.muted", "  All callbacks are active."))
    lines.append(("", "\n\n"))

    _render_contributions(lines, menu, entry)

    hooks = plugin_meta.get_hooks(entry.name)
    lines.append(("bold", f"  Lifecycle hooks used ({len(hooks)}):"))
    lines.append(("", "\n"))
    if hooks:
        for hook in hooks:
            lines.append(("class:tui.header", f"    • {hook}"))
            lines.append(("", "\n"))
    else:
        lines.append(("class:tui.muted", "    (none registered)"))
        lines.append(("", "\n"))
    lines.append(("", "\n"))

    # Pre-wrap: paths can be very long.
    path = plugin_meta.get_file_path(entry.name, entry.tier)
    if path:
        lines.append(("bold", "  Path:"))
        lines.append(("", "\n"))
        inner = max(20, menu._detail_cols - 6)  # -4 indent, -2 frame border
        _append_wrapped(lines, "class:tui.muted", "    ", path, inner)
        lines.append(("", "\n"))

    if menu._changed:
        lines.append(("", "\n\n"))
        # Let the shared wrapper decide whether this fits on one line --
        # hard-coding a two-line split made the warning look broken on
        # any pane wider than ~50 cols (which is the common case).
        inner = max(20, menu._detail_cols - 4)  # -2 indent, -2 frame border
        _append_wrapped(
            lines,
            "class:tui.warning",
            "  ",
            "Restart Code Puppy for changes to take effect.",
            inner,
        )

    return lines


def _render_contributions(
    lines: Fragments, menu: "PluginsMenu", entry: "_PluginEntry"
) -> None:
    """Render the 'Contributes' section, grouped by non-empty category.

    Best-effort and display-only: extraction failures degrade to showing
    nothing extra rather than crashing the preview. Empty categories are
    skipped, and a command handler with no ``custom_command_help`` is
    surfaced as 'command handler (name unknown)'.
    """
    from code_puppy.plugins.plugin_list import plugin_contributions

    try:
        contributions = plugin_contributions.get_contributions(entry.name)
    except Exception:
        contributions = {}

    # Synthesize a placeholder only when custom_command_help gave us nothing
    # but a command handler exists.
    if not contributions.get(plugin_contributions.CATEGORY_COMMANDS):
        if _registers_command_handler(entry.name):
            contributions[plugin_contributions.CATEGORY_COMMANDS] = [
                "command handler (name unknown)"
            ]

    if not any(contributions.get(key) for key, _ in _CONTRIB_LABELS):
        return

    lines.append(("bold", "  Contributes:"))
    lines.append(("", "\n"))
    # Pre-wrap contribution items to the pane's inner width. Without this,
    # long entries (e.g. agent_skills /<skill-name> entries with trimmed
    # 80-char descriptions) extend past our padding cap and leave stale
    # tail glyphs (a literal "...") when the user switches to a plugin
    # whose detail content doesn't reach those columns.
    bullet_prefix = "      • "
    cont_prefix = "        "  # aligns continuation lines under the text
    inner = max(20, menu._detail_cols - 2 - len(bullet_prefix))
    for key, label in _CONTRIB_LABELS:
        items = contributions.get(key)
        if not items:
            continue
        lines.append(("class:tui.title", f"    {label}:"))
        lines.append(("", "\n"))
        for item in items:
            pieces = wrap_text(str(item), inner)
            for idx, piece in enumerate(pieces):
                prefix = bullet_prefix if idx == 0 else cont_prefix
                lines.append(("class:tui.header", f"{prefix}{piece}"))
                lines.append(("", "\n"))
    lines.append(("", "\n"))


# ---------------------------------------------------------------------------
# Pane post-processing (cell padding + blank-row fill)
# ---------------------------------------------------------------------------
def fill_pane(fragments: Fragments, pane_cols: int, pane_rows: int) -> Fragments:
    """Strip emojis, pad to pane width, fill to *pane_rows* rows.

    Emojis are stripped first (cell-width accounting in TUIs is fragile —
    cleaner to just not draw them), then each line is cell-padded to the
    pane's inner width and blank rows fill any unused height. The combo
    guarantees every visible cell is explicitly written every render.

    Takes scalar dimensions instead of the whole menu so this stays a pure
    function over its inputs (Law of Demeter — the renderer doesn't need to
    know about ``PluginsMenu``'s shape).
    """
    fragments = strip_emojis_from_fragments(fragments)
    current_lines = count_lines(fragments)
    out = list(fragments)
    # Ensure the final line ends with a newline so blank padding lines up.
    if out and not out[-1][1].endswith("\n"):
        out.append(("", "\n"))
        current_lines += 1
    blanks_needed = max(0, pane_rows - current_lines)
    if blanks_needed:
        out.append(("", "\n" * blanks_needed))
    return pad_lines_to_cells(out, max(0, pane_cols - 2))
