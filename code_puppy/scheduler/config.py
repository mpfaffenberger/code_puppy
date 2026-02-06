"""Scheduler configuration and task management.

Handles ScheduledTask dataclass definition and JSON persistence
for scheduled Code Puppy tasks.
"""

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import List, Optional

# Import from existing config
from code_puppy.config import DATA_DIR

SCHEDULES_FILE = os.path.join(DATA_DIR, "scheduled_tasks.json")
SCHEDULER_PID_FILE = os.path.join(DATA_DIR, "scheduler.pid")
SCHEDULER_LOG_DIR = os.path.join(DATA_DIR, "scheduler_logs")


@dataclass
class ScheduledTask:
    """A scheduled Code Puppy task."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    prompt: str = ""
    agent: str = "code-puppy"
    model: str = ""  # Uses default if empty
    schedule_type: str = "interval"  # "interval", "cron", "daily", "hourly"
    schedule_value: str = "1h"  # e.g., "30m", "1h", "0 9 * * *" for cron
    working_directory: str = "."
    log_file: str = ""  # Auto-generated if empty
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_run: Optional[str] = None
    last_status: Optional[str] = None  # "success", "failed", "running"
    last_exit_code: Optional[int] = None

    def __post_init__(self):
        if not self.log_file:
            self.log_file = os.path.join(SCHEDULER_LOG_DIR, f"{self.id}.log")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def ensure_scheduler_dirs() -> None:
    """Create scheduler directories if they don't exist."""
    os.makedirs(SCHEDULER_LOG_DIR, mode=0o700, exist_ok=True)


def load_tasks() -> List[ScheduledTask]:
    """Load all scheduled tasks from JSON file."""
    ensure_scheduler_dirs()
    if not os.path.exists(SCHEDULES_FILE):
        return []
    try:
        with open(SCHEDULES_FILE, "r") as f:
            data = json.load(f)
            return [ScheduledTask.from_dict(t) for t in data]
    except (json.JSONDecodeError, IOError):
        return []


def save_tasks(tasks: List[ScheduledTask]) -> None:
    """Save all scheduled tasks to JSON file."""
    ensure_scheduler_dirs()
    with open(SCHEDULES_FILE, "w") as f:
        json.dump([t.to_dict() for t in tasks], f, indent=2)


def add_task(task: ScheduledTask) -> None:
    """Add a new scheduled task."""
    tasks = load_tasks()
    tasks.append(task)
    save_tasks(tasks)


def update_task(task: ScheduledTask) -> bool:
    """Update an existing task. Returns True if found and updated."""
    tasks = load_tasks()
    for i, t in enumerate(tasks):
        if t.id == task.id:
            tasks[i] = task
            save_tasks(tasks)
            return True
    return False


def delete_task(task_id: str) -> bool:
    """Delete a task by ID. Returns True if found and deleted."""
    tasks = load_tasks()
    original_len = len(tasks)
    tasks = [t for t in tasks if t.id != task_id]
    if len(tasks) < original_len:
        save_tasks(tasks)
        return True
    return False


def get_task(task_id: str) -> Optional[ScheduledTask]:
    """Get a task by ID."""
    tasks = load_tasks()
    for t in tasks:
        if t.id == task_id:
            return t
    return None


def toggle_task(task_id: str) -> Optional[bool]:
    """Toggle a task's enabled state. Returns new state or None if not found."""
    task = get_task(task_id)
    if task:
        task.enabled = not task.enabled
        update_task(task)
        return task.enabled
    return None
