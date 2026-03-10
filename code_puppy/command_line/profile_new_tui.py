"""Profile TUI — dual-panel: profile list on the left, agent config on the right.

Both panels are always visible.  Tab switches which panel has keyboard focus.
Navigating profiles in the left panel live-previews their model assignments on
the right.  Press Enter on a profile to activate it; then Tab to the right panel
to tweak individual agent models, and S to save.

Key bindings
────────────
  Tab         switch focus between panels
  ↑ / ↓      navigate (profiles or agents)
  Enter       activate profile (left) · open model picker (right) · confirm pick
  Esc         cancel model picker
  N           new profile (prompts for name, clones current models)
  S           save agent-model changes to the active profile (right panel)
  Ctrl+C      exit
"""

import sys
from typing import Dict, List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line._profile_tui_panels import (
    VISIBLE,
    load_models,
    render_agent_config,
    render_model_picker,
    render_profile_list,
    valid_name,
)
from code_puppy.messaging import emit_error, emit_success
from code_puppy.task_models import (
    TASK_CONFIGS,
    Task,
    get_active_profile,
    get_model_for,
    list_profiles,
    load_profile,
    save_profile_from_models,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

_TASKS: List[Task] = list(TASK_CONFIGS.keys())
_FOCUS_PROFILES = "profiles"
_FOCUS_AGENTS = "agents"


# ── helpers ───────────────────────────────────────────────────────────────────


async def _prompt_text(label: str, current: str = "") -> Optional[str]:
    """Briefly drop to the normal terminal to collect a text value."""
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


def _models_from_profile(profile: dict) -> Dict[Task, str]:
    """Build a Task→model dict from a raw profile dict."""
    raw = profile.get("models", {})
    base = {t: get_model_for(t) for t in _TASKS}
    for task in _TASKS:
        val = raw.get(task.name.lower())
        if val:
            base[task] = val
    return base


def _desc_for_profile(name: str) -> str:
    try:
        for p in list_profiles():
            if p.get("name") == name:
                return p.get("description", "")
    except Exception:
        pass
    return ""


# ── main TUI ──────────────────────────────────────────────────────────────────


async def interactive_new_profile_tui(initial_name: str = "") -> Optional[str]:
    """
    Dual-panel profile TUI.

    Args:
        initial_name: Profile to highlight/pre-select on open.

    Returns:
        Name of the last activated profile, or ``None``.
    """

    # ── mutable state ─────────────────────────────────────────────────────────
    profiles: List[List[dict]] = [[]]
    prof_idx = [0]
    focus = [_FOCUS_PROFILES]

    agent_idx = [0]
    agent_models: List[Dict[Task, str]] = [{t: get_model_for(t) for t in _TASKS}]

    # model-picker overlay (shown in right panel instead of agent config)
    picking = [False]
    pick_task: List[Optional[Task]] = [None]
    pick_names: List[List[str]] = [[]]
    pick_idx = [0]
    pick_scroll = [0]

    status = [""]
    last_activated: List[Optional[str]] = [None]

    # ── state helpers ─────────────────────────────────────────────────────────

    def reload_profiles():
        try:
            profiles[0] = list_profiles()
        except Exception:
            profiles[0] = []
        active = get_active_profile()
        prof_idx[0] = 0
        for i, p in enumerate(profiles[0]):
            if p.get("name") == active:
                prof_idx[0] = i
                break
        # honour initial_name on first load
        if initial_name and not last_activated[0]:
            for i, p in enumerate(profiles[0]):
                if p.get("name") == initial_name:
                    prof_idx[0] = i
                    break

    def sync_agent_models():
        """Update right panel to reflect the currently highlighted profile."""
        ps = profiles[0]
        if ps and 0 <= prof_idx[0] < len(ps):
            agent_models[0] = _models_from_profile(ps[prof_idx[0]])
        else:
            agent_models[0] = {t: get_model_for(t) for t in _TASKS}

    reload_profiles()
    sync_agent_models()

    # ── widgets ───────────────────────────────────────────────────────────────
    left_ctrl = FormattedTextControl(text="")
    right_ctrl = FormattedTextControl(text="")

    def refresh():
        active = get_active_profile()
        left_ctrl.text = render_profile_list(
            profiles[0], prof_idx[0], active, focus[0] == _FOCUS_PROFILES
        )
        prof_name = profiles[0][prof_idx[0]].get("name", "") if profiles[0] else ""
        if picking[0] and pick_task[0] is not None:
            right_ctrl.text = render_model_picker(
                pick_task[0],
                pick_names[0],
                pick_idx[0],
                pick_scroll[0],
                agent_models[0].get(pick_task[0], ""),
            )
        else:
            right_ctrl.text = render_agent_config(
                agent_models[0],
                agent_idx[0],
                focus[0] == _FOCUS_AGENTS,
                prof_name,
                status[0],
                active,
            )

    layout = Layout(
        VSplit(
            [
                Frame(
                    Window(content=left_ctrl, wrap_lines=False),
                    title="Profiles",
                    width=Dimension(weight=36),
                ),
                Frame(
                    Window(content=right_ctrl, wrap_lines=False),
                    title="Configure",
                    width=Dimension(weight=64),
                ),
            ]
        )
    )

    # ── key bindings ──────────────────────────────────────────────────────────
    kb = KeyBindings()

    @kb.add("tab")
    def _tab(event):
        if picking[0]:
            return
        focus[0] = _FOCUS_AGENTS if focus[0] == _FOCUS_PROFILES else _FOCUS_PROFILES
        status[0] = ""
        refresh()

    @kb.add("up")
    def _up(event):
        if picking[0]:
            if pick_idx[0] > 0:
                pick_idx[0] -= 1
                if pick_idx[0] < pick_scroll[0]:
                    pick_scroll[0] = pick_idx[0]
                refresh()
        elif focus[0] == _FOCUS_PROFILES:
            if prof_idx[0] > 0:
                prof_idx[0] -= 1
                sync_agent_models()
                status[0] = ""
                refresh()
        else:
            if agent_idx[0] > 0:
                agent_idx[0] -= 1
                status[0] = ""
                refresh()

    @kb.add("down")
    def _down(event):
        if picking[0]:
            if pick_idx[0] < len(pick_names[0]) - 1:
                pick_idx[0] += 1
                if pick_idx[0] >= pick_scroll[0] + VISIBLE:
                    pick_scroll[0] = pick_idx[0] - VISIBLE + 1
                refresh()
        elif focus[0] == _FOCUS_PROFILES:
            if prof_idx[0] < len(profiles[0]) - 1:
                prof_idx[0] += 1
                sync_agent_models()
                status[0] = ""
                refresh()
        else:
            if agent_idx[0] < len(_TASKS) - 1:
                agent_idx[0] += 1
                status[0] = ""
                refresh()

    @kb.add("enter")
    def _enter(event):
        if picking[0]:
            # confirm model selection
            if pick_names[0] and pick_task[0] is not None:
                chosen = pick_names[0][pick_idx[0]]
                agent_models[0][pick_task[0]] = chosen
                status[0] = f"Set {pick_task[0].name.lower()} → {chosen[:28]}"
            picking[0] = False
            pick_task[0] = None
            refresh()

        elif focus[0] == _FOCUS_PROFILES:
            # activate highlighted profile
            ps = profiles[0]
            if not ps:
                return
            event.app._ptu = "activate"  # type: ignore[attr-defined]
            event.app._ptu_name = ps[prof_idx[0]].get("name", "")  # type: ignore[attr-defined]
            event.app.exit()

        else:
            # open model picker for highlighted agent
            task = _TASKS[agent_idx[0]]
            names = load_models()
            if not names:
                status[0] = "No models available"
                refresh()
                return
            cur = agent_models[0].get(task, "")
            start = names.index(cur) if cur in names else 0
            pick_task[0] = task
            pick_names[0] = names
            pick_idx[0] = start
            pick_scroll[0] = max(0, start - VISIBLE // 2)
            picking[0] = True
            status[0] = ""
            refresh()

    @kb.add("escape")
    def _esc(event):
        if picking[0]:
            picking[0] = False
            pick_task[0] = None
            status[0] = ""
            refresh()

    @kb.add("n")
    def _kn(event):
        if not picking[0]:
            event.app._ptu = "new"  # type: ignore[attr-defined]
            event.app.exit()

    @kb.add("s")
    def _ks(event):
        if picking[0] or focus[0] != _FOCUS_AGENTS:
            return
        active = get_active_profile()
        prof_name = profiles[0][prof_idx[0]].get("name", "") if profiles[0] else ""
        if not active or prof_name != active:
            status[0] = "Activate this profile first (Enter in left panel)"
            refresh()
            return
        event.app._ptu = "save"  # type: ignore[attr-defined]
        event.app.exit()

    @kb.add("c-c")
    def _kcc(event):
        event.app._ptu = "cancel"  # type: ignore[attr-defined]
        event.app.exit()

    # ── run loop ──────────────────────────────────────────────────────────────
    app = Application(
        layout=layout, key_bindings=kb, full_screen=False, mouse_support=False
    )
    app._ptu = None  # type: ignore[attr-defined]

    set_awaiting_user_input(True)
    sys.stdout.write("\033[?1049h\033[2J\033[H")
    sys.stdout.flush()

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
                return last_activated[0]

            if action == "activate":
                pname = getattr(app, "_ptu_name", "")
                ok, msg = load_profile(pname)
                if ok:
                    last_activated[0] = pname
                    reload_profiles()
                    sync_agent_models()
                    status[0] = f"'{pname}' is now active — Tab to configure"
                    emit_success(f"✅ Profile '{pname}' activated")
                else:
                    status[0] = f"Failed: {msg}"

            elif action == "new":
                v = await _prompt_text("  New profile name: ", "")
                if v and valid_name(v):
                    active_desc = _desc_for_profile(get_active_profile() or "")
                    if save_profile_from_models(v, active_desc, agent_models[0]):
                        ok2, _ = load_profile(v)
                        if ok2:
                            last_activated[0] = v
                        reload_profiles()
                        sync_agent_models()
                        status[0] = f"Created '{v}' — Tab to configure"
                        emit_success(f"✅ Profile '{v}' created")
                    else:
                        status[0] = "Failed to create profile"
                elif v is not None:
                    status[0] = "Invalid name — use letters, digits, - or _"

            elif action == "save":
                active = get_active_profile()
                if active:
                    if save_profile_from_models(
                        active, _desc_for_profile(active), agent_models[0]
                    ):
                        reload_profiles()
                        status[0] = f"Saved '{active}'"
                        emit_success(f"✅ Profile '{active}' saved")
                    else:
                        status[0] = "Save failed"

    finally:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        set_awaiting_user_input(False)
