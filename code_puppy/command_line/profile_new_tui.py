"""Interactive TUI wizard for creating a new model profile.

Split-panel interface — mirrors the style of agent_menu.py:

  Left  (Configure):  profile name · description · per-agent model selector
  Right (Preview):    live view of exactly what will be written to disk

Key bindings
─────────────
  ↑ / ↓     Navigate the agent list
  Enter      Open model picker for the highlighted agent
  N          Edit the profile name (mini prompt appears below the TUI)
  D          Edit the profile description
  S          Save and exit
  R          Reset all agent models to current session defaults
  Ctrl+C     Cancel without saving
"""

import asyncio
import sys
from typing import Dict, List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.messaging import emit_error, emit_success, emit_warning
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
from code_puppy.tools.common import arrow_select_async

# All tasks in display order
_TASKS: List[Task] = list(TASK_CONFIGS.keys())

_PLACEHOLDER_NAME = "<press N to enter a name>"
_PLACEHOLDER_DESC = "<press D to add a description>"

# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────


def _trunc(text: str, width: int) -> str:
    """Truncate *text* to *width* chars, appending '…' if cut."""
    return text if len(text) <= width else text[: width - 1] + "…"


def _is_valid_name(name: str) -> bool:
    """Return True if *name* is safe for use as a profile filename."""
    return bool(name) and all(c.isalnum() or c in "-_" for c in name)


def _render_left(
    name: str,
    description: str,
    agent_models: Dict[Task, str],
    selected_idx: int,
    error_msg: str,
    edit_mode: bool = False,
) -> List:
    """Build formatted-text lines for the left (Configure) panel."""
    lines: List = []

    if edit_mode and name:
        lines += [("bold cyan", f"  Edit Profile: {_trunc(name, 28)}"), ("", "\n\n")]
    else:
        lines += [("bold cyan", "  Create New Profile"), ("", "\n\n")]

    # ── name field ────────────────────────────────────────────────────────────
    lines += [("bold", "  Name  ")]
    if name:
        lines += [("fg:ansicyan", _trunc(name, 34))]
    else:
        lines += [("fg:ansibrightblack italic", _PLACEHOLDER_NAME)]
    lines += [("fg:ansibrightblack", "  N\n")]

    # ── description field ─────────────────────────────────────────────────────
    lines += [("bold", "  Desc  ")]
    if description:
        lines += [("fg:ansicyan", _trunc(description, 34))]
    else:
        lines += [("fg:ansibrightblack italic", _PLACEHOLDER_DESC)]
    lines += [("fg:ansibrightblack", "  D\n")]

    # ── validation error ──────────────────────────────────────────────────────
    lines += [("", "\n")]
    if error_msg:
        lines += [("fg:ansired", f"  {error_msg}"), ("", "\n")]
    lines += [("", "\n")]

    # ── agent list ────────────────────────────────────────────────────────────
    lines += [("bold", "  Agent Models\n")]
    lines += [("fg:ansibrightblack", "  ─────────────────────────────────\n")]

    for idx, task in enumerate(_TASKS):
        is_sel = idx == selected_idx
        model = _trunc(agent_models.get(task, "—"), 30)
        label = task.name.lower()
        if is_sel:
            lines += [
                ("fg:ansigreen bold", f"  ▶ {label:<12}"),
                ("fg:ansigreen", model),
                ("", "\n"),
            ]
        else:
            lines += [
                ("", f"    {label:<12}"),
                ("fg:ansicyan", model),
                ("", "\n"),
            ]

    # ── key hints ─────────────────────────────────────────────────────────────
    lines += [("", "\n")]
    for key, action in [
        ("↑↓", "navigate"),
        ("Enter", "change model"),
        ("N / D", "edit name / desc"),
        ("R", "reset models"),
    ]:
        lines += [("fg:ansibrightblack", f"  {key:<8}"), ("", f" {action}\n")]
    lines += [("fg:ansigreen bold", "  S       "), ("", " save\n")]
    lines += [("fg:ansired", "  Ctrl+C  "), ("", " cancel\n")]

    return lines


