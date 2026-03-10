"""Panel renderers and helpers for profile_new_tui.

Separated into its own module to keep profile_new_tui.py under the 600-line cap.
"""

import os
from pathlib import Path
from typing import List

from code_puppy.task_models import TASK_CONFIGS, Task, get_active_profile

_TASKS: List[Task] = list(TASK_CONFIGS.keys())

_PLACEHOLDER_NAME = "<press N to enter a name>"
_PLACEHOLDER_DESC = "<press D to add a description>"

_BROWSE = "browse"
_PICK = "pick"
_IMPORT = "import"

VISIBLE = 16  # rows shown in any inline picker


# ── tiny helpers ──────────────────────────────────────────────────────────────


def trunc(t: str, w: int) -> str:
    return t if len(t) <= w else t[: w - 1] + "…"


def valid_name(n: str) -> bool:
    return bool(n) and all(c.isalnum() or c in "-_" for c in n)


def load_models() -> List[str]:
    try:
        from code_puppy.command_line.model_picker_completion import load_model_names

        return load_model_names() or []
    except Exception:
        return []


def cwd_json_files() -> List[Path]:
    return sorted(Path(os.getcwd()).glob("*.json"))


# ── left panel ────────────────────────────────────────────────────────────────


def render_left(name, description, agent_models, agent_idx, error_msg, mode, edit_mode):
    L = []
    title = (
        f"  Edit Profile: {trunc(name, 24)}"
        if (edit_mode and name)
        else "  Create New Profile"
    )
    L += [("bold cyan", title), ("", "\n\n")]

    L += [
        ("bold", "  Name  "),
        ("fg:ansicyan", trunc(name, 30))
        if name
        else ("fg:ansibrightblack italic", _PLACEHOLDER_NAME),
        ("fg:ansibrightblack", "  N\n"),
    ]
    L += [
        ("bold", "  Desc  "),
        ("fg:ansicyan", trunc(description, 30))
        if description
        else ("fg:ansibrightblack italic", _PLACEHOLDER_DESC),
        ("fg:ansibrightblack", "  D\n"),
    ]

    L += [("", "\n")]
    if error_msg:
        L += [("fg:ansired", f"  {error_msg}"), ("", "\n")]
    L += [("", "\n")]

    L += [
        ("bold", "  Agent Models\n"),
        ("fg:ansibrightblack", "  ─────────────────────────────\n"),
    ]
    dim = mode != _BROWSE
    for idx, task in enumerate(_TASKS):
        is_sel = idx == agent_idx
        model = trunc(agent_models.get(task, "—"), 26)
        label = task.name.lower()
        if is_sel and not dim:
            L += [
                ("fg:ansigreen bold", f"  ▶ {label:<11}"),
                ("fg:ansigreen", model),
                ("", "\n"),
            ]
        elif is_sel:
            L += [
                ("fg:ansibrightblack bold", f"  ▶ {label:<11}"),
                ("fg:ansibrightblack", model),
                ("", "\n"),
            ]
        else:
            s = "fg:ansibrightblack" if dim else ""
            L += [
                (s, f"    {label:<11}"),
                ("fg:ansibrightblack" if dim else "fg:ansicyan", model),
                ("", "\n"),
            ]

    L += [("", "\n")]
    if mode == _BROWSE:
        for k, a in [
            ("↑↓", "navigate"),
            ("Enter", "pick model"),
            ("N/D", "name/desc"),
            ("C", "new"),
            ("U", "duplicate"),
            ("E", "export"),
            ("I", "import"),
            ("R", "reset"),
        ]:
            L += [("fg:ansibrightblack", f"  {k:<8}"), ("", f"{a}\n")]
        L += [("fg:ansigreen bold", "  S       "), ("", "save\n")]
        L += [("fg:ansired", "  Ctrl+C  "), ("", "cancel\n")]
    else:
        L += [("fg:ansibrightblack", "  ↑↓      "), ("", "scroll\n")]
        L += [("fg:ansigreen bold", "  Enter   "), ("", "confirm\n")]
        L += [("fg:ansiyellow", "  Esc     "), ("", "back\n")]
    return L


# ── right panel: preview ──────────────────────────────────────────────────────


