"""Runtime scaffolding for multi-session chat.

These modules are intentionally lightweight and are not yet wired into
`/ws/chat` or the planned `/ws/chat_mux` endpoint.

They provide an async-friendly session runtime object (cancellation, active
streaming task handle, etc.) and a manager that keeps runtimes keyed by
session_id.
"""

from .session_runtime import SessionRuntime
from .session_runtime_manager import SessionRuntimeManager

__all__ = ["SessionRuntime", "SessionRuntimeManager"]
