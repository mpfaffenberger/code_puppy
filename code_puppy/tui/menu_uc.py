"""Phase 3: /uc universal-constructor tool browser as Textual screens.

list tools -> per-tool actions (enable/disable toggle, view source). Reuses
the list kit + a small source viewer; toggling/source loading go through the
existing uc_menu helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .screens.base import FilterableListScreen, ListChoice

if TYPE_CHECKING:
    from .app import CooperApp


def open_uc(app: "CooperApp") -> None:
    from code_puppy.command_line.uc_menu import _get_tool_entries
    from code_puppy.messaging import emit_info

    tools = _get_tool_entries()
    if not tools:
        emit_info("No universal-constructor tools found.")
        return

    by_name = {t.full_name: t for t in tools}
    choices = []
    for tool in tools:
        suffix = "" if tool.meta.enabled else "   [disabled]"
        choices.append(
            ListChoice(
                id=tool.full_name,
                label=f"{tool.full_name}{suffix}",
                search=tool.full_name,
            )
        )

    def _on_pick(name) -> None:
        tool = by_name.get(name) if name else None
        if tool is not None:
            _open_tool_actions(app, tool)

    app.push_screen(
        FilterableListScreen("Universal Constructor tools", choices), _on_pick
    )


def _open_tool_actions(app: "CooperApp", tool) -> None:
    toggle_label = "Disable this tool" if tool.meta.enabled else "Enable this tool"
    choices = [
        ListChoice(id="toggle", label=toggle_label),
        ListChoice(id="source", label="View source"),
    ]

    def _on_action(action) -> None:
        if action == "toggle":
            from code_puppy.command_line.uc_menu import _toggle_tool_enabled

            _toggle_tool_enabled(tool)
        elif action == "source":
            _open_source(app, tool)

    app.push_screen(
        FilterableListScreen(f"Tool: {tool.full_name}", choices), _on_action
    )


def _open_source(app: "CooperApp", tool) -> None:
    from code_puppy.command_line.uc_menu import _load_source_code

    from .screens.source_view import SourceViewScreen

    lines, error = _load_source_code(tool)
    app.push_screen(SourceViewScreen(tool.full_name, "\n".join(lines or []), error))
