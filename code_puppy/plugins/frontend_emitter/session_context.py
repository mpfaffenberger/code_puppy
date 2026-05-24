"""Session-id ContextVar used by the frontend_emitter plugin.

This module defines a single ``contextvars.ContextVar`` that carries
the *current agent invocation's* session identifier across the asyncio
call graph without requiring every callable to take an explicit kwarg.

The primary use case is letting embedders (e.g. a WebSocket backend
hosting multiple concurrent agent sessions) tag every event emitted
during an agent run with a session identifier, so subscribers can
filter events by session without monkey-patching the emitter.

Usage::

    from code_puppy.plugins.frontend_emitter.session_context import (
        current_emitter_session_id,
    )

    token = current_emitter_session_id.set("my-session-id")
    try:
        await some_agent_work()  # any emit_event() inside picks up the sid
    finally:
        current_emitter_session_id.reset(token)

Because ``ContextVar`` values are copied into each new asyncio Task at
creation time, sessions are naturally isolated across concurrent tasks
without explicit propagation.

Scope note
----------
This ContextVar is intentionally scoped to the ``frontend_emitter``
plugin.  It is not a general-purpose ``code_puppy.context.session_id``
because the only consumer is the emitter's session-channel fan-out
logic.  Other subsystems that need session-level metadata should
introduce their own ContextVar with a clearly-scoped name.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

# The session_id of the currently running agent invocation, if any.
#
# Set by embedders (e.g. a backend WebSocket session handler) before
# kicking off agent work, and read by ``emit_event()`` (and helpers
# in ``register_callbacks``) to tag every emitted event with the
# current session.
#
# ``None`` is the legitimate "no session context" value -- callers
# should treat it as "this event is not associated with any particular
# session" rather than as an error.
current_emitter_session_id: ContextVar[Optional[str]] = ContextVar(
    "code_puppy_frontend_emitter_session_id", default=None
)


__all__ = ["current_emitter_session_id"]
