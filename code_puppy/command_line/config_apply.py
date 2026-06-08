"""Single-key config writes with validation + side effects.

Used by both the ``/set`` slash command and the interactive ``/set``
menu so validation rules (e.g. ``cancel_agent_key`` allow-list) and
restart-required warnings stay in one place.

Lives in its own module to break the import cycle that would otherwise
form between ``config_commands`` and ``set_menu``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of writing a single config key/value pair.

    ``warning`` carries validation/policy notices that should fire
    regardless of whether the agent reload succeeds (e.g. restart-required
    notices for ``enable_dbos`` and ``cancel_agent_key``).
    ``reload_error`` is the separate "the config saved fine but the live
    agent couldn't be reloaded" signal -- keeping it on its own field
    means a reload failure can't silently clobber a restart notice.
    """

    ok: bool
    value_after: Optional[str] = None
    error: Optional[str] = None
    warning: Optional[str] = None
    reload_error: Optional[str] = None
    requires_restart: bool = False


def _restart_notice(label: str) -> str:
    return f"{label} changed. Please restart Code Puppy for this change to take effect."


def invalidate_post_write_caches(key: str) -> None:
    """Invalidate any in-memory caches whose source-of-truth just changed.

    Some config getters cache resolved values per-process to avoid
    re-reading puppy.cfg + validating registries on every call. After a
    write (set OR reset) those caches need explicit invalidation, or
    subsequent reads return the stale pre-write value until the process
    restarts -- which is exactly how users discover this kind of bug.

    Called from both the slash-set path (:func:`apply_setting`) and the
    menu reset path so the two stay in lock-step.

    Today only the ``model`` key has a cache that needs this treatment;
    add new keys here as they grow caches.
    """
    if key == "model":
        from code_puppy.config import clear_model_cache, reset_session_model

        reset_session_model()
        clear_model_cache()


def apply_setting(
    key: str,
    value: str,
    *,
    reload_agent: bool = True,
) -> ApplyResult:
    """Persist ``key`` -> ``value`` to ``puppy.cfg`` with validation.

    Parameters
    ----------
    key:
        Config key to write.
    value:
        Value to persist. Stored as-is unless validation normalises it
        (e.g. ``cancel_agent_key`` is lower-cased).
    reload_agent:
        When True (the default) the currently-active agent is reloaded
        so the change takes effect immediately. The menu passes False
        per-edit and triggers a single reload at picker exit to avoid
        reload thrash when the user edits multiple settings.
    """
    from code_puppy.config import set_config_value

    if not key:
        return ApplyResult(ok=False, error="You must supply a key.")

    warning: Optional[str] = None
    requires_restart = False
    normalized_value = value

    if key == "cancel_agent_key":
        from code_puppy.keymap import VALID_CANCEL_KEYS

        normalized_value = value.strip().lower()
        if normalized_value not in VALID_CANCEL_KEYS:
            return ApplyResult(
                ok=False,
                error=(
                    f"Invalid cancel_agent_key '{value}'. Valid options: "
                    f"{', '.join(sorted(VALID_CANCEL_KEYS))}"
                ),
            )
        warning = _restart_notice("cancel_agent_key")
        requires_restart = True
    elif key == "enable_dbos":
        warning = _restart_notice("DBOS configuration")
        requires_restart = True

    set_config_value(key, normalized_value)
    invalidate_post_write_caches(key)

    reload_error: Optional[str] = None
    if reload_agent:
        from code_puppy.agents import get_current_agent

        try:
            get_current_agent().reload_code_generation_agent()
        except Exception as exc:
            reload_error = f"Config saved but agent reload failed: {exc}"

    return ApplyResult(
        ok=True,
        value_after=normalized_value,
        warning=warning,
        reload_error=reload_error,
        requires_restart=requires_restart,
    )
