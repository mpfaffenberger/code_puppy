"""Register puppy_kennel with Mist's callback system.

Hooks wired:
* ``load_prompt``         -> passive recall block in the system prompt
* ``agent_run_end``       -> record the agent's response as a verbatim drawer
* ``register_tools``      -> defines kennel tools in ``TOOL_REGISTRY``
* ``register_agent_tools``-> advertises kennel tools to every agent's tool list
* ``custom_command``      -> handles ``/kennel`` and subcommands
* ``custom_command_help`` -> advertises ``/kennel`` in the /help menu
"""

from __future__ import annotations

from code_puppy.callbacks import register_callback
from code_puppy.messaging.bus import emit_debug

from . import commands, kennel, tools
from .recorder import record_run_end
from .retriever import build_recall_block
from .state import is_enabled


def _initialize_once() -> bool:
    """Create the SQLite schema on first import. Idempotent + fail-soft."""
    try:
        kennel.initialize()
        return True
    except Exception as exc:  # noqa: BLE001 — plugin must never crash boot.
        emit_debug(f"[puppy_kennel] init failed, disabling: {exc!r}")
        return False


def _on_load_prompt() -> str | None:
    """Sync hook — returns a text fragment or None."""
    try:
        return build_recall_block()
    except Exception as exc:  # noqa: BLE001
        emit_debug(f"[puppy_kennel] load_prompt skipped: {exc!r}")
        return None


def _on_agent_run_end(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
    success: bool = True,
    error: Exception | None = None,
    response_text: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Async-compatible hook (sync body, runner accepts either)."""
    record_run_end(
        agent_name=agent_name,
        model_name=model_name,
        session_id=session_id,
        success=success,
        error=error,
        response_text=response_text,
        metadata=metadata,
    )


_KENNEL_TOOL_NAMES = (
    "kennel_recall",
    "kennel_remember",
    "kennel_recent",
    "kennel_list_wings",
    "kennel_stats",
)


def _advertise_tools_to_agent(agent_name: str | None = None) -> list[str]:
    """``register_agent_tools`` callback — advertise kennel tools to every agent.

    Agnostic to ``agent_name`` for now: memory is universally useful, no
    agent currently has a reason to opt out. If that changes, branch here.

    When the kennel is toggled off via ``/kennel disable``, we advertise
    NO tools — the agent shouldn't see (and definitely shouldn't try to
    call) memory tools that will just bounce with ``DISABLED_TOOL_ERROR``.
    The slash command pairs this with an agent reload so the tool list
    actually shrinks/grows live.
    """
    if not is_enabled():
        return []
    return list(_KENNEL_TOOL_NAMES)


if _initialize_once():
    register_callback("load_prompt", _on_load_prompt)
    register_callback("agent_run_end", _on_agent_run_end)
    register_callback("register_tools", tools.register_tools_callback)
    register_callback("register_agent_tools", _advertise_tools_to_agent)
    register_callback("custom_command", commands.handle)
    register_callback("custom_command_help", commands.help_entries)