def _render_right(
    name: str,
    description: str,
    agent_models: Dict[Task, str],
) -> List:
    """Build formatted-text lines for the right (Preview) panel."""
    lines: List = []

    lines += [("dim cyan", "  PROFILE PREVIEW"), ("", "\n\n")]

    # ── name ──────────────────────────────────────────────────────────────────
    lines += [("bold", "  Name:  ")]
    if name:
        lines += [("fg:ansicyan bold", name)]
    else:
        lines += [("fg:ansired", "<name required>")]
    lines += [("", "\n")]

    # ── description ───────────────────────────────────────────────────────────
    if description:
        lines += [
            ("bold", "  Desc:  "),
            ("fg:ansibrightblack", _trunc(description, 48)),
            ("", "\n"),
        ]

    lines += [("", "\n"), ("bold", "  Models:\n")]
    lines += [("fg:ansibrightblack", "  ─────────────────────────────────────────\n")]

    for task in _TASKS:
        model = agent_models.get(task, "—")
        lines += [
            ("", f"  {task.name.lower():<12}"),
            ("fg:ansicyan", _trunc(model, 38)),
            ("", "\n"),
        ]

    lines += [("", "\n")]

    # ── active profile note ───────────────────────────────────────────────────
    active = get_active_profile()
    if active:
        lines += [
            ("fg:ansibrightblack", f"  Based on active profile: {active}\n"),
            ("", "\n"),
        ]

    # ── save-readiness indicator ──────────────────────────────────────────────
    if name and _is_valid_name(name):
        lines += [("fg:ansigreen bold", "  ✓ Ready — press S to save")]
    elif name:
        lines += [
            ("fg:ansired", "  ✗ Name must be alphanumeric (dashes/underscores OK)")
        ]
    else:
        lines += [("fg:ansiyellow", "  Enter a profile name (N) to save")]

    lines += [("", "\n")]
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Sub-dialog helpers (text input / model picker)
# ─────────────────────────────────────────────────────────────────────────────


async def _prompt_text(label: str, current: str = "") -> Optional[str]:
    """
    Exit alternate screen, prompt for a text value, re-enter alternate screen.

    Returns the stripped text, or None if the user pressed Ctrl+C / EOFError.
    """
    from prompt_toolkit import PromptSession

    sys.stdout.write("\033[?1049l")
    sys.stdout.flush()
    try:
        session = PromptSession()
        result = await session.prompt_async(label, default=current)
        return result.strip()
    except (KeyboardInterrupt, EOFError):
        return None
    finally:
        sys.stdout.write("\033[?1049h")
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


async def _pick_model(task: Task, current_model: str) -> Optional[str]:
    """Show the arrow-key model picker for *task*."""
    from code_puppy.command_line.model_picker_completion import load_model_names

    try:
        model_names = load_model_names() or []
    except Exception as exc:
        emit_warning(f"Could not load model list: {exc}")
        return None

    if not model_names:
        emit_warning("No models available.")
        return None

    choices = []
    for m in model_names:
        marker = "✓ " if m == current_model else "  "
        suffix = "  ← current" if m == current_model else ""
        choices.append(f"{marker}{m}{suffix}")

    try:
        choice = await arrow_select_async(
            f"Select model for '{task.name.lower()}' agent",
            choices,
        )
    except KeyboardInterrupt:
        return None

    # Strip decoration
    cleaned = choice.strip().lstrip("✓").strip()
    if "← current" in cleaned:
        cleaned = cleaned[: cleaned.index("← current")].strip()
    return cleaned or None


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────


