"""Budget state — authoritative in-memory holder synced to the carrier.

Why a holder *and* a carrier? The ``pre_tool_call`` / ``post_tool_call`` hooks
that increment and gate the budget do **not** receive the conversation history,
so they can't touch the carrier directly. The carrier (see :mod:`carrier`) is
the *persistence* layer; this holder is the *live* layer.

Sync contract (driven by :mod:`carrier_processor`, which runs each model call):

* On a fresh process / after a session reset, the holder is "unloaded". The
  first processor pass loads state from the carrier (so ``--resume`` restores
  counts).
* While loaded, the holder is authoritative — it accumulates the tool-call
  increments that happen between model calls. The processor writes the holder
  back into the carrier every call, re-pinning it so it survives compaction.

State is a plain dict matching :func:`carrier.default_state`.
"""

from __future__ import annotations

import threading
from typing import Any, Dict

from . import carrier
from .config import get_max_budget, get_onboarding_budget

# Tools that must NEVER count against the budget AND must never be blocked,
# otherwise the agent cannot escape the gate (the classic deadlock: if the
# unlock tools are themselves blocked, there is no way to unlock).
#
# Two categories are exempt:
#   1. Escape-hatch tools (skills + tasks) — needed to unlock / comply.
#   2. Read-only exploration tools — the agent must be able to READ and LIST
#      to understand a codebase before it can know what skill to create.
#      Gating exploration forces "create a skill blindly" or "burn the budget
#      reading, then get blocked before acting", both of which are worse than
#      letting cheap read-only calls through. Only mutating/acting tools and
#      other side-effecting calls count against the budget.
EXEMPT_TOOLS = frozenset(
    {
        # --- escape hatch: skills ---
        "skill_manage",
        "activate_skill",
        "list_or_search_skills",
        # --- escape hatch: tasks ---
        "task_create",
        "task_update",
        "task_list",
        "task_get",
        "taskcreate",
        "taskupdate",
        "tasklist",
        "taskget",
        # --- read-only exploration (never gated; understanding precedes acting) ---
        "read_file",
        "list_files",
        "grep",
        "glob",
        "find",
    }
)

_UNLOCK_TOOL_MARKERS = ("skill_manage", "activate_skill")

_lock = threading.Lock()
_state: Dict[str, Any] = carrier.default_state()
_loaded = False


def is_exempt(tool_name: str) -> bool:
    return (tool_name or "").strip().lower() in EXEMPT_TOOLS


def is_unlock_action(tool_name: str) -> bool:
    name = (tool_name or "").strip().lower()
    return any(marker in name for marker in _UNLOCK_TOOL_MARKERS)


# --- Carrier sync (called by the history processor) -----------------------


def load_from_carrier(history: list) -> None:
    """Load state from the carrier the first time we see history this process.

    Subsequent calls are no-ops so live increments aren't clobbered.

    Per-turn regeneration: when enabled (the default), the spent counter is
    refreshed to zero *after* hydrating durable fields (``unlocked``,
    ``skill_usage``) from the carrier. This makes the gate a per-turn allowance
    instead of a monotonic lifetime cap that eventually locks the agent out for
    good. Disable via ``hermes_governance_regenerate_each_turn=false`` to get the
    old lifetime-cap behaviour.
    """
    global _state, _loaded
    with _lock:
        if _loaded:
            return
        found = carrier.find_state(history)
        if found is not None:
            _state = found
        _loaded = True
        _maybe_regenerate_locked()


def _maybe_regenerate_locked() -> None:
    """Zero the per-turn counters in-place (caller holds ``_lock``)."""
    try:
        from .config import is_regenerate_each_turn
    except Exception:
        return
    if not is_regenerate_each_turn():
        return
    _state["used"] = 0
    _state["calls_since_skill"] = 0
    _state["acting_since_skill"] = 0


def snapshot() -> Dict[str, Any]:
    with _lock:
        return dict(_state)


def reset() -> None:
    """Forget live state so the next processor pass reloads from the carrier."""
    global _state, _loaded
    with _lock:
        _state = carrier.default_state()
        _loaded = False


# --- Budget operations (called by enforcer hooks) -------------------------


def _cap_locked() -> int:
    return get_max_budget() if _state["unlocked"] else get_onboarding_budget()


def cap() -> int:
    with _lock:
        return _cap_locked()


def used() -> int:
    with _lock:
        return int(_state["used"])


def unlocked() -> bool:
    with _lock:
        return bool(_state["unlocked"])


def remaining() -> int:
    with _lock:
        return max(0, _cap_locked() - int(_state["used"]))


def would_exceed() -> bool:
    """True if the NEXT non-exempt tool call would breach the cap."""
    with _lock:
        return int(_state["used"]) >= _cap_locked()


def increment() -> None:
    with _lock:
        _state["used"] = int(_state["used"]) + 1


def unlock() -> bool:
    """Expand the cap. Returns True if this was the unlocking transition."""
    with _lock:
        if _state["unlocked"]:
            return False
        _state["unlocked"] = True
        return True


# --- Nudge counters (kept in the same state dict so they also persist) ----


def note_nudge_call(is_acting: bool) -> None:
    with _lock:
        _state["calls_since_skill"] = int(_state["calls_since_skill"]) + 1
        if is_acting:
            _state["acting_since_skill"] = int(_state["acting_since_skill"]) + 1


def reset_nudge_counters() -> None:
    with _lock:
        _state["calls_since_skill"] = 0
        _state["acting_since_skill"] = 0


def nudge_counts() -> tuple[int, int]:
    with _lock:
        return int(_state["calls_since_skill"]), int(_state["acting_since_skill"])


# --- Skill usage (for the curator) ----------------------------------------


def record_skill_use(skill_name: str, iso_ts: str) -> None:
    if not skill_name:
        return
    with _lock:
        usage = _state.setdefault("skill_usage", {})
        usage[skill_name] = iso_ts
