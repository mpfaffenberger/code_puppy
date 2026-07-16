"""Atomic counter for unique DBOS workflow IDs (sub-agent invocations)."""

from __future__ import annotations

import itertools

_dbos_workflow_counter = itertools.count()


def generate_dbos_workflow_id(base_id: str) -> str:
    """Generate a unique DBOS workflow ID by appending an atomic counter.

    DBOS requires workflow IDs to be unique across all executions.
    """
    counter = next(_dbos_workflow_counter)
    return f"{base_id}-{counter}"