async def interactive_new_profile_tui(initial_name: str = "") -> Optional[str]:
    """
    Show the /profile TUI — both for creating new profiles and editing existing ones.

    Pre-populates all agent models with the current session's effective values.
    When *initial_name* matches an existing profile the wizard enters edit mode:
    the title changes and the saved description is restored.

    Args:
        initial_name: Optional pre-filled profile name.  When it matches an
                      existing profile the TUI shows "Edit Profile" instead of
                      "Create New Profile".

    Returns:
        The saved profile name on success, or ``None`` if the user cancelled.
    """

    # ── detect edit vs create ─────────────────────────────────────────────────
    edit_mode = bool(initial_name) and profile_exists(initial_name)

    # ── mutable state ─────────────────────────────────────────────────────────
    name = [initial_name]

    # Restore description from existing profile file when editing
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

    agent_models = [{task: get_model_for(task) for task in _TASKS}]
    selected_idx = [0]
    pending_action: List[Optional[str]] = [None]
    error_msg = [""]

    # ── prompt-toolkit widgets ────────────────────────────────────────────────
    left_ctrl = FormattedTextControl(text="")
    right_ctrl = FormattedTextControl(text="")

    def refresh():
        left_ctrl.text = _render_left(
            name[0],
            description[0],
            agent_models[0],
            selected_idx[0],
            error_msg[0],
            edit_mode=edit_mode,
        )
        right_ctrl.text = _render_right(name[0], description[0], agent_models[0])

    layout = Layout(
        VSplit(
            [
                Frame(
                    Window(
                        content=left_ctrl, wrap_lines=False, width=Dimension(weight=45)
                    ),
                    title="Configure",
                    width=Dimension(weight=45),
                ),
                Frame(
                    Window(
                        content=right_ctrl, wrap_lines=False, width=Dimension(weight=55)
                    ),
                    title="Preview",
                    width=Dimension(weight=55),
                ),
            ]
        )
    )

    # ── key bindings ──────────────────────────────────────────────────────────
    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            error_msg[0] = ""
            refresh()

    @kb.add("down")
    def _down(event):
        if selected_idx[0] < len(_TASKS) - 1:
            selected_idx[0] += 1
            error_msg[0] = ""
            refresh()

    @kb.add("n")
    def _edit_name(event):
        pending_action[0] = "edit_name"
        event.app.exit()

    @kb.add("d")
    def _edit_desc(event):
        pending_action[0] = "edit_desc"
        event.app.exit()

    @kb.add("enter")
    def _pick(event):
        pending_action[0] = "pick_model"
        event.app.exit()

    @kb.add("r")
    def _reset(event):
        agent_models[0] = {task: get_model_for(task) for task in _TASKS}
        error_msg[0] = "Models reset to session defaults"
        refresh()

    @kb.add("s")
    def _save(event):
        if not name[0]:
            error_msg[0] = "Name required — press N to enter one"
            refresh()
            return
        if not _is_valid_name(name[0]):
            error_msg[0] = "Alphanumeric only (dashes/underscores OK)"
            refresh()
            return
        pending_action[0] = "save"
        event.app.exit()

    @kb.add("c-c")
    def _cancel(event):
        pending_action[0] = "cancel"
        event.app.exit()

    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )

    # ── main loop ─────────────────────────────────────────────────────────────
    set_awaiting_user_input(True)
    sys.stdout.write("\033[?1049h")  # enter alternate screen
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    await asyncio.sleep(0.05)

    try:
        while True:
            pending_action[0] = None
            refresh()
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            await app.run_async()

            action = pending_action[0]

            if action == "cancel":
                emit_error("Profile creation cancelled.")
                return None

            if action == "save":
                break  # exit loop → write to disk below

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

            elif action == "pick_model":
                task = _TASKS[selected_idx[0]]
                chosen = await _pick_model(task, agent_models[0].get(task, ""))
                if chosen:
                    agent_models[0][task] = chosen
                error_msg[0] = ""

    finally:
        sys.stdout.write("\033[?1049l")  # leave alternate screen
        sys.stdout.flush()
        set_awaiting_user_input(False)

    # ── persist ───────────────────────────────────────────────────────────────
    saved_name = name[0]
    if save_profile_from_models(saved_name, description[0], agent_models[0]):
        emit_success(f"✅ Profile '{saved_name}' saved!")
        return saved_name

    emit_error("Failed to save profile.")
    return None
