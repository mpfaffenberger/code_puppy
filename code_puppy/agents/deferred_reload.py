"""Queue agent rebuilds for the live CLI event loop.

Background integrations may update an agent's configuration from a worker
thread, but rebuilding the pydantic/MCP agent must happen on the main event
loop. This module provides the synchronization seam between those contexts.
"""

import threading

_pending_agent_reloads: set[str] = set()
_pending_lock = threading.Lock()


def request_agent_reload(agent_name: str) -> None:
    """Request a main-loop reload for *agent_name* after its config changes."""
    with _pending_lock:
        _pending_agent_reloads.add(agent_name)


def apply_pending_agent_reloads() -> None:
    """Apply queued reloads for the currently active agent.

    Call this from the main event loop. Requests for inactive agents remain
    queued until that agent becomes active, avoiding a lost update while a
    background operation finishes during an agent switch.
    """
    from code_puppy.agents import get_current_agent

    with _pending_lock:
        pending = set(_pending_agent_reloads)
        _pending_agent_reloads.clear()

    if not pending:
        return

    try:
        current = get_current_agent()
        if current.name in pending:
            if hasattr(current, "refresh_config"):
                current.refresh_config()
            current.reload_code_generation_agent()
            pending.remove(current.name)
    except Exception:
        # Keep the request queued so a later prompt can retry safely.
        pass

    if pending:
        with _pending_lock:
            _pending_agent_reloads.update(pending)
