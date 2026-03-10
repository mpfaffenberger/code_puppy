"""Panel renderers for the profile dual-panel TUI.

Three render functions:
  render_profile_list  — left panel, always visible
  render_agent_config  — right panel, browse/edit agent models
  render_model_picker  — right panel overlay when picking a model
"""

from typing import Dict, List, Optional

from code_puppy.task_models import TASK_CONFIGS, Task

_TASKS: List[Task] = list(TASK_CONFIGS.keys())

VISIBLE = 16  # max rows shown in the model picker at once


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


# ── left panel: profile list ──────────────────────────────────────────────────


def render_profile_list(
    profiles: list,
    prof_idx: int,
    active_name: Optional[str],
    focused: bool,
) -> list:
    """Scrollable list of saved profiles with active marker."""
    header_color = "bold cyan" if focused else "bold"
    L: list = [
        (header_color, "  Profiles\n"),
        ("fg:ansibrightblack", "  ─────────────────────────────\n\n"),
    ]

    if not profiles:
        L += [
            ("fg:ansiyellow", "  No saved profiles yet.\n\n"),
            ("fg:ansibrightblack", "  Press N to create the first one.\n"),
        ]
    else:
        for i, p in enumerate(profiles):
            pname = p.get("name", "?")
            desc = p.get("description", "")
            is_active = pname == active_name
            mark = "✓" if is_active else " "
            is_sel = i == prof_idx

            if is_sel:
                row_color = "fg:ansigreen bold" if focused else "fg:ansicyan bold"
                L += [(row_color, f"  ▶{mark} {trunc(pname, 22)}"), ("", "\n")]
                if desc:
                    L += [("fg:ansibrightblack", f"      {trunc(desc, 24)}\n")]
            elif is_active:
                L += [("fg:ansicyan", f"   {mark} {trunc(pname, 22)}"), ("", "\n")]
                if desc:
                    L += [("fg:ansibrightblack", f"      {trunc(desc, 24)}\n")]
            else:
                dim = "fg:ansibrightblack"
                L += [(dim, f"    {trunc(pname, 22)}"), ("", "\n")]

    L += [("", "\n")]

    # key hints adapt to focus
    if focused:
        L += [
            ("fg:ansibrightblack", "  ↑↓      browse\n"),
            ("fg:ansigreen bold", "  Enter   activate\n"),
            ("fg:ansibrightblack", "  N       new profile\n"),
            ("fg:ansibrightblack", "  Tab     configure →\n"),
            ("fg:ansired", "  Ctrl+C  exit\n"),
        ]
    else:
        L += [
            ("fg:ansibrightblack", "  Tab     ← switch here\n"),
        ]

    return L


# ── right panel: agent config ─────────────────────────────────────────────────


def render_agent_config(
    agent_models: Dict[Task, str],
    agent_idx: int,
    focused: bool,
    prof_name: str,
    status: str,
    active_name: Optional[str],
) -> list:
    """Agent-model assignment list with status line and key hints."""
    is_active = bool(prof_name) and prof_name == active_name

    header_color = "bold cyan" if focused else "bold"
    active_badge = (
        ("fg:ansigreen", "  ✓ active")
        if is_active
        else ("fg:ansibrightblack", "  (preview)")
    )
    display_name = trunc(prof_name, 32) if prof_name else "—"

    L: list = [
        (header_color, f"  {display_name}"),
        active_badge,
        ("", "\n"),
        ("fg:ansibrightblack", "  ─────────────────────────────────────────\n\n"),
    ]

    for idx, task in enumerate(_TASKS):
        label = task.name.lower()
        model = trunc(agent_models.get(task, "—"), 36)
        is_sel = idx == agent_idx

        if is_sel and focused:
            L += [
                ("fg:ansigreen bold", f"  ▶ {label:<12}"),
                ("fg:ansigreen", model),
                ("", "\n"),
            ]
        elif is_sel:
            L += [
                ("fg:ansicyan bold", f"  ▶ {label:<12}"),
                ("fg:ansicyan", model),
                ("", "\n"),
            ]
        else:
            row_color = "" if focused else "fg:ansibrightblack"
            model_color = "fg:ansicyan" if focused else "fg:ansibrightblack"
            L += [
                (row_color, f"    {label:<12}"),
                (model_color, model),
                ("", "\n"),
            ]

    L += [("", "\n")]

    if status:
        err = status.lower().startswith("fail") or status.lower().startswith("error")
        L += [("fg:ansired" if err else "fg:ansigreen", f"  {status}\n"), ("", "\n")]
    else:
        L += [("", "\n")]

    if focused:
        L += [
            ("fg:ansibrightblack", "  ↑↓       navigate agents\n"),
            ("fg:ansigreen bold", "  Enter    pick model\n"),
        ]
        if is_active:
            L += [("fg:ansigreen bold", "  S        save changes\n")]
        else:
            L += [("fg:ansiyellow", "  (activate profile to save)\n")]
        L += [
            ("fg:ansibrightblack", "  Tab      ← profiles\n"),
            ("fg:ansired", "  Ctrl+C   exit\n"),
        ]
    else:
        L += [("fg:ansibrightblack", "  Tab      switch here\n")]

    return L


# ── right panel: model picker overlay ─────────────────────────────────────────


def render_model_picker(
    task: Task,
    model_names: List[str],
    pick_idx: int,
    scroll: int,
    current: str,
) -> list:
    """Scrollable model list — replaces agent config while picking."""
    L: list = [
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
            color = "fg:ansicyan" if m == current else "fg:ansibrightblack"
            L += [(color, f"   {mark} {trunc(m, 38)}"), ("", "\n")]

    rem = total - end
    L += (
        [("fg:ansibrightblack", f"  ↓  {rem} more below\n")]
        if rem > 0
        else [("", "\n")]
    )

    L += [
        ("", "\n"),
        ("fg:ansibrightblack", f"  {pick_idx + 1} / {total}\n\n"),
        ("fg:ansigreen bold", "  Enter  confirm\n"),
        ("fg:ansiyellow", "  Esc    cancel\n"),
    ]
    return L
