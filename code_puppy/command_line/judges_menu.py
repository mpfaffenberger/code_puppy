"""Interactive terminal UI for configuring goal-mode LLM judges.

A split-panel list (left = judges, right = preview), with an in-TUI
form for adding/editing — no $EDITOR popout. Everything happens in
prompt_toolkit, so the UX stays inside the terminal session.

List view keys:
  N           add new judge (opens form)
  Enter / E   edit selected judge (opens form)
  T           toggle enabled
  D           delete selected
  Esc / Ctrl+C  close menu

Form view keys:
  Tab / Shift+Tab     cycle between Name ↔ Model ↔ Prompt
  ↑ / ↓               (when Model is focused) select model
  ←→ / PgUp PgDn      (when Model is focused) page through models
  Home / End          (when Model is focused) jump to first / last model
  Ctrl+S              save
  Esc / Ctrl+C        cancel
"""

from __future__ import annotations

import asyncio
import sys
import unicodedata
from typing import Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame, TextArea

from code_puppy.command_line.model_picker_completion import load_model_names
from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_page_for_index,
    get_total_pages,
)
from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.plugins.wiggum.judge_config import (
    DEFAULT_JUDGE_PROMPT,
    JudgeConfig,
    add_judge,
    delete_judge,
    load_judges,
    toggle_judge,
    update_judge,
    validate_name,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 10


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _sanitize(text: str) -> str:
    """Strip characters that mess with prompt_toolkit width calculations."""
    safe = (
        "Lu",
        "Ll",
        "Lt",
        "Lm",
        "Lo",
        "Nd",
        "Nl",
        "No",
        "Pc",
        "Pd",
        "Ps",
        "Pe",
        "Pi",
        "Pf",
        "Po",
        "Zs",
        "Sm",
        "Sc",
        "Sk",
    )
    cleaned = "".join(c for c in text if unicodedata.category(c) in safe)
    return " ".join(cleaned.split())


def _wrap(text: str, width: int) -> list[str]:
    """Crude word-wrap for the preview panel."""
    out: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            out.append("")
            continue
        words = line.split()
        current = ""
        for word in words:
            if not current:
                current = word
            elif len(current) + 1 + len(word) > width:
                out.append(current)
                current = word
            else:
                current += " " + word
        if current:
            out.append(current)
    return out


# ---------------------------------------------------------------------------
# Model list (inline paginated picker rendered as a tabbable form section)
# ---------------------------------------------------------------------------

MODEL_PAGE_SIZE = 8  # rows of models visible at once in the form section


def _load_available_models() -> list[str]:
    """Return the list of model names, or [] if loading fails."""
    try:
        return load_model_names() or []
    except Exception as exc:
        emit_warning(f"Failed to load models: {exc}")
        return []


def _render_model_list(
    models: list[str],
    selected_idx: int,
    page: int,
    *,
    focused: bool,
) -> list:
    """Render the inline paginated model list with a selection marker."""
    lines: list = []

    if not models:
        lines.append(("fg:yellow", "  No models available."))
        lines.append(("", "\n"))
        lines.append(
            (
                "fg:ansibrightblack",
                "  Configure models first — see /model in the main CLI.",
            )
        )
        return lines

    total_pages = get_total_pages(len(models), MODEL_PAGE_SIZE)
    start, end = get_page_bounds(page, len(models), MODEL_PAGE_SIZE)

    # Header: (Page x/y, focused indicator)
    if focused:
        lines.append(("fg:ansigreen bold", "▼ "))
    else:
        lines.append(("fg:ansibrightblack", "  "))
    lines.append(
        (
            "fg:ansibrightblack",
            f"Page {page + 1}/{max(total_pages, 1)}   "
            f"(↑↓ to move, ←→ / PgUp PgDn to page)\n",
        )
    )

    for i in range(start, end):
        is_sel = i == selected_idx
        name = _sanitize(models[i])
        if is_sel and focused:
            lines.append(("fg:ansigreen bold", "  ▶ "))
            lines.append(("fg:ansigreen bold", name))
        elif is_sel:
            lines.append(("fg:ansiyellow", "  · "))
            lines.append(("fg:ansiyellow", name))
        else:
            lines.append(("", "    "))
            lines.append(("", name))
        lines.append(("", "\n"))

    return lines


# ---------------------------------------------------------------------------
# In-TUI form for add/edit
# ---------------------------------------------------------------------------


class _FormResult:
    """Mutable struct so closures in key bindings can mutate."""

    def __init__(self) -> None:
        self.saved: bool = False
        self.cancelled: bool = False
        self.name: str = ""
        self.model: str = ""
        self.prompt: str = ""


async def _run_judge_form(
    *,
    title: str,
    initial_name: str = "",
    initial_model: str = "",
    initial_prompt: str = DEFAULT_JUDGE_PROMPT,
) -> _FormResult:
    """Render the add/edit form with three tabbable sections:

        1. Name   — single-line TextArea
        2. Model  — inline paginated list (focusable Window)
        3. Prompt — multiline TextArea

    Tab / Shift+Tab cycles between sections. When Model is focused, the
    arrow keys move the selection; ←→ / PgUp PgDn page-jump. Whatever's
    highlighted IS the selected model — no separate "confirm" gesture.
    """
    from prompt_toolkit.filters import Condition

    result = _FormResult()
    status_line = [""]

    # ---- Model list state ----
    models = _load_available_models()
    # Find the index of the initial model, or default to 0.
    try:
        model_idx = [models.index(initial_model)] if initial_model in models else [0]
    except ValueError:
        model_idx = [0]
    model_page = [get_page_for_index(model_idx[0], MODEL_PAGE_SIZE) if models else 0]

    def current_model() -> str:
        if not models:
            return ""
        return models[max(0, min(model_idx[0], len(models) - 1))]

    # ---- Widgets ----
    name_area = TextArea(
        text=initial_name,
        multiline=False,
        wrap_lines=False,
        focusable=True,
        height=1,
    )
    prompt_area = TextArea(
        text=initial_prompt,
        multiline=True,
        wrap_lines=True,
        focusable=True,
        scrollbar=True,
        height=Dimension(min=6, weight=55),
    )

    model_control = FormattedTextControl(
        text="",
        focusable=True,
        show_cursor=False,
    )
    model_window = Window(
        content=model_control,
        wrap_lines=False,
        # +2 rows for the header line and padding.
        height=Dimension(min=MODEL_PAGE_SIZE + 2, max=MODEL_PAGE_SIZE + 2),
    )

    status_control = FormattedTextControl(text="")
    help_control = FormattedTextControl(text="")
    status_window = Window(content=status_control, height=1)
    help_window = Window(content=help_control, height=1)

    # Layout: stacked frames, Name fixed-height, Model fixed-height,
    # Prompt takes the rest of the column.
    model_frame = Frame(model_window, title="Model")
    root = HSplit(
        [
            Frame(name_area, title="Name", height=3),
            model_frame,
            Frame(prompt_area, title="Prompt (multiline)"),
            status_window,
            help_window,
        ]
    )

    # ---- Renderers ----
    def is_model_focused() -> bool:
        try:
            return app.layout.current_window is model_window
        except Exception:
            return False

    def refresh() -> None:
        model_control.text = _render_model_list(
            models,
            model_idx[0],
            model_page[0],
            focused=is_model_focused(),
        )
        if status_line[0]:
            status_control.text = [("fg:ansired", status_line[0])]
        else:
            # Hint at the bottom of the form: show current model selection.
            current = current_model() or "(no models available)"
            status_control.text = [
                ("fg:ansibrightblack", "Selected model: "),
                ("fg:ansiyellow", _sanitize(current)),
            ]
        help_control.text = [
            ("fg:ansibrightblack", "  Tab "),
            ("", "next field    "),
            ("fg:ansigreen", "  ↑↓ "),
            ("", "select model    "),
            ("fg:ansigreen", "  Ctrl+S "),
            ("", "save    "),
            ("fg:ansibrightred", "  Esc/Ctrl+C "),
            ("", "cancel"),
        ]

    # ---- Keybindings ----
    kb = KeyBindings()

    # Cycle order: name → model → prompt → name ...
    _focus_cycle = [name_area, model_window, prompt_area]

    def _focus_index() -> int:
        try:
            cur = app.layout.current_window
        except Exception:
            return 0
        for i, item in enumerate(_focus_cycle):
            target = item.window if hasattr(item, "window") else item
            if cur is target:
                return i
        return 0

    def _focus(item) -> None:
        # TextArea.focus works on the TextArea; Window is focused directly.
        app.layout.focus(item)

    @kb.add("tab")
    def _(event):
        nxt = (_focus_index() + 1) % len(_focus_cycle)
        _focus(_focus_cycle[nxt])
        refresh()

    @kb.add("s-tab")
    def _(event):
        prev = (_focus_index() - 1) % len(_focus_cycle)
        _focus(_focus_cycle[prev])
        refresh()

    @kb.add("escape")
    @kb.add("c-c")
    def _(event):
        result.cancelled = True
        event.app.exit()

    @kb.add("c-s")
    def _(event):
        name = name_area.text.strip()
        prompt_text = prompt_area.text
        err = validate_name(name)
        if err:
            status_line[0] = err
            refresh()
            return
        chosen_model = current_model()
        if not chosen_model:
            status_line[0] = "No models available — cannot save."
            refresh()
            return
        if not prompt_text.strip():
            status_line[0] = "Prompt cannot be empty."
            refresh()
            return
        result.saved = True
        result.name = name
        result.model = chosen_model
        result.prompt = prompt_text
        event.app.exit()

    # ---- Model-list navigation (only fires when the model window is focused) ----
    model_focused = Condition(is_model_focused)

    @kb.add("up", filter=model_focused)
    def _(event):
        if not models:
            return
        if model_idx[0] > 0:
            model_idx[0] -= 1
            model_page[0] = ensure_visible_page(
                model_idx[0], model_page[0], len(models), MODEL_PAGE_SIZE
            )
            status_line[0] = ""
            refresh()

    @kb.add("down", filter=model_focused)
    def _(event):
        if not models:
            return
        if model_idx[0] < len(models) - 1:
            model_idx[0] += 1
            model_page[0] = ensure_visible_page(
                model_idx[0], model_page[0], len(models), MODEL_PAGE_SIZE
            )
            status_line[0] = ""
            refresh()

    def _page_jump(delta: int) -> None:
        if not models:
            return
        total = get_total_pages(len(models), MODEL_PAGE_SIZE)
        new_page = max(0, min(model_page[0] + delta, total - 1))
        if new_page == model_page[0]:
            return
        model_page[0] = new_page
        # Snap selection to the first item on the new page.
        model_idx[0] = new_page * MODEL_PAGE_SIZE
        status_line[0] = ""
        refresh()

    @kb.add("left", filter=model_focused)
    @kb.add("pageup", filter=model_focused)
    def _(event):
        _page_jump(-1)

    @kb.add("right", filter=model_focused)
    @kb.add("pagedown", filter=model_focused)
    def _(event):
        _page_jump(1)

    @kb.add("home", filter=model_focused)
    def _(event):
        if not models:
            return
        model_idx[0] = 0
        model_page[0] = 0
        status_line[0] = ""
        refresh()

    @kb.add("end", filter=model_focused)
    def _(event):
        if not models:
            return
        model_idx[0] = len(models) - 1
        model_page[0] = get_page_for_index(model_idx[0], MODEL_PAGE_SIZE)
        status_line[0] = ""
        refresh()

    # ---- App ----
    layout = Layout(root)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )
    layout.focus(name_area)

    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    refresh()
    await app.run_async()

    return result


