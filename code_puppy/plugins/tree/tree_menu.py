"""Searchable prompt_toolkit selector for Pi-style session trees."""

from __future__ import annotations

import shutil
import sys
import time
from typing import Optional

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.callbacks import on_prompt_toolkit_style
from code_puppy.i18n import t
from code_puppy.plugins.tree.tree_model import ConversationTree

_FILTERS = ("default", "no-tools", "user", "all")


class TreeMenu:
    """Single-pane tree browser with search, folding, filters, and copy."""

    def __init__(
        self, tree: ConversationTree, initial_id: Optional[str] = None
    ) -> None:
        if not tree.nodes:
            raise ValueError("TreeMenu requires at least one entry")
        self.tree = tree
        self.query = ""
        self.filter_mode = "default"
        self.folded: set[str] = set()
        self.rows: list[str] = []
        self.cursor = 0
        self.viewport_top = 0
        self.visible_rows = 20
        self.control: Optional[FormattedTextControl] = None
        self.result: Optional[str] = None
        self._preferred_id = initial_id or tree.leaf_id
        self.refresh()

    def refresh(self) -> None:
        previous = self.current_id or self._preferred_id
        candidates = self.tree.visible_nodes(self.filter_mode, self.query)
        hidden: set[str] = set()
        for node_id in self.folded:
            hidden.update(self._descendants(node_id))
        self.rows = [node_id for node_id in candidates if node_id not in hidden]
        if previous in self.rows:
            self.cursor = self.rows.index(previous)
        elif self.rows:
            ancestor = self._nearest_visible_ancestor(previous)
            self.cursor = self.rows.index(ancestor) if ancestor else len(self.rows) - 1
        else:
            self.cursor = 0
        self._scroll_into_view()
        if self.control:
            self.control.text = self.render()

    @property
    def current_id(self) -> Optional[str]:
        if not self.rows:
            return None
        return self.rows[self.cursor]

    def _descendants(self, node_id: str) -> set[str]:
        found: set[str] = set()
        stack = list(self.tree.nodes[node_id].children)
        while stack:
            child = stack.pop()
            found.add(child)
            stack.extend(self.tree.nodes[child].children)
        return found

    def _nearest_visible_ancestor(self, node_id: Optional[str]) -> Optional[str]:
        while node_id and node_id in self.tree.nodes:
            if node_id in self.rows:
                return node_id
            node_id = self.tree.nodes[node_id].parent_id
        return None

    def _depth(self, node_id: str) -> int:
        depth = 0
        parent = self.tree.nodes[node_id].parent_id
        while parent is not None and parent in self.tree.nodes:
            depth += 1
            parent = self.tree.nodes[parent].parent_id
        return depth

    def _scroll_into_view(self) -> None:
        page = max(1, self.visible_rows)
        if self.cursor < self.viewport_top:
            self.viewport_top = self.cursor
        elif self.cursor >= self.viewport_top + page:
            self.viewport_top = self.cursor - page + 1
        self.viewport_top = min(self.viewport_top, max(0, len(self.rows) - page))

    def render(self) -> FormattedText:
        fragments: list[tuple[str, str]] = [
            ("class:tui.title", f" {t('tree.title')}\n"),
            ("class:tui.muted", f" {t('tree.controls')}\n"),
            (
                "class:tui.muted",
                " "
                + t(
                    "tree.filter_search",
                    filter=self.filter_mode,
                    query=self.query or "—",
                )
                + "\n\n",
            ),
        ]
        if not self.rows:
            fragments.append(("class:tui.warning", f" {t('tree.no_results')}\n"))
            return FormattedText(fragments)

        active = set(self.tree.active_path)
        end = min(len(self.rows), self.viewport_top + self.visible_rows)
        for index in range(self.viewport_top, end):
            node_id = self.rows[index]
            node = self.tree.nodes[node_id]
            selected = index == self.cursor
            marker = "›" if selected else " "
            active_marker = "•" if node_id in active else " "
            fold = "⊞" if node_id in self.folded else ("⊟" if node.children else " ")
            indent = "  " * self._depth(node_id)
            label = f" [{node.label}]" if node.label else ""
            preview = " ".join(node.text.replace("\t", " ").splitlines())
            if len(preview) > 160:
                preview = preview[:159] + "…"
            style = "class:tui.selected" if selected else _role_style(node.role)
            fragments.append(
                (
                    style,
                    f"{marker} {indent}{fold}{active_marker} {node.role}{label}: {preview}\n",
                )
            )
        fragments.append(
            (
                "class:tui.muted",
                "\n "
                + t(
                    "tree.visible_count",
                    current=self.cursor + 1,
                    total=len(self.rows),
                )
                + "\n",
            )
        )
        return FormattedText(fragments)

    def _move(self, amount: int, *, wrap: bool = True) -> None:
        if not self.rows:
            return
        if wrap:
            self.cursor = (self.cursor + amount) % len(self.rows)
        else:
            self.cursor = max(0, min(len(self.rows) - 1, self.cursor + amount))
        self.refresh()

    def _toggle_fold(self, folded: bool) -> None:
        node_id = self.current_id
        if not node_id or not self.tree.nodes[node_id].children:
            return
        if folded:
            self.folded.add(node_id)
        else:
            self.folded.discard(node_id)
        self.refresh()

    def _cycle_filter(self) -> None:
        index = (_FILTERS.index(self.filter_mode) + 1) % len(_FILTERS)
        self.filter_mode = _FILTERS[index]
        self.folded.clear()
        self.refresh()

    def _copy_current(self, clipboard) -> None:
        node_id = self.current_id
        if not node_id:
            return
        try:
            clipboard.set_text(self.tree.nodes[node_id].text)
        except Exception:
            pass

    def build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("c-p")
        def _up(event):
            self._move(-1)

        @kb.add("down")
        @kb.add("c-n")
        def _down(event):
            self._move(1)

        @kb.add("pageup")
        @kb.add("left")
        @kb.add("c-b")
        def _page_up(event):
            self._move(-max(1, self.visible_rows), wrap=False)

        @kb.add("pagedown")
        @kb.add("right")
        @kb.add("c-f")
        def _page_down(event):
            self._move(max(1, self.visible_rows), wrap=False)

        @kb.add("c-left")
        @kb.add("escape", "left")
        def _fold(event):
            self._toggle_fold(True)

        @kb.add("c-right")
        @kb.add("escape", "right")
        def _unfold(event):
            self._toggle_fold(False)

        @kb.add("c-o")
        def _filter(event):
            self._cycle_filter()

        @kb.add("c-d")
        def _default_filter(event):
            self.filter_mode = "default"
            self.refresh()

        @kb.add("c-t")
        def _no_tools_filter(event):
            self.filter_mode = "no-tools"
            self.refresh()

        @kb.add("c-u")
        def _user_filter(event):
            self.filter_mode = "user"
            self.refresh()

        @kb.add("c-a")
        def _all_filter(event):
            self.filter_mode = "all"
            self.refresh()

        @kb.add("c-x")
        def _copy(event):
            self._copy_current(event.app.clipboard)

        @kb.add("backspace")
        def _backspace(event):
            if self.query:
                self.query = self.query[:-1]
                self.folded.clear()
                self.refresh()

        @kb.add("enter")
        def _select(event):
            self.result = self.current_id
            event.app.exit()

        @kb.add("escape")
        @kb.add("c-c")
        def _cancel(event):
            if self.query:
                self.query = ""
                self.folded.clear()
                self.refresh()
            else:
                self.result = None
                event.app.exit()

        @kb.add(Keys.Any)
        def _search(event):
            value = event.data
            if value and (
                value.isprintable() and (not value.isspace() or value == " ")
            ):
                self.query += value
                self.folded.clear()
                self.refresh()

        return kb

    def run(self) -> Optional[str]:
        cols, rows = shutil.get_terminal_size(fallback=(120, 40))
        self.visible_rows = max(5, rows - 9)
        self.control = FormattedTextControl(self.render())
        root = Frame(
            Window(self.control, wrap_lines=False), title=t("tree.frame_title")
        )
        app = Application(
            layout=Layout(root),
            key_bindings=self.build_keybindings(),
            full_screen=False,
            mouse_support=False,
            style=on_prompt_toolkit_style(),
        )
        try:
            from code_puppy.tools.command_runner import set_awaiting_user_input

            set_awaiting_user_input(True)
        except Exception:
            pass
        sys.stdout.write("\033[?1049h\033[2J\033[H")
        sys.stdout.flush()
        time.sleep(0.05)
        try:
            app.run(in_thread=True)
        finally:
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
            try:
                from code_puppy.tools.command_runner import set_awaiting_user_input

                set_awaiting_user_input(False)
            except Exception:
                pass
        return self.result


def _role_style(role: str) -> str:
    return {
        "user": "class:tui.success",
        "assistant": "class:tui.header",
        "tool": "class:tui.warning",
        "system": "class:tui.muted",
    }.get(role, "")


__all__ = ["TreeMenu"]
