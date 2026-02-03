"""Scheduler daemon for Code Puppy.

Runs as a background process, checking for and executing scheduled tasks.
Uses pure Python timing (no external scheduler dependencies).
"""

import atexit
import os
import re
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

from code_puppy.scheduler.config import (
    SCHEDULER_PID_FILE,
    ScheduledTask,
    load_tasks,
)
from code_puppy.scheduler.executor import execute_task

# Global flag for graceful shutdown
_shutdown_requested = False


def parse_interval(interval_str: str) -> Optional[timedelta]:
    """Parse interval string like '30m', '1h', '2d' into timedelta."""
    match = re.match(r"^(\d+)([smhd])$", interval_str.lower())
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "s":
        return timedelta(seconds=value)
    elif unit == "m":
        return timedelta(minutes=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    return None


def should_run_task(task: ScheduledTask, now: datetime) -> bool:
    """Determine if a task should run now based on its schedule."""
    if not task.enabled:
        return False

    if task.schedule_type == "interval":
        interval = parse_interval(task.schedule_value)
        if not interval:
            return False

        if not task.last_run:
            return True  # Never run before

        last_run = datetime.fromisoformat(task.last_run)
        return (now - last_run) >= interval

    elif task.schedule_type == "hourly":
        if not task.last_run:
            return True
        last_run = datetime.fromisoformat(task.last_run)
        return (now - last_run) >= timedelta(hours=1)

    elif task.schedule_type == "daily":
        if not task.last_run:
            return True
        last_run = datetime.fromisoformat(task.last_run)
        return (now - last_run) >= timedelta(days=1)

    elif task.schedule_type == "cron":
        # Cron expressions not yet supported - would need croniter library
        # Log warning so users know why task isn't running
        print(
            f"[Scheduler] Warning: Cron schedules not yet supported, skipping: {task.name}"
        )
        return False

    return False


def run_scheduler_loop(check_interval: int = 60):
    """Main scheduler loop. Checks tasks every `check_interval` seconds."""
    global _shutdown_requested

    print(f"[Scheduler] Starting daemon (PID: {os.getpid()})")
    print(f"[Scheduler] Check interval: {check_interval}s")

    while not _shutdown_requested:
        try:
            tasks = load_tasks()
            now = datetime.now()

            for task in tasks:
                if _shutdown_requested:
                    break

                if should_run_task(task, now):
                    print(f"[Scheduler] Running task: {task.name} ({task.id})")
                    success, exit_code, error = execute_task(task)
                    if success:
                        print(f"[Scheduler] Task completed: {task.name}")
                    else:
                        print(f"[Scheduler] Task failed: {task.name} - {error}")

            # Sleep in small increments to allow graceful shutdown
            for _ in range(check_interval):
                if _shutdown_requested:
                    break
                time.sleep(1)

        except Exception as e:
            print(f"[Scheduler] Error in loop: {e}")
            time.sleep(10)  # Wait before retrying

    print("[Scheduler] Daemon stopped")


def write_pid_file():
    """Write the current PID to the PID file."""
    os.makedirs(os.path.dirname(SCHEDULER_PID_FILE), exist_ok=True)
    with open(SCHEDULER_PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid_file():
    """Remove the PID file."""
    try:
        if os.path.exists(SCHEDULER_PID_FILE):
            os.remove(SCHEDULER_PID_FILE)
    except OSError:
        pass


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global _shutdown_requested
    print(f"\n[Scheduler] Received signal {signum}, shutting down...")
    _shutdown_requested = True


def start_daemon(foreground: bool = False):
    """Start the scheduler daemon.

    Args:
        foreground: If True, run in foreground. If False, daemonize.
    """
    global _shutdown_requested
    _shutdown_requested = False

    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Write PID file and register cleanup
    write_pid_file()
    atexit.register(remove_pid_file)

    # Run the scheduler loop
    run_scheduler_loop()


def get_daemon_pid() -> Optional[int]:
    """Get the PID of the running daemon, or None if not running."""
    if not os.path.exists(SCHEDULER_PID_FILE):
        return None

    try:
        with open(SCHEDULER_PID_FILE, "r") as f:
            pid = int(f.read().strip())

        # Check if process is actually running
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(
                0x1000, False, pid
            )  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return pid
            return None
        else:
            os.kill(pid, 0)  # Doesn't kill, just checks if process exists
            return pid
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        # PID file exists but process is not running - stale PID file
        remove_pid_file()
        return None


def start_daemon_background() -> bool:
    """Start the scheduler daemon in the background.

    Returns:
        True if daemon started successfully, False otherwise.
    """
    import subprocess
    import time

    pid = get_daemon_pid()
    if pid:
        return True  # Already running

    cmd = [sys.executable, "-m", "code_puppy.scheduler"]

    if sys.platform == "win32":
        subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.Popen(
            cmd,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    time.sleep(1)
    return get_daemon_pid() is not None


def stop_daemon() -> bool:
    """Stop the running daemon. Returns True if stopped successfully."""
    pid = get_daemon_pid()
    if not pid:
        return False

    try:
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, False, pid)  # PROCESS_TERMINATE
            kernel32.TerminateProcess(handle, 0)
            kernel32.CloseHandle(handle)
        else:
            os.kill(pid, signal.SIGTERM)

        # Wait for process to stop
        for _ in range(10):
            time.sleep(0.5)
            if not get_daemon_pid():
                return True

        return False
    except Exception:
        return False
