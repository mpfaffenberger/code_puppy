"""Code Puppy Scheduler - Run scheduled prompts automatically.

This module provides a cross-platform scheduler daemon that executes
Code Puppy prompts on configurable schedules (intervals, cron expressions).

Components:
    - config: Task definitions and JSON persistence
    - daemon: Background scheduler process
    - executor: Task execution logic
    - platform: Cross-platform daemon management
"""

from code_puppy.scheduler.config import (
    SCHEDULER_LOG_DIR,
    SCHEDULER_PID_FILE,
    SCHEDULES_FILE,
    ScheduledTask,
    add_task,
    delete_task,
    get_task,
    load_tasks,
    save_tasks,
    toggle_task,
    update_task,
)
from code_puppy.scheduler.daemon import start_daemon_background

__all__ = [
    "ScheduledTask",
    "load_tasks",
    "save_tasks",
    "add_task",
    "update_task",
    "delete_task",
    "get_task",
    "toggle_task",
    "start_daemon_background",
    "SCHEDULES_FILE",
    "SCHEDULER_PID_FILE",
    "SCHEDULER_LOG_DIR",
]
