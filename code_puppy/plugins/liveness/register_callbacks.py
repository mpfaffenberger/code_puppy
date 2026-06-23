"""Drive the standalone liveliness heartbeat from the agent run lifecycle.

Starts the title-bar pulse when an agent run begins and stops it when the run
ends (ref-counted, so nested sub-agent runs don't cut it short). This is the
dedicated "agent is alive" signal — independent of the sparkle spinner and the
text-streaming path.
"""

from __future__ import annotations

from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.messaging.liveness import get_heartbeat


def _on_agent_run_start(
    agent_name: str | None = None,
    model_name: str | None = None,
    session_id: str | None = None,
) -> None:
    try:
        get_heartbeat().start()
    except Exception:
        pass


def _on_agent_run_end(*args: Any, **kwargs: Any) -> None:
    try:
        get_heartbeat().stop()
    except Exception:
        pass


register_callback("agent_run_start", _on_agent_run_start)
register_callback("agent_run_end", _on_agent_run_end)
