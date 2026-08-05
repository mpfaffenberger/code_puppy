"""Slash commands for humans interacting with yantrik_memory.

Sub-commands under ``/yantrik``:

* ``/yantrik``         — show status + stats
* ``/yantrik status``  — is memory enabled?
* ``/yantrik enable``  — turn learned memory on (opt-in)
* ``/yantrik disable`` — turn it off (stored memories preserved)
* ``/yantrik stats``   — store totals + enabled state
* ``/yantrik help``    — usage hint

Handlers return ``True`` to mark a command handled (per callback contract) or
``None`` to let other plugins try.
"""

from __future__ import annotations

from typing import Any

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from . import substrate
from .config import DB_PATH
from .state import is_enabled, set_enabled

_COMMAND = "yantrik"
_HELP_LINES: tuple[tuple[str, str], ...] = (
    ("yantrik", "Yantrik memory — YantrikDB-backed learning memory (opt-in)"),
)


def _reload_current_agent() -> None:
    """Rebuild the active agent so its tool list reflects the new state.

    Toggling memory on/off changes what ``register_agent_tools`` advertises;
    the live agent baked its tools in at construction. Fail soft.
    """
    try:
        from code_puppy.agents.agent_manager import get_current_agent

        get_current_agent().reload_code_generation_agent()
    except Exception as exc:  # noqa: BLE001
        emit_error(f"Could not reload agent after yantrik toggle: {exc!r}")


def _parse(command: str) -> tuple[str, str]:
    """Split ``/yantrik <sub> <rest>`` into ``(sub, rest)``."""
    body = command.lstrip("/").strip()
    if body.startswith(_COMMAND):
        body = body[len(_COMMAND) :].strip()
    parts = body.split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    return sub, rest


def _namespace() -> str:
    try:
        return substrate.namespace_for_cwd()
    except Exception:
        return "default"


def _cmd_stats() -> bool:
    state = "enabled" if is_enabled() else "DISABLED"
    available = "yes" if substrate.MEMORY_AVAILABLE else "NO (YantrikDB missing)"
    emit_info(f"Yantrik memory at `{DB_PATH}`")
    emit_info(f"  state     : {state}")
    emit_info(f"  yantrikdb : {available}")
    emit_info(f"  namespace : {_namespace()}")
    if substrate.MEMORY_AVAILABLE and is_enabled():
        mem = None
        try:
            from .tools import _open

            mem = _open()
            emit_info(f"  facts     : {len(mem.list_semantic(limit=10000))}")
        except Exception as exc:  # noqa: BLE001
            emit_warning(f"  facts     : (unavailable: {exc!r})")
        finally:
            if mem is not None:
                mem.close()
    return True


def _cmd_status() -> bool:
    if not substrate.MEMORY_AVAILABLE:
        emit_warning(
            "Yantrik memory is INERT — YantrikDB is not installed. "
            "Install yantrikdb_mcp[onnx] to enable it."
        )
        return True
    if is_enabled():
        emit_success("Yantrik memory is ENABLED.")
    else:
        emit_warning(
            "Yantrik memory is DISABLED (opt-in). Run /yantrik enable to turn it on."
        )
    return True


def _cmd_enable() -> bool:
    if not substrate.MEMORY_AVAILABLE:
        emit_warning(
            "Cannot enable — YantrikDB is not installed. "
            "Install yantrikdb_mcp[onnx] first."
        )
        return True
    if is_enabled():
        emit_info("Yantrik memory is already enabled.")
        return True
    try:
        set_enabled(True)
    except Exception as exc:  # noqa: BLE001
        emit_warning(f"Could not persist enabled state: {exc!r}")
        return True
    _reload_current_agent()
    emit_success(
        "Yantrik memory ENABLED. Turns will be distilled into learned facts "
        "and recalled into the prompt."
    )
    return True


def _cmd_disable() -> bool:
    if not is_enabled():
        emit_info("Yantrik memory is already disabled.")
        return True
    try:
        set_enabled(False)
    except Exception as exc:  # noqa: BLE001
        emit_warning(f"Could not persist disabled state: {exc!r}")
        return True
    _reload_current_agent()
    emit_success(
        "Yantrik memory DISABLED. Stored memories remain on disk; distilling "
        "and recall are paused. Run /yantrik enable to resume."
    )
    return True


def _cmd_help() -> bool:
    emit_info("Yantrik memory commands:")
    emit_info("  /yantrik           - status + stats")
    emit_info("  /yantrik status    - is memory enabled?")
    emit_info("  /yantrik enable    - turn learned memory on (opt-in)")
    emit_info("  /yantrik disable   - turn it off (memories preserved)")
    emit_info("  /yantrik stats     - store totals + enabled state")
    emit_info("  /yantrik help      - this message")
    return True


def handle(command: str, name: str) -> Any:
    """Dispatch ``/yantrik``. Returns ``None`` for non-yantrik commands."""
    if name != _COMMAND:
        return None
    sub, _rest = _parse(command)
    if not sub:
        return _cmd_status() and _cmd_stats()
    if sub == "stats":
        return _cmd_stats()
    if sub == "status":
        return _cmd_status()
    if sub in ("enable", "on"):
        return _cmd_enable()
    if sub in ("disable", "off"):
        return _cmd_disable()
    if sub in ("help", "?"):
        return _cmd_help()
    emit_warning(f"Unknown /yantrik subcommand: '{sub}'")
    return _cmd_help()


def help_entries() -> list[tuple[str, str]]:
    """``custom_command_help`` callback — list ``/yantrik`` in /help."""
    return list(_HELP_LINES)
