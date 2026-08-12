"""The current run's session id, readable from anywhere inside that run.

``run_with_mcp`` mints a fresh ``group_id`` (a UUID) for every agent run and
hands it to the ``user_prompt_submit``, ``agent_run_start`` and
``agent_run_end`` callbacks. It does *not* reach ``pre_tool_call`` /
``post_tool_call``: pydantic-ai invokes those deep inside the run, and the
callback contract has no run-scoped argument to carry it.

So anything that wants to correlate tool calls with the run they belong to —
hook scripts, telemetry, audit logs — had no way to recover the id. This module
publishes it instead, so any code executing inside the run can read it.

Why a ContextVar rather than a module global: nested runs are real (a sub-agent
calling ``run_with_mcp`` while its parent run is still in flight), and the agent
run itself executes in its own ``asyncio.Task``. ContextVars are copied into a
task at ``create_task`` time and writes inside a task stay local to it, so every
run observes its own id and a nested run can never clobber its parent's.
"""

from contextvars import ContextVar
from typing import Optional

_session_id: ContextVar[Optional[str]] = ContextVar(
    "code_puppy_session_id", default=None
)


def set_session_id(session_id: Optional[str]) -> None:
    """Publish *session_id* as the current context's run id."""
    _session_id.set(session_id)


def get_session_id() -> Optional[str]:
    """Return the current run's session id, or ``None`` outside of a run."""
    return _session_id.get()
