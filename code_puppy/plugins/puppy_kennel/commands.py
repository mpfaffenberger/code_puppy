"""Slash commands for humans interacting with the kennel.

Sub-commands under ``/kennel``:

* ``/kennel``                 — Show stats and recent activity
* ``/kennel search <query>``  — FTS5 search the current recall scope
* ``/kennel wings``           — List all wings and drawer counts
* ``/kennel stats``           — Storage stats and totals
* ``/kennel help``            — Usage hint

All commands return ``True`` to mark them handled (per callback contract)
or ``None`` to let other plugins try. ``False`` is never returned because
we own the ``/kennel`` prefix unconditionally.
"""

from __future__ import annotations

from typing import Any

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from . import kennel
from .config import DB_PATH
from .state import is_enabled, set_enabled
from .wings import default_recall_scope, detect_cwd


def _reload_current_agent() -> None:
    """Rebuild the active agent so its tool list reflects the new kennel state.

    Toggling memory on/off changes what ``register_agent_tools`` advertises,
    but the live agent has already baked its tools in at construction time.
    Without a reload, ``/kennel disable`` would leave the kennel tools
    dangling on the agent (and ``/kennel enable`` wouldn't add them back)
    until the next natural reload. Fail soft — toggling persisted fine
    even if the reload trips.
    """
    try:
        from code_puppy.agents.agent_manager import get_current_agent

        get_current_agent().reload_code_generation_agent()
    except Exception as exc:  # noqa: BLE001
        emit_error(f"Could not reload agent after kennel toggle: {exc!r}")


_COMMAND = "kennel"
_HELP_LINES: tuple[tuple[str, str], ...] = (
    ("kennel", "Mist Memory — local memory: search, stats, wings"),
)


def _parse(command: str) -> tuple[str, str]:
    """Split ``/kennel <sub> <rest>`` into ``(sub, rest)``."""
    body = command.lstrip("/").strip()
    if body.startswith(_COMMAND):
        body = body[len(_COMMAND) :].strip()
    parts = body.split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    return sub, rest


def _humanize_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


def _cmd_stats() -> bool:
    total = kennel.count_drawers()
    wings = kennel.list_wings()
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    state = "enabled" if is_enabled() else "DISABLED"
    emit_info(f"Mist Memory at `{DB_PATH}`")
    emit_info(f"  state   : {state}")
    emit_info(f"  drawers : {total}")
    emit_info(f"  wings   : {len(wings)}")
    emit_info(f"  on disk : {_humanize_bytes(db_size)}")
    return True


def _cmd_status() -> bool:
    if is_enabled():
        emit_success("Mist Memory memory is ENABLED.")
    else:
        emit_warning(
            "Mist Memory memory is DISABLED. Run /kennel enable to turn it on."
        )
    return True


def _cmd_enable() -> bool:
    if is_enabled():
        emit_info("Mist Memory memory is already enabled.")
        return True
    try:
        set_enabled(True)
    except Exception as exc:  # noqa: BLE001
        emit_warning(f"Could not persist enabled state: {exc!r}")
        return True
    _reload_current_agent()
    emit_success("Mist Memory memory ENABLED. New runs will be recorded and recalled.")
    return True


def _cmd_disable() -> bool:
    if not is_enabled():
        emit_info("Mist Memory memory is already disabled.")
        return True
    try:
        set_enabled(False)
    except Exception as exc:  # noqa: BLE001
        emit_warning(f"Could not persist disabled state: {exc!r}")
        return True
    _reload_current_agent()
    emit_success(
        "Mist Memory memory DISABLED. Existing drawers remain on disk; "
        "recording and recall are paused. Run /kennel enable to resume."
    )
    return True


def _cmd_wings() -> bool:
    wings = kennel.list_wings()
    if not wings:
        emit_warning("No wings in the kennel yet.")
        return True
    emit_info(f"{len(wings)} wing(s):")
    for w in wings:
        n = kennel.count_drawers(wing_name=w)
        emit_info(f"  {w}  ({n} drawer{'s' if n != 1 else ''})")
    return True


def _cmd_search(query: str) -> bool:
    if not query.strip():
        emit_warning("Usage: /kennel search <your query>")
        return True
    wings = default_recall_scope("mist", detect_cwd())
    hits = kennel.search_drawers_multi(query, wing_names=wings, limit=5)
    if not hits:
        emit_warning(f"No hits for '{query}' in scope {wings}")
        return True
    emit_success(f"{len(hits)} hit(s) for '{query}':")
    for d in hits:
        agent = (d.metadata or {}).get("agent", "?")
        preview = d.content[:200].replace("\n", " ")
        emit_info(f"  [{d.ts}] {agent}: {preview}{'…' if len(d.content) > 200 else ''}")
    return True


def _cmd_help() -> bool:
    emit_info("Mist Memory commands:")
    emit_info("  /kennel                 - stats + recent activity")
    emit_info("  /kennel search <query>  - FTS5 search across default scope")
    emit_info("  /kennel wings           - list wings with drawer counts")
    emit_info("  /kennel stats           - storage stats + enabled state")
    emit_info("  /kennel status          - is memory enabled?")
    emit_info("  /kennel enable          - turn memory on")
    emit_info("  /kennel disable         - turn memory off (drawers preserved)")
    emit_info("  /kennel help            - this message")
    return True


def _cmd_default_overview() -> bool:
    """Bare ``/kennel`` — show stats + a tiny preview of the recent block."""
    _cmd_stats()
    from .retriever import build_recall_block

    block = build_recall_block()
    if block:
        emit_info("")
        emit_info(block)
    return True


def handle(command: str, name: str) -> Any:
    """Dispatch ``/kennel`` and aliases. Returns ``None`` for non-kennel cmds."""
    if name != _COMMAND:
        return None
    sub, rest = _parse(command)
    if not sub:
        return _cmd_default_overview()
    if sub == "search":
        return _cmd_search(rest)
    if sub == "wings":
        return _cmd_wings()
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
    emit_warning(f"Unknown /kennel subcommand: '{sub}'")
    return _cmd_help()


def help_entries() -> list[tuple[str, str]]:
    """``custom_command_help`` callback — list ``/kennel`` in /help."""
    return list(_HELP_LINES)