# ---------------------------------------------------------------------------
# Panel rendering for the list view
# ---------------------------------------------------------------------------


def _render_menu(
    judges: list[JudgeConfig],
    page: int,
    selected_idx: int,
) -> list:
    lines = []
    total_pages = get_total_pages(len(judges), PAGE_SIZE)
    start, end = get_page_bounds(page, len(judges), PAGE_SIZE)

    lines.append(("bold", "Goal Judges"))
    lines.append(("fg:ansibrightblack", f" (Page {page + 1}/{max(total_pages, 1)})"))
    lines.append(("", "\n\n"))

    if not judges:
        lines.append(("fg:yellow", "  No judges configured."))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  Press "))
        lines.append(("fg:ansigreen bold", "N"))
        lines.append(("fg:ansibrightblack", " to add one."))
        lines.append(("", "\n\n"))
    else:
        for i in range(start, end):
            judge = judges[i]
            is_selected = i == selected_idx
            marker = "▶ " if is_selected else "  "
            row_style = "fg:ansigreen bold" if is_selected else ""
            enabled_glyph = "[on] " if judge.enabled else "[off]"
            enabled_style = "fg:ansigreen" if judge.enabled else "fg:ansibrightblack"

            lines.append((row_style or "fg:ansigreen", marker))
            lines.append((enabled_style, enabled_glyph + " "))
            lines.append((row_style, _sanitize(judge.name)))
            lines.append(("fg:ansibrightblack", "  "))
            lines.append(("fg:ansiyellow", _sanitize(judge.model)))
            lines.append(("", "\n"))

    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  ↑↓ "))
    lines.append(("", "Navigate\n"))
    lines.append(("fg:ansibrightblack", "  ←→ "))
    lines.append(("", "Page\n"))
    lines.append(("fg:ansigreen", "  N "))
    lines.append(("", "New judge\n"))
    lines.append(("fg:ansigreen", "  Enter "))
    lines.append(("", "Edit (or E)\n"))
    lines.append(("fg:ansibrightblack", "  T "))
    lines.append(("", "Toggle enabled\n"))
    lines.append(("fg:ansibrightred", "  D "))
    lines.append(("", "Delete\n"))
    lines.append(("fg:ansibrightblack", "  Esc "))
    lines.append(("", "Close (or Ctrl+C)"))
    return lines


