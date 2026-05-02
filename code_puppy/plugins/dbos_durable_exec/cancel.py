"""Cancel an in-flight DBOS workflow, registered via agent_run_cancel hook."""

from __future__ import annotations


async def cancel_workflow(group_id: str) -> None:
    """Best-effort cancel of a DBOS workflow. Never raises into core."""
    try:
        from dbos import DBOS
    except ImportError:
        return
    try:
        await DBOS.cancel_workflow_async(group_id)
    except Exception:
        pass
