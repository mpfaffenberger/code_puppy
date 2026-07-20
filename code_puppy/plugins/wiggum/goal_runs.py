"""Durable records for resumable ``/goal`` runs."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from code_puppy.config import STATE_DIR

_RUNS_DIR = Path(STATE_DIR) / "goal_runs"


@dataclass(frozen=True)
class GoalRun:
    """The minimum state required to continue an interrupted goal."""

    run_id: str
    prompt: str
    loop_count: int = 0
    remediation_notes: str | None = None
    status: str = "active"


def create(prompt: str) -> GoalRun:
    """Create and persist a new goal run."""
    run = GoalRun(run_id=str(uuid.uuid4()), prompt=prompt)
    save(run)
    return run


def save(run: GoalRun) -> None:
    """Atomically persist a goal run."""
    _RUNS_DIR.mkdir(parents=True, exist_ok=True)
    destination = _path(run.run_id)
    temporary = destination.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(asdict(run), indent=2), encoding="utf-8")
    temporary.replace(destination)


def load(run_id: str) -> GoalRun | None:
    """Load a run by UUID, returning ``None`` for invalid or missing IDs."""
    normalized = _normalize_uuid(run_id)
    if normalized is None:
        return None
    try:
        payload = json.loads(_path(normalized).read_text(encoding="utf-8"))
        return GoalRun(
            run_id=normalized,
            prompt=str(payload["prompt"]),
            loop_count=max(0, int(payload.get("loop_count", 0))),
            remediation_notes=payload.get("remediation_notes"),
            status=str(payload.get("status", "active")),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def update(
    run_id: str,
    *,
    loop_count: int,
    remediation_notes: str | None,
    status: str = "active",
) -> None:
    """Update mutable progress fields when the run still exists."""
    run = load(run_id)
    if run is None:
        return
    save(
        GoalRun(
            run_id=run.run_id,
            prompt=run.prompt,
            loop_count=loop_count,
            remediation_notes=remediation_notes,
            status=status,
        )
    )


def _path(run_id: str) -> Path:
    return _RUNS_DIR / f"{run_id}.json"


def _normalize_uuid(value: str) -> str | None:
    try:
        return str(uuid.UUID(value.strip()))
    except (AttributeError, ValueError):
        return None