def _render_preview(judge: Optional[JudgeConfig]) -> list:
    lines = []
    lines.append(("dim cyan", " JUDGE DETAILS"))
    lines.append(("", "\n\n"))

    if judge is None:
        lines.append(("fg:yellow", "  No judge selected."))
        lines.append(("", "\n"))
        return lines

    lines.append(("bold", "Name: "))
    lines.append(("", _sanitize(judge.name)))
    lines.append(("", "\n\n"))

    lines.append(("bold", "Model: "))
    lines.append(("fg:ansiyellow", _sanitize(judge.model)))
    lines.append(("", "\n\n"))

    lines.append(("bold", "Enabled: "))
    if judge.enabled:
        lines.append(("fg:ansigreen", "yes"))
    else:
        lines.append(("fg:ansibrightblack", "no"))
    lines.append(("", "\n\n"))

    lines.append(("bold", "Prompt:"))
    lines.append(("", "\n"))
    for wrapped in _wrap(judge.prompt or "", width=58):
        lines.append(("fg:ansibrightblack", wrapped or " "))
        lines.append(("", "\n"))

    return lines


# ---------------------------------------------------------------------------
# Add / edit handlers (invoked between TUI sessions)
# ---------------------------------------------------------------------------


async def _add_judge_flow() -> Optional[str]:
    form = await _run_judge_form(title="New Judge")
    if not form.saved:
        emit_info("Cancelled.")
        return None
    try:
        add_judge(
            JudgeConfig(
                name=form.name,
                model=form.model,
                prompt=form.prompt,
                enabled=True,
            )
        )
    except ValueError as exc:
        emit_warning(str(exc))
        return None
    emit_success(f"Added judge {form.name!r} → {form.model}")
    return form.name


