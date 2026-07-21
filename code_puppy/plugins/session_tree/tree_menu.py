"""Prompt-toolkit TUI for session tree selection."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_page_for_index,
    get_total_pages,
)

from .tree_model import (
    FILTER_MODES,
    FilterMode,
    HistoryNode,
    build_nodes,
    visible_nodes,
)
from .tree_store import SessionTree

TREE_PAGE_SIZE = 14


@dataclass(slots=True)
class TreeMenuResult:
    node: HistoryNode | None = None
    cancelled: bool = False
    summarize: bool = False
    custom_summary_focus: str = ""


@dataclass(slots=True)
class TreeSelectionMenu:
    tree: SessionTree
    mode: FilterMode = FilterMode.DEFAULT
    selected_index: int = 0
    page: int = 0
    page_size: int = TREE_PAGE_SIZE
    result: TreeMenuResult = field(default_factory=TreeMenuResult)
    show_label_timestamps: bool = False
    search_query: str = ""

    def __post_init__(self) -> None:
        self._clamp_selection()

    @property
    def nodes(self) -> list[HistoryNode]:
        return build_nodes(self.tree)

    @property
    def visible(self) -> list[HistoryNode]:
        return visible_nodes(self.nodes, self.mode, self.search_query)

    @property
    def total_pages(self) -> int:
        return get_total_pages(len(self.visible), self.page_size)

    @property
    def page_start(self) -> int:
        start, _ = get_page_bounds(self.page, len(self.visible), self.page_size)
        return start

    @property
    def page_end(self) -> int:
        _, end = get_page_bounds(self.page, len(self.visible), self.page_size)
        return end

    @property
    def page_nodes(self) -> list[HistoryNode]:
        return self.visible[self.page_start : self.page_end]

    def selected_node(self) -> HistoryNode | None:
        if 0 <= self.selected_index < len(self.visible):
            return self.visible[self.selected_index]
        return None

    def _clamp_selection(self) -> None:
        if not self.visible:
            self.selected_index = 0
            self.page = 0
            return
        self.selected_index = max(0, min(self.selected_index, len(self.visible) - 1))
        self.page = ensure_visible_page(
            self.selected_index, self.page, len(self.visible), self.page_size
        )

    def _move(self, delta: int) -> None:
        self.selected_index += delta
        self._clamp_selection()

    def _page(self, delta: int) -> None:
        if not self.visible:
            return
        self.page = max(0, min(self.page + delta, self.total_pages - 1))
        self.selected_index = self.page_start

    def _cycle_filter(self) -> None:
        modes = list(FILTER_MODES)
        next_index = (modes.index(self.mode) + 1) % len(modes)
        selected = self.selected_node()
        self.mode = modes[next_index]
        if selected and selected in self.visible:
            self.selected_index = self.visible.index(selected)
        else:
            self.selected_index = 0
        self._clamp_selection()

    def _toggle_label_timestamp(self) -> None:
        self.show_label_timestamps = not self.show_label_timestamps

    def _toggle_label(self) -> None:
        selected = self.selected_node()
        if selected is None:
            return
        self.tree.set_label(selected.node_id, None if selected.label else "label")

    def _branch_prefix(self, node: HistoryNode) -> str:
        ancestors = "".join(
            "│  " if has_next else "   " for has_next in node.ancestor_has_next
        )
        if node.depth == 0:
            return ""
        return f"{ancestors}{'└─ ' if node.is_last else '├─ '}"

    def _render(self):
        lines = [("bold cyan", "  Session Tree")]
        lines.append(("fg:ansibrightblack", f"\n  Filter: {self.mode.value}"))
        lines.append(
            (
                "fg:ansibrightblack",
                f"  Search: {self.search_query or '(type to search)'}",
            )
        )
        if self.total_pages > 1:
            lines.append(
                ("fg:ansibrightblack", f"  Page {self.page + 1}/{self.total_pages}")
            )
        lines.append(("", "\n"))

        if not self.visible:
            lines.append(("fg:ansiyellow", "\n  No entries match this filter.\n\n"))
        for offset, node in enumerate(self.page_nodes):
            absolute_index = self.page_start + offset
            is_selected = absolute_index == self.selected_index
            is_active = node.is_active
            cursor = " › " if is_selected else "   "
            style = "fg:ansiwhite bold" if is_selected else "fg:ansibrightblack"
            timestamp = ""
            if self.show_label_timestamps and node.label_timestamp:
                timestamp = f" @{node.label_timestamp[11:16]}"
            label = f" [{node.label}{timestamp}]" if node.label else ""
            active = " ← active" if is_active else ""
            path_marker = "• " if node.is_on_active_path else "  "
            lines.append(
                (
                    style,
                    f'{cursor}{self._branch_prefix(node)}{path_marker}{node.role}: "{node.preview}"',
                )
            )
            lines.append(("fg:ansiblue", f" #{node.node_id}{label}{active}\n"))

        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓  "))
        lines.append(("", "Navigate\n"))
        lines.append(("fg:ansibrightblack", "  ←/→ PgUp/PgDn  "))
        lines.append(("", "Page\n"))
        lines.append(("fg:ansibrightblack", "  Ctrl+O  "))
        lines.append(("", "Cycle filter\n"))
        lines.append(("fg:ansibrightblack", "  L  "))
        lines.append(("", "Set/clear label\n"))
        lines.append(("fg:ansibrightblack", "  T  "))
        lines.append(("", "Toggle label timestamps\n"))
        lines.append(("fg:ansigreen", "  Enter  "))
        lines.append(("", "Select/restore\n"))
        lines.append(("fg:ansigreen", "  S  "))
        lines.append(("", "Summarize through selection as new conversation\n"))
        lines.append(("fg:ansiyellow", "  Esc/Ctrl+C  "))
        lines.append(("", "Cancel\n"))
        return lines

    async def run_async(self) -> TreeMenuResult:
        control = FormattedTextControl(lambda: self._render())
        kb = KeyBindings()

        def refresh(event) -> None:
            control.text = self._render()
            event.app.invalidate()

        @kb.add("up")
        @kb.add("c-p")
        def _(event):
            self._move(-1)
            refresh(event)

        @kb.add("down")
        @kb.add("c-n")
        def _(event):
            self._move(1)
            refresh(event)

        @kb.add("pageup")
        @kb.add("left")
        def _(event):
            self._page(-1)
            refresh(event)

        @kb.add("pagedown")
        @kb.add("right")
        def _(event):
            self._page(1)
            refresh(event)

        @kb.add("c-o")
        def _(event):
            self._cycle_filter()
            refresh(event)

        @kb.add("L")
        @kb.add("l")
        def _(event):
            self._toggle_label()
            refresh(event)

        @kb.add("T")
        @kb.add("t")
        def _(event):
            self._toggle_label_timestamp()
            refresh(event)

        @kb.add("enter")
        def _(event):
            self.result.node = self.selected_node()
            event.app.exit()

        @kb.add("S")
        @kb.add("s")
        def _(event):
            self.result.node = self.selected_node()
            self.result.summarize = True
            event.app.exit()

        @kb.add("backspace")
        def _(event):
            if self.search_query:
                self.search_query = self.search_query[:-1]
                self.selected_index = 0
                self._clamp_selection()
                refresh(event)

        @kb.add("<any>")
        def _(event):
            text = event.data
            if text and text.isprintable():
                self.search_query += text
                self.selected_index = 0
                self._clamp_selection()
                refresh(event)

        @kb.add("escape")
        @kb.add("c-c")
        def _(event):
            if self.search_query:
                self.search_query = ""
                self.selected_index = 0
                self._clamp_selection()
                refresh(event)
                return
            self.result.cancelled = True
            event.app.exit()

        sys.stdout.write("\033[?1049h\033[2J\033[H")
        sys.stdout.flush()
        try:
            app = Application(
                layout=Layout(Window(content=control, wrap_lines=True)),
                key_bindings=kb,
                full_screen=False,
            )
            await app.run_async()
        finally:
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
        return self.result


def selected_index_to_page(index: int, page_size: int = TREE_PAGE_SIZE) -> int:
    return get_page_for_index(index, page_size)
