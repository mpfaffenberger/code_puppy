"""Interactive TUI wizard for creating / editing a model profile.

Split-panel interface — mirrors the style of agent_menu.py:

  Left  (Configure):  profile name · description · per-agent model selector
  Right (Preview):    live preview of what will be saved
                 ──► switches to an inline model picker on Enter

The model picker renders **inside the right panel** of the running
Application so no content is ever pushed to the terminal scroll buffer.

Key bindings — browse mode
───────────────────────────
  ↑ / ↓     Navigate the agent list
  Enter      Open inline model picker for highlighted agent
  N          Edit profile name  (temporary PromptSession below TUI)
  D          Edit profile description
  S          Save and exit
  R          Reset all agent models to session defaults
  Ctrl+C     Cancel without saving

Key bindings — model-pick mode (right panel becomes the picker)
───────────────────────────────────────────────────────────────
  ↑ / ↓     Navigate model list
  Enter      Confirm selection, return to browse mode
  Escape     Cancel, return to browse mode
"""

import sys
from typing import Dict, List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.messaging import emit_error, emit_success
from code_puppy.task_models import (
    TASK_CONFIGS,
    Task,
    get_active_profile,
    get_model_for,
    list_profiles,
    profile_exists,
    save_profile_from_models,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

# All tasks in display order
_TASKS: List[Task] = list(TASK_CONFIGS.keys())

_PLACEHOLDER_NAME = "<press N to enter a name>"
_PLACEHOLDER_DESC = "<press D to add a description>"

# How many model rows to show at once inside the right panel picker
_PICK_VISIBLE = 18

# Internal mode constants
_BROWSE = "browse"
_PICK = "pick"

# ─────────────────────────────────────────────────────────────────────────────
# Tiny helpers
# ─────────────────────────────────────────────────────────────────────────────


def _trunc(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _is_valid_name(name: str) -> bool:
    return bool(name) and all(c.isalnum() or c in "-_" for c in name)


def _load_model_names() -> List[str]:
    try:
        from code_puppy.command_line.model_picker_completion import load_model_names

        return load_model_names() or []
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Panel renderers
# ─────────────────────────────────────────────────────────────────────────────


def _render_left(
    name: str,
    description: str,
    agent_models: Dict[Task, str],
    agent_idx: int,
    error_msg: str,
    mode: str,
    edit_mode: bool,
) -> List:
    lines: List = []

    if edit_mode and name:
        lines += [("bold cyan", f"  Edit Profile: {_trunc(name, 26)}"), ("", "\n\n")]
    else:
        lines += [("bold cyan", "  Create New Profile"), ("", "\n\n")]

    # name
    lines += [("bold", "  Name  ")]
    lines += [
        ("fg:ansicyan", _trunc(name, 32))
        if name
        else ("fg:ansibrightblack italic", _PLACEHOLDER_NAME)
    ]
    lines += [("fg:ansibrightblack", "  N\n")]

    # description
    lines += [("bold", "  Desc  ")]
    lines += [
        ("fg:ansicyan", _trunc(description, 32))
        if description
        else ("fg:ansibrightblack italic", _PLACEHOLDER_DESC)
    ]
    lines += [("fg:ansibrightblack", "  D\n")]

    # error
    lines += [("", "\n")]
    if error_msg:
        lines += [("fg:ansired", f"  {error_msg}"), ("", "\n")]
    lines += [("", "\n")]

    # agent list
    lines += [("bold", "  Agent Models\n")]
    lines += [("fg:ansibrightblack", "  ─────────────────────────────────\n")]

    for idx, task in enumerate(_TASKS):
        is_sel = idx == agent_idx
        # Dim agents when in pick mode so focus is clearly on the right panel
        dim = mode == _PICK
        model = _trunc(agent_models.get(task, "—"), 28)
        label = task.name.lower()
        if is_sel and not dim:
            lines += [
                ("fg:ansigreen bold", f"  ▶ {label:<12}"),
                ("fg:ansigreen", model),
                ("", "\n"),
            ]
        elif is_sel and dim:
            lines += [
                ("fg:ansibrightblack bold", f"  ▶ {label:<12}"),
                ("fg:ansibrightblack", model),
                ("", "\n"),
            ]
        else:
            style = "fg:ansibrightblack" if dim else ""
            lines += [
                (style, f"    {label:<12}"),
                ("fg:ansibrightblack" if dim else "fg:ansicyan", model),
                ("", "\n"),
            ]

    # key hints — change depending on mode
    lines += [("", "\n")]
    if mode == _BROWSE:
        for key, action in [
            ("↑↓", "navigate"),
            ("Enter", "pick model"),
            ("N / D", "name / desc"),
            ("R", "reset models"),
        ]:
            lines += [("fg:ansibrightblack", f"  {key:<9}"), ("", f"{action}\n")]
        lines += [("fg:ansigreen bold", "  S         "), ("", "save\n")]
        lines += [("fg:ansired", "  Ctrl+C    "), ("", "cancel\n")]
    else:
        lines += [("fg:ansibrightblack", "  ↑↓       "), ("", "scroll models\n")]
        lines += [("fg:ansigreen bold", "  Enter    "), ("", "confirm\n")]
        lines += [("fg:ansiyellow", "  Esc      "), ("", "back\n")]

    return lines


def _render_right_preview(
    name: str,
    description: str,
    agent_models: Dict[Task, str],
) -> List:
    lines: List = []

    lines += [("dim cyan", "  PROFILE PREVIEW"), ("", "\n\n")]

    lines += [("bold", "  Name:  ")]
    if name:
        lines += [("fg:ansicyan bold", name)]
    else:
        lines += [("fg:ansired", "<name required>")]
    lines += [("", "\n")]

    if description:
        lines += [
            ("bold", "  Desc:  "),
            ("fg:ansibrightblack", _trunc(description, 46)),
            ("", "\n"),
        ]

    lines += [("", "\n"), ("bold", "  Models:\n")]
    lines += [("fg:ansibrightblack", "  ─────────────────────────────────────────\n")]

    for task in _TASKS:
        model = agent_models.get(task, "—")
        lines += [
            ("", f"  {task.name.lower():<12}"),
            ("fg:ansicyan", _trunc(model, 36)),
            ("", "\n"),
        ]

    lines += [("", "\n")]

    active = get_active_profile()
    if active:
        lines += [("fg:ansibrightblack", f"  Based on: {active}\n"), ("", "\n")]

    if name and _is_valid_name(name):
        lines += [("fg:ansigreen bold", "  ✓ Ready — press S to save")]
    elif name:
        lines += [("fg:ansired", "  ✗ Name must be alphanumeric (- _ OK)")]
    else:
        lines += [("fg:ansiyellow", "  Press N to enter a profile name")]

    lines += [("", "\n")]
    return lines


def _render_right_picker(
    task: Task,
    model_names: List[str],
    pick_idx: int,
    scroll: int,
    current_model: str,
) -> List:
    """Render the model-picker list inside the right panel."""
    lines: List = []

    label = task.name.lower()
    lines += [("bold cyan", f"  Select model for '{label}'\n")]
    lines += [("fg:ansibrightblack", "  ─────────────────────────────────────────\n\n")]

    total = len(model_names)
    visible_end = min(scroll + _PICK_VISIBLE, total)

    # scroll-up indicator
    if scroll > 0:
        lines += [("fg:ansibrightblack", f"  ↑  {scroll} more above\n")]
    else:
        lines += [("", "\n")]

    for i in range(scroll, visible_end):
        m = model_names[i]
        is_sel = i == pick_idx
        is_cur = m == current_model

        cur_mark = " ✓" if is_cur else "  "

        if is_sel:
            lines += [
                ("fg:ansigreen bold", f"  ▶{cur_mark} {_trunc(m, 40)}"),
                ("", "\n"),
            ]
        else:
            style = "fg:ansicyan" if is_cur else "fg:ansibrightblack"
            lines += [(style, f"   {cur_mark} {_trunc(m, 40)}"), ("", "\n")]

    # scroll-down indicator
    remaining = total - visible_end
    if remaining > 0:
        lines += [("fg:ansibrightblack", f"  ↓  {remaining} more below\n")]
    else:
        lines += [("", "\n")]

    lines += [("", "\n")]
    lines += [("fg:ansibrightblack", f"  {pick_idx + 1} / {total}")]
    lines += [("", "\n")]

    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Text-input helper  (only for name / description — exits alternate screen
# briefly so PromptSession can render, then restores it)
# ─────────────────────────────────────────────────────────────────────────────


async def _prompt_text(label: str, current: str = "") -> Optional[str]:
    from prompt_toolkit import PromptSession

    sys.stdout.write("\033[?1049l")
    sys.stdout.flush()
    try:
        result = await PromptSession().prompt_async(label, default=current)
        return result.strip()
    except (KeyboardInterrupt, EOFError):
        return None
    finally:
        sys.stdout.write("\033[?1049h")
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────


async def interactive_new_profile_tui(initial_name: str = "") -> Optional[str]:
    """
    Show the /profile TUI — creates new profiles or edits existing ones.

    Model picking happens **inside** the right panel of the running Application
    so the terminal layout is never disrupted.

    Args:
        initial_name: Optional pre-filled name.  When it matches an existing
                      profile the TUI opens in "Edit Profile" mode.

    Returns:
        Saved profile name, or ``None`` if the user cancelled.
    """
    # ── edit vs create ────────────────────────────────────────────────────────
    edit_mode = bool(initial_name) and profile_exists(initial_name)

    # ── initial state ─────────────────────────────────────────────────────────
    name = [initial_name]

    initial_desc = ""
    if edit_mode:
        try:
            for p in list_profiles():
                if p["name"] == initial_name:
                    initial_desc = p.get("description", "")
                    break
        except Exception:
            pass
    description = [initial_desc]

    agent_models: List[Dict[Task, str]] = [{t: get_model_for(t) for t in _TASKS}]
    agent_idx = [0]  # which task row is highlighted in browse mode
    error_msg = [""]

    # ── model-picker state ────────────────────────────────────────────────────
    mode = [_BROWSE]
    model_names: List[List[str]] = [[]]  # loaded lazily when picker opens
    pick_idx = [0]
    pick_scroll = [0]
    pick_task: List[Optional[Task]] = [None]

    # ── prompt-toolkit widgets ────────────────────────────────────────────────
    left_ctrl = FormattedTextControl(text="")
    right_ctrl = FormattedTextControl(text="")

    def refresh():
        left_ctrl.text = _render_left(
            name[0],
            description[0],
            agent_models[0],
            agent_idx[0],
            error_msg[0],
            mode[0],
            edit_mode,
        )
        if mode[0] == _PICK and pick_task[0] is not None:
            right_ctrl.text = _render_right_picker(
                pick_task[0],
                model_names[0],
                pick_idx[0],
                pick_scroll[0],
                agent_models[0].get(pick_task[0], ""),
            )
        else:
            right_ctrl.text = _render_right_preview(
                name[0], description[0], agent_models[0]
            )

    # ── layout ────────────────────────────────────────────────────────────────
    layout = Layout(
        VSplit(
            [
                Frame(
                    Window(
                        content=left_ctrl, wrap_lines=False, width=Dimension(weight=42)
                    ),
                    title="Configure",
                    width=Dimension(weight=42),
                ),
                Frame(
                    Window(
                        content=right_ctrl, wrap_lines=False, width=Dimension(weight=58)
                    ),
                    title="Preview / Model Picker",
                    width=Dimension(weight=58),
                ),
            ]
        )
    )

    # ── key bindings ──────────────────────────────────────────────────────────
    kb = KeyBindings()

    # ·· up / down — context-sensitive ························

    @kb.add("up")
    def _up(event):
        if mode[0] == _BROWSE:
            if agent_idx[0] > 0:
                agent_idx[0] -= 1
                error_msg[0] = ""
                refresh()
        else:
            if pick_idx[0] > 0:
                pick_idx[0] -= 1
                if pick_idx[0] < pick_scroll[0]:
                    pick_scroll[0] = pick_idx[0]
                refresh()

    @kb.add("down")
    def _down(event):
        if mode[0] == _BROWSE:
            if agent_idx[0] < len(_TASKS) - 1:
                agent_idx[0] += 1
                error_msg[0] = ""
                refresh()
        else:
            if pick_idx[0] < len(model_names[0]) - 1:
                pick_idx[0] += 1
                if pick_idx[0] >= pick_scroll[0] + _PICK_VISIBLE:
                    pick_scroll[0] = pick_idx[0] - _PICK_VISIBLE + 1
                refresh()

    # ·· enter — context-sensitive ····························

    @kb.add("enter")
    def _enter(event):
        if mode[0] == _BROWSE:
            task = _TASKS[agent_idx[0]]
            names = _load_model_names()
            if not names:
                error_msg[0] = "No models available"
                refresh()
                return
            current = agent_models[0].get(task, "")
            start = names.index(current) if current in names else 0
            pick_task[0] = task
            model_names[0] = names
            pick_idx[0] = start
            pick_scroll[0] = max(0, start - _PICK_VISIBLE // 2)
            mode[0] = _PICK
            error_msg[0] = ""
            refresh()
        else:
            if model_names[0] and pick_task[0] is not None:
                agent_models[0][pick_task[0]] = model_names[0][pick_idx[0]]
            mode[0] = _BROWSE
            pick_task[0] = None
            refresh()

    # ·· escape — only meaningful in pick mode ···············

    @kb.add("escape")
    def _escape(event):
        if mode[0] == _PICK:
            mode[0] = _BROWSE
            pick_task[0] = None
            refresh()

    # ·· browse-only actions ···································

    @kb.add("n")
    def _edit_name(event):
        if mode[0] != _BROWSE:
            return
        event.app._profile_tui_action = "edit_name"
        event.app.exit()

    @kb.add("d")
    def _edit_desc(event):
        if mode[0] != _BROWSE:
            return
        event.app._profile_tui_action = "edit_desc"
        event.app.exit()

    @kb.add("r")
    def _reset(event):
        if mode[0] != _BROWSE:
            return
        agent_models[0] = {t: get_model_for(t) for t in _TASKS}
        error_msg[0] = "Models reset to session defaults"
        refresh()

    @kb.add("s")
    def _save(event):
        if mode[0] != _BROWSE:
            return
        if not name[0]:
            error_msg[0] = "Name required — press N to enter one"
            refresh()
            return
        if not _is_valid_name(name[0]):
            error_msg[0] = "Alphanumeric only (dashes / underscores OK)"
            refresh()
            return
        event.app._profile_tui_action = "save"
        event.app.exit()

    @kb.add("c-c")
    def _cancel(event):
        event.app._profile_tui_action = "cancel"
        event.app.exit()

    # ── application ───────────────────────────────────────────────────────────
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )
    app._profile_tui_action = None  # type: ignore[attr-defined]

    # ── main loop ─────────────────────────────────────────────────────────────
    set_awaiting_user_input(True)
    sys.stdout.write("\033[?1049h")
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

    saved_name: Optional[str] = None

    try:
        while True:
            app._profile_tui_action = None  # type: ignore[attr-defined]
            refresh()
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            await app.run_async()

            action = getattr(app, "_profile_tui_action", None)

            if action == "cancel":
                emit_error("Profile creation cancelled.")
                return None

            if action == "save":
                break

            if action == "edit_name":
                new_val = await _prompt_text("  Profile name: ", name[0])
                if new_val is not None:
                    name[0] = new_val
                error_msg[0] = ""

            elif action == "edit_desc":
                new_val = await _prompt_text("  Description:  ", description[0])
                if new_val is not None:
                    description[0] = new_val
                error_msg[0] = ""

    finally:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        set_awaiting_user_input(False)

    # ── persist ───────────────────────────────────────────────────────────────
    if save_profile_from_models(name[0], description[0], agent_models[0]):
        emit_success(f"✅ Profile '{name[0]}' saved!")
        saved_name = name[0]
    else:
        emit_error("Failed to save profile.")

    return saved_name