async def _edit_judge_flow(current: JudgeConfig) -> Optional[str]:
    form = await _run_judge_form(
        title=f"Edit Judge — {current.name}",
        initial_name=current.name,
        initial_model=current.model,
        initial_prompt=current.prompt,
    )
    if not form.saved:
        emit_info("Cancelled.")
        return current.name

    try:
        update_judge(
            current.name,
            new_name=form.name if form.name != current.name else None,
            model=form.model if form.model != current.model else None,
            prompt=form.prompt if form.prompt != current.prompt else None,
        )
    except ValueError as exc:
        emit_warning(str(exc))
        return current.name
    emit_success(f"Updated judge {form.name!r}")
    return form.name


# ---------------------------------------------------------------------------
# Main TUI loop
# ---------------------------------------------------------------------------


async def interactive_judges_menu() -> None:
    """Open the goal-judges TUI. Returns when the user closes the menu."""
    registry = load_judges()
    judges = list(registry.judges)

    selected_idx = [0]
    current_page = [0]
    pending_action: list[Optional[str]] = [None]
    pending_target: list[Optional[str]] = [None]

    def refresh(select_name: Optional[str] = None) -> None:
        nonlocal judges
        registry = load_judges()
        judges = list(registry.judges)
        if not judges:
            selected_idx[0] = 0
            current_page[0] = 0
            return
        if select_name:
            for i, j in enumerate(judges):
                if j.name == select_name:
                    selected_idx[0] = i
                    break
            else:
                selected_idx[0] = min(selected_idx[0], len(judges) - 1)
        else:
            selected_idx[0] = min(selected_idx[0], len(judges) - 1)
        current_page[0] = get_page_for_index(selected_idx[0], PAGE_SIZE)

    def current_judge() -> Optional[JudgeConfig]:
        if 0 <= selected_idx[0] < len(judges):
            return judges[selected_idx[0]]
        return None

    menu_control = FormattedTextControl(text="")
    preview_control = FormattedTextControl(text="")

    def update_display() -> None:
        menu_control.text = _render_menu(judges, current_page[0], selected_idx[0])
        preview_control.text = _render_preview(current_judge())

    menu_window = Window(
        content=menu_control, wrap_lines=False, width=Dimension(weight=40)
    )
    preview_window = Window(
        content=preview_control, wrap_lines=True, width=Dimension(weight=60)
    )
    menu_frame = Frame(menu_window, width=Dimension(weight=40), title="Judges")
    preview_frame = Frame(preview_window, width=Dimension(weight=60), title="Preview")
    root = VSplit([menu_frame, preview_frame])

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            current_page[0] = ensure_visible_page(
                selected_idx[0], current_page[0], len(judges), PAGE_SIZE
            )
            update_display()

    @kb.add("down")
    def _(event):
        if selected_idx[0] < len(judges) - 1:
            selected_idx[0] += 1
            current_page[0] = ensure_visible_page(
                selected_idx[0], current_page[0], len(judges), PAGE_SIZE
            )
            update_display()

    @kb.add("left")
    def _(event):
        if current_page[0] > 0:
            current_page[0] -= 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("right")
    def _(event):
        total = get_total_pages(len(judges), PAGE_SIZE)
        if current_page[0] < total - 1:
            current_page[0] += 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("n")
    def _(event):
        pending_action[0] = "add"
        event.app.exit()

    # Enter edits the highlighted judge — it's the obvious "act on this row"
    # gesture in a list view. 'E' is kept as an alias for muscle memory.
    @kb.add("enter")
    @kb.add("e")
    def _(event):
        judge = current_judge()
        if judge:
            pending_action[0] = "edit"
            pending_target[0] = judge.name
            event.app.exit()

    @kb.add("t")
    def _(event):
        judge = current_judge()
        if judge:
            pending_action[0] = "toggle"
            pending_target[0] = judge.name
            event.app.exit()

    @kb.add("d")
    def _(event):
        judge = current_judge()
        if judge:
            pending_action[0] = "delete"
            pending_target[0] = judge.name
            event.app.exit()

    # Esc and Ctrl+C both close the menu. Esc is the natural "I'm done"
    # gesture; Ctrl+C is the universal escape hatch. eager=False (the
    # default) is fine here because the list view has no Esc-chord, so
    # there's nothing to wait for — prompt_toolkit fires the handler as
    # soon as the chord timeout expires (immediate in practice).
    @kb.add("escape")
    @kb.add("c-c")
    def _(event):
        pending_action[0] = "close"
        event.app.exit()

    layout = Layout(root)
    app = Application(
        layout=layout, key_bindings=kb, full_screen=False, mouse_support=False
    )

    set_awaiting_user_input(True)
    sys.stdout.write("\033[?1049h")
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    await asyncio.sleep(0.05)

    try:
        while True:
            pending_action[0] = None
            pending_target[0] = None
            update_display()
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            await app.run_async()

            action = pending_action[0]
            target = pending_target[0]

            if action in (None, "close", "cancel"):
                break

            if action == "add":
                new_name = await _add_judge_flow()
                refresh(select_name=new_name)
                continue

            if not target:
                continue

            if action == "edit":
                judge = next((j for j in judges if j.name == target), None)
                if judge:
                    new_name = await _edit_judge_flow(judge)
                    refresh(select_name=new_name or target)
                continue

            if action == "toggle":
                new_state = toggle_judge(target)
                if new_state is None:
                    emit_warning(f"No judge named {target!r}.")
                else:
                    emit_info(
                        f"{target!r} is now {'enabled' if new_state else 'disabled'}"
                    )
                refresh(select_name=target)
                continue

            if action == "delete":
                if delete_judge(target):
                    emit_success(f"Deleted judge {target!r}")
                else:
                    emit_warning(f"No judge named {target!r}.")
                refresh()
                continue

    finally:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        set_awaiting_user_input(False)

    emit_info("✓ Exited judges menu")