def render_preview(name, description, agent_models):
    L = [("dim cyan", "  PROFILE PREVIEW"), ("", "\n\n"), ("bold", "  Name:  ")]
    L += [("fg:ansicyan bold", name)] if name else [("fg:ansired", "<name required>")]
    L += [("", "\n")]
    if description:
        L += [
            ("bold", "  Desc:  "),
            ("fg:ansibrightblack", trunc(description, 44)),
            ("", "\n"),
        ]
    L += [
        ("", "\n"),
        ("bold", "  Models:\n"),
        ("fg:ansibrightblack", "  ─────────────────────────────────────────\n"),
    ]
    for task in _TASKS:
        L += [
            ("", f"  {task.name.lower():<12}"),
            ("fg:ansicyan", trunc(agent_models.get(task, "—"), 34)),
            ("", "\n"),
        ]
    L += [("", "\n")]
    active = get_active_profile()
    if active:
        L += [("fg:ansibrightblack", f"  Based on: {active}\n"), ("", "\n")]
    if name and valid_name(name):
        L += [("fg:ansigreen bold", "  ✓ Ready — press S to save")]
    elif name:
        L += [("fg:ansired", "  ✗ Name must be alphanumeric (- _ OK)")]
    else:
        L += [("fg:ansiyellow", "  Press N to enter a profile name")]
    L += [("", "\n")]
    return L


# ── right panel: model picker ─────────────────────────────────────────────────


def render_model_picker(task, model_names, pick_idx, scroll, current):
    L = [
        ("bold cyan", f"  Model for '{task.name.lower()}'\n"),
        ("fg:ansibrightblack", "  ──────────────────────────────────────────\n\n"),
    ]
    total = len(model_names)
    end = min(scroll + VISIBLE, total)
    L += (
        [("fg:ansibrightblack", f"  ↑  {scroll} more above\n")]
        if scroll > 0
        else [("", "\n")]
    )
    for i in range(scroll, end):
        m = model_names[i]
        mark = " ✓" if m == current else "  "
        if i == pick_idx:
            L += [("fg:ansigreen bold", f"  ▶{mark} {trunc(m, 38)}"), ("", "\n")]
        else:
            L += [
                (
                    "fg:ansicyan" if m == current else "fg:ansibrightblack",
                    f"   {mark} {trunc(m, 38)}",
                ),
                ("", "\n"),
            ]
    rem = total - end
    L += (
        [("fg:ansibrightblack", f"  ↓  {rem} more below\n")]
        if rem > 0
        else [("", "\n")]
    )
    L += [("", "\n"), ("fg:ansibrightblack", f"  {pick_idx + 1} / {total}\n")]
    return L


# ── right panel: import picker ────────────────────────────────────────────────


def render_import_picker(files, imp_idx, scroll):
    cwd = str(Path(os.getcwd()))
    L = [
        ("bold cyan", "  Import profile JSON\n"),
        ("fg:ansibrightblack", f"  from {trunc(cwd, 44)}\n"),
        ("fg:ansibrightblack", "  ──────────────────────────────────────────\n\n"),
    ]
    if not files:
        L += [
            ("fg:ansiyellow", "  No .json files found in current directory.\n"),
            ("", "\n"),
            ("fg:ansibrightblack", "  Export a profile first with E, or cd to\n"),
            ("fg:ansibrightblack", "  the folder containing your profile JSON.\n"),
        ]
        return L
    total = len(files)
    end = min(scroll + VISIBLE, total)
    L += (
        [("fg:ansibrightblack", f"  ↑  {scroll} more above\n")]
        if scroll > 0
        else [("", "\n")]
    )
    for i in range(scroll, end):
        fname = files[i].name
        if i == imp_idx:
            L += [("fg:ansigreen bold", f"  ▶ {trunc(fname, 44)}"), ("", "\n")]
        else:
            L += [("fg:ansibrightblack", f"    {trunc(fname, 44)}"), ("", "\n")]
    rem = total - end
    L += (
        [("fg:ansibrightblack", f"  ↓  {rem} more below\n")]
        if rem > 0
        else [("", "\n")]
    )
    L += [("", "\n"), ("fg:ansibrightblack", f"  {imp_idx + 1} / {total}\n")]
    return L
