"""Scheduler plugin callbacks.

Registers the /scheduler command (and aliases /sched, /cron) via the
custom_command and custom_command_help callback hooks, keeping all
scheduler UI out of core puppy.
"""

from typing import Any, List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error, emit_info

_COMMAND_NAME = "scheduler"
_ALIASES = ("sched", "cron")
_DESCRIPTION = "Manage scheduled tasks – create, run, and monitor automated prompts"


def _scheduler_help() -> List[Tuple[str, str]]:
    """Return help entries for the scheduler commands."""
    return [
        (
            "scheduler",
            "Manage scheduled tasks – launch TUI or use sub-commands",
        ),
        ("sched", "Alias for /scheduler"),
        ("cron", "Alias for /scheduler"),
    ]


def _handle_scheduler_command(command: str, name: str) -> Optional[Any]:
    """Handle /scheduler, /sched, and /cron slash commands.

    Sub-commands:
        /scheduler         – Launch interactive TUI menu
        /scheduler start   – Start the scheduler daemon
        /scheduler stop    – Stop the scheduler daemon
        /scheduler status  – Show daemon status
        /scheduler list    – List all tasks
        /scheduler run <id>– Run a task immediately
    """
    if name not in (_COMMAND_NAME, *_ALIASES):
        return None

    from code_puppy.plugins.scheduler.scheduler_menu import show_scheduler_menu
    from code_puppy.scheduler.cli import (
        handle_scheduler_list,
        handle_scheduler_run,
        handle_scheduler_start,
        handle_scheduler_status,
        handle_scheduler_stop,
    )

    tokens = command.split()

    # Handle sub-commands
    if len(tokens) > 1:
        subcommand = tokens[1].lower()

        if subcommand == "start":
            handle_scheduler_start()
            return True
        elif subcommand == "stop":
            handle_scheduler_stop()
            return True
        elif subcommand == "status":
            handle_scheduler_status()
            return True
        elif subcommand == "list":
            handle_scheduler_list()
            return True
        elif subcommand == "run":
            if len(tokens) < 3:
                emit_error("Usage: /scheduler run <task_id>")
                return True
            handle_scheduler_run(tokens[2])
            return True
        else:
            emit_error(f"Unknown subcommand: {subcommand}")
            emit_info("Usage: /scheduler [start|stop|status|list|run <id>]")
            return True

    # No subcommand – launch TUI menu
    show_scheduler_menu()
    return True


register_callback("custom_command_help", _scheduler_help)
register_callback("custom_command", _handle_scheduler_command)
