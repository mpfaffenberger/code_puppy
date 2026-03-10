"""Interactive TUI wizard for creating / editing a model profile.

Split-panel interface — mirrors the style of agent_menu.py.  The right panel
switches between three live views inside the running Application (no exit /
re-enter, so the terminal layout is never disrupted):

  Preview      live view of what will be saved       (browse mode)
  Model pick   scrollable model list                 (Enter on an agent)
  Import pick  scrollable list of .json files        (I key)

Key bindings — browse mode
───────────────────────────
  ↑ / ↓    navigate agent list
  Enter     inline model picker for highlighted agent
  N / D     edit name / description  (brief PromptSession)
  C         clear — start a brand-new blank profile
  U         dUplicate — keep models, rename via prompt
  E         export profile JSON to current working directory
  I         import a profile JSON from current working directory
  R         reset agent models to session defaults
  S         save and exit
  Ctrl+C    cancel without saving

Key bindings — model-pick / import-pick modes
──────────────────────────────────────────────
  ↑ / ↓    scroll list
  Enter     confirm selection
  Escape    back to browse
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line._profile_tui_panels import (
    VISIBLE,
    cwd_json_files,
    load_models,
    render_import_picker,
    render_left,
    render_model_picker,
    render_preview,
    valid_name,
)
from code_puppy.messaging import emit_error, emit_success, emit_warning
from code_puppy.task_models import (
    TASK_CONFIGS,
    Task,
    get_model_for,
    list_profiles,
    profile_exists,
    save_profile_from_models,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

_TASKS: List[Task] = list(TASK_CONFIGS.keys())
_BROWSE = "browse"
_PICK = "pick"
_IMPORT = "import"


# ── text-input helper (briefly exits alternate screen) ────────────────────────


async def _prompt_text(label: str, current: str = "") -> Optional[str]:
    from prompt_toolkit import PromptSession

    sys.stdout.write("\033[?1049l")
    sys.stdout.flush()
    try:
        return (await PromptSession().prompt_async(label, default=current)).strip()
    except (KeyboardInterrupt, EOFError):
        return None
    finally:
        sys.stdout.write("\033[?1049h\033[2J\033[H")
        sys.stdout.flush()


# ── main entry point ──────────────────────────────────────────────────────────


async def interactive_new_profile_tui(initial_name: str = "") -> Optional[str]:
    """
    /profile TUI — create, edit, duplicate, export or import model profiles.

    Args:
        initial_name: Pre-filled name; opens in "Edit" mode if the profile exists.

    Returns:
        Saved profile name, or ``None`` if cancelled.
    """
    edit_mode = bool(initial_name) and profile_exists(initial_name)

    # ── state ─────────────────────────────────────────────────────────────────
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
    agent_idx = [0]
    error_msg = [""]

    mode = [_BROWSE]
    model_names: List[List[str]] = [[]]
    pick_idx = [0]
    pick_scroll = [0]
    pick_task: List[Optional[Task]] = [None]
    imp_files: List[List[Path]] = [[]]
    imp_idx = [0]
    imp_scroll = [0]

    # ── widgets ───────────────────────────────────────────────────────────────
    left_ctrl = FormattedTextControl(text="")
    right_ctrl = FormattedTextControl(text="")

    def refresh():
        left_ctrl.text = render_left(
            name[0],
            description[0],
            agent_models[0],
            agent_idx[0],
            error_msg[0],
            mode[0],
            edit_mode,
        )
        if mode[0] == _PICK and pick_task[0] is not None:
            right_ctrl.text = render_model_picker(
                pick_task[0],
                model_names[0],
                pick_idx[0],
                pick_scroll[0],
                agent_models[0].get(pick_task[0], ""),
            )
        elif mode[0] == _IMPORT:
            right_ctrl.text = render_import_picker(
                imp_files[0], imp_idx[0], imp_scroll[0]
            )
        else:
            right_ctrl.text = render_preview(name[0], description[0], agent_models[0])

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
                    title="Preview / Picker",
                    width=Dimension(weight=58),
                ),
            ]
        )
    )

    # ── key bindings ──────────────────────────────────────────────────────────
    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        if mode[0] == _BROWSE:
            if agent_idx[0] > 0:
                agent_idx[0] -= 1
                error_msg[0] = ""
                refresh()
        elif mode[0] == _PICK:
            if pick_idx[0] > 0:
                pick_idx[0] -= 1
                if pick_idx[0] < pick_scroll[0]:
                    pick_scroll[0] = pick_idx[0]
                refresh()
        else:
            if imp_idx[0] > 0:
                imp_idx[0] -= 1
                if imp_idx[0] < imp_scroll[0]:
                    imp_scroll[0] = imp_idx[0]
                refresh()

    @kb.add("down")
    def _down(event):
        if mode[0] == _BROWSE:
            if agent_idx[0] < len(_TASKS) - 1:
                agent_idx[0] += 1
                error_msg[0] = ""
                refresh()
        elif mode[0] == _PICK:
            if pick_idx[0] < len(model_names[0]) - 1:
                pick_idx[0] += 1
                if pick_idx[0] >= pick_scroll[0] + VISIBLE:
                    pick_scroll[0] = pick_idx[0] - VISIBLE + 1
                refresh()
        else:
            if imp_idx[0] < len(imp_files[0]) - 1:
                imp_idx[0] += 1
                if imp_idx[0] >= imp_scroll[0] + VISIBLE:
                    imp_scroll[0] = imp_idx[0] - VISIBLE + 1
                refresh()

    @kb.add("enter")
    def _enter(event):
        if mode[0] == _BROWSE:
            task = _TASKS[agent_idx[0]]
            names = load_models()
            if not names:
                error_msg[0] = "No models available"
                refresh()
                return
            cur = agent_models[0].get(task, "")
            start = names.index(cur) if cur in names else 0
            pick_task[0] = task
            model_names[0] = names
            pick_idx[0] = start
            pick_scroll[0] = max(0, start - VISIBLE // 2)
            mode[0] = _PICK
            error_msg[0] = ""
            refresh()
        elif mode[0] == _PICK:
            if model_names[0] and pick_task[0] is not None:
                agent_models[0][pick_task[0]] = model_names[0][pick_idx[0]]
            mode[0] = _BROWSE
            pick_task[0] = None
            refresh()
        else:  # _IMPORT
            files = imp_files[0]
            if not files:
                mode[0] = _BROWSE
                refresh()
                return
            path = files[imp_idx[0]]
            try:
                data = json.loads(path.read_text())
                name[0] = data.get("name", path.stem)
                description[0] = data.get("description", "")
                for task in _TASKS:
                    m = data.get("models", {}).get(task.name.lower())
                    if m:
                        agent_models[0][task] = m
                error_msg[0] = f"Imported {path.name}"
            except Exception as exc:
                error_msg[0] = f"Import failed: {exc}"
            mode[0] = _BROWSE
            refresh()

    @kb.add("escape")
    def _esc(event):
        if mode[0] != _BROWSE:
            mode[0] = _BROWSE
            pick_task[0] = None
            refresh()

    @kb.add("n")
    def _kn(event):
        if mode[0] == _BROWSE:
            event.app._ptu = "edit_name"
            event.app.exit()

    @kb.add("d")
    def _kd(event):
        if mode[0] == _BROWSE:
            event.app._ptu = "edit_desc"
            event.app.exit()

    @kb.add("c")
    def _kc(event):
        if mode[0] != _BROWSE:
            return
        name[0] = ""
        description[0] = ""
        agent_models[0] = {t: get_model_for(t) for t in _TASKS}
        error_msg[0] = "Cleared — enter a name with N to start a new profile"
        refresh()

    @kb.add("u")
    def _ku(event):
        if mode[0] == _BROWSE:
            event.app._ptu = "duplicate"
            event.app.exit()

    @kb.add("e")
    def _ke(event):
        if mode[0] != _BROWSE:
            return
        if not name[0]:
            error_msg[0] = "Enter a name (N) before exporting"
            refresh()
            return
        if not valid_name(name[0]):
            error_msg[0] = "Invalid name — alphanumeric only"
            refresh()
            return
        event.app._ptu = "export"
        event.app.exit()

    @kb.add("i")
    def _ki(event):
        if mode[0] != _BROWSE:
            return
        imp_files[0] = cwd_json_files()
        imp_idx[0] = 0
        imp_scroll[0] = 0
        mode[0] = _IMPORT
        error_msg[0] = ""
        refresh()

    @kb.add("r")
    def _kr(event):
        if mode[0] != _BROWSE:
            return
        agent_models[0] = {t: get_model_for(t) for t in _TASKS}
        error_msg[0] = "Models reset to session defaults"
        refresh()

    @kb.add("s")
    def _ks(event):
        if mode[0] != _BROWSE:
            return
        if not name[0]:
            error_msg[0] = "Name required — press N"
            refresh()
            return
        if not valid_name(name[0]):
            error_msg[0] = "Alphanumeric only (- _ OK)"
            refresh()
            return
        event.app._ptu = "save"
        event.app.exit()

    @kb.add("c-c")
    def _kcc(event):
        event.app._ptu = "cancel"
        event.app.exit()

    # ── run ───────────────────────────────────────────────────────────────────
    app = Application(
        layout=layout, key_bindings=kb, full_screen=False, mouse_support=False
    )
    app._ptu = None  # type: ignore[attr-defined]

    set_awaiting_user_input(True)
    sys.stdout.write("\033[?1049h\033[2J\033[H")
    sys.stdout.flush()
    saved_name: Optional[str] = None

    try:
        while True:
            app._ptu = None  # type: ignore[attr-defined]
            refresh()
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            await app.run_async()
            action = getattr(app, "_ptu", None)

            if action == "cancel":
                emit_error("Cancelled.")
                return None
            if action == "save":
                break

            if action == "edit_name":
                v = await _prompt_text("  Profile name: ", name[0])
                if v is not None:
                    name[0] = v
                error_msg[0] = ""
            elif action == "edit_desc":
                v = await _prompt_text("  Description:  ", description[0])
                if v is not None:
                    description[0] = v
                error_msg[0] = ""
            elif action == "duplicate":
                v = await _prompt_text("  Duplicate as: ", "")
                if v:
                    name[0] = v
                    error_msg[0] = f"Duplicated — press S to save as '{v}'"
                else:
                    error_msg[0] = ""
            elif action == "export":
                dest = Path(os.getcwd()) / f"{name[0]}.json"
                try:
                    dest.write_text(
                        json.dumps(
                            {
                                "name": name[0],
                                "description": description[0],
                                "models": {
                                    t.name.lower(): m
                                    for t, m in agent_models[0].items()
                                },
                            },
                            indent=2,
                        )
                    )
                    emit_success(f"✅ Exported to {dest}")
                    error_msg[0] = f"Exported → {dest.name}"
                except Exception as exc:
                    emit_warning(f"Export failed: {exc}")
                    error_msg[0] = f"Export failed: {exc}"

    finally:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        set_awaiting_user_input(False)

    if save_profile_from_models(name[0], description[0], agent_models[0]):
        emit_success(f"✅ Profile '{name[0]}' saved!")
        saved_name = name[0]
    else:
        emit_error("Failed to save profile.")
    return saved_name
