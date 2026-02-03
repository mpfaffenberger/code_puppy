"""Task executor for the Code Puppy scheduler.

Handles executing scheduled tasks by invoking code-puppy CLI
with the configured prompt, model, and agent.
"""

import os
import subprocess
import sys
from datetime import datetime
from typing import Tuple

from code_puppy.scheduler.config import (
    SCHEDULER_LOG_DIR,
    ScheduledTask,
    update_task,
)


def get_code_puppy_command() -> str:
    """Get the path to the code-puppy executable."""
    # Try to find code-puppy in the same environment as this script
    if sys.platform == "win32":
        # On Windows, look for code-puppy.exe or use python -m
        return "code-puppy"
    else:
        # On Unix, code-puppy should be in PATH if installed
        return "code-puppy"


def execute_task(task: ScheduledTask) -> Tuple[bool, int, str]:
    """Execute a scheduled task.

    Args:
        task: The ScheduledTask to execute

    Returns:
        Tuple of (success: bool, exit_code: int, error_message: str)
    """
    # Ensure log directory exists
    os.makedirs(SCHEDULER_LOG_DIR, mode=0o700, exist_ok=True)

    # Build the command
    cmd = [get_code_puppy_command()]

    # Add prompt
    cmd.extend(["-p", task.prompt])

    # Add model if specified
    if task.model:
        cmd.extend(["--model", task.model])

    # Add agent if specified
    if task.agent:
        cmd.extend(["--agent", task.agent])

    # Determine working directory
    working_dir = task.working_directory
    if working_dir == "." or not working_dir:
        working_dir = os.getcwd()
    working_dir = os.path.expanduser(working_dir)

    # Validate working directory exists
    if not os.path.isdir(working_dir):
        error_msg = f"Working directory not found: {working_dir}"
        task.last_status = "failed"
        task.last_exit_code = -1
        update_task(task)
        return (False, -1, error_msg)

    # Ensure log file path
    log_file = task.log_file
    if not log_file:
        log_file = os.path.join(SCHEDULER_LOG_DIR, f"{task.id}.log")
    log_file = os.path.expanduser(log_file)

    # Ensure log file directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Update task status to running
    task.last_status = "running"
    task.last_run = datetime.now().isoformat()
    update_task(task)

    try:
        # Open log file for appending
        with open(log_file, "a") as log_f:
            # Write header
            log_f.write(f"\n{'=' * 60}\n")
            log_f.write(f"Task: {task.name} ({task.id})\n")
            log_f.write(f"Started: {datetime.now().isoformat()}\n")
            log_f.write(f"Command: {' '.join(cmd)}\n")
            log_f.write(f"Working Dir: {working_dir}\n")
            log_f.write(f"{'=' * 60}\n\n")
            log_f.flush()

            # Execute the command
            process = subprocess.Popen(
                cmd,
                cwd=working_dir,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                shell=False,
                env=os.environ.copy(),
            )

            # Wait for completion
            exit_code = process.wait()

            # Write footer
            log_f.write(f"\n{'=' * 60}\n")
            log_f.write(f"Finished: {datetime.now().isoformat()}\n")
            log_f.write(f"Exit Code: {exit_code}\n")
            log_f.write(f"{'=' * 60}\n")

        # Update task status
        task.last_status = "success" if exit_code == 0 else "failed"
        task.last_exit_code = exit_code
        update_task(task)

        return (exit_code == 0, exit_code, "")

    except FileNotFoundError as e:
        error_msg = f"code-puppy not found: {e}"
        task.last_status = "failed"
        task.last_exit_code = -1
        update_task(task)
        return (False, -1, error_msg)

    except Exception as e:
        error_msg = f"Execution error: {e}"
        task.last_status = "failed"
        task.last_exit_code = -1
        update_task(task)
        return (False, -1, error_msg)


def run_task_by_id(task_id: str) -> Tuple[bool, str]:
    """Run a task immediately by its ID.

    Returns:
        Tuple of (success: bool, message: str)
    """
    from code_puppy.scheduler.config import get_task

    task = get_task(task_id)
    if not task:
        return (False, f"Task not found: {task_id}")

    success, exit_code, error = execute_task(task)

    if success:
        return (True, f"Task '{task.name}' completed successfully")
    else:
        return (False, f"Task '{task.name}' failed (exit code: {exit_code}): {error}")
