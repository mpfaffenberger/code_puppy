"""CLI subcommands for the scheduler.

Handles command-line operations like starting/stopping the daemon,
listing tasks, and running tasks immediately.
"""

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning


def handle_scheduler_start() -> bool:
    """Start the scheduler daemon in background."""
    from code_puppy.scheduler.daemon import get_daemon_pid, start_daemon_background

    pid = get_daemon_pid()
    if pid:
        emit_warning(f"Scheduler daemon already running (PID {pid})")
        return True

    emit_info("Starting scheduler daemon...")

    if start_daemon_background():
        pid = get_daemon_pid()
        emit_success(f"Scheduler daemon started (PID {pid})")
        return True
    else:
        emit_error("Failed to start scheduler daemon")
        return False


def handle_scheduler_stop() -> bool:
    """Stop the scheduler daemon."""
    from code_puppy.scheduler.daemon import get_daemon_pid, stop_daemon

    pid = get_daemon_pid()
    if not pid:
        emit_info("Scheduler daemon is not running")
        return True

    emit_info(f"Stopping scheduler daemon (PID {pid})...")

    if stop_daemon():
        emit_success("Scheduler daemon stopped")
        return True
    else:
        emit_error("Failed to stop scheduler daemon")
        return False


def handle_scheduler_status() -> bool:
    """Show scheduler daemon status."""
    from code_puppy.scheduler.config import load_tasks
    from code_puppy.scheduler.daemon import get_daemon_pid

    pid = get_daemon_pid()
    if pid:
        emit_success(f"🐕 Scheduler daemon: RUNNING (PID {pid})")
    else:
        emit_warning("🐕 Scheduler daemon: STOPPED")

    tasks = load_tasks()
    enabled_count = sum(1 for t in tasks if t.enabled)

    emit_info(f"\n📅 Scheduled tasks: {len(tasks)} total, {enabled_count} enabled")

    if tasks:
        emit_info("\nTasks:")
        for task in tasks:
            status_icon = "🟢" if task.enabled else "🔴"
            last_run = task.last_run[:19] if task.last_run else "never"
            emit_info(
                f"  {status_icon} {task.name} ({task.schedule_type}: {task.schedule_value})"
            )
            emit_info(
                f"      Last run: {last_run}, Status: {task.last_status or 'pending'}"
            )

    return True


def handle_scheduler_list() -> bool:
    """List all scheduled tasks."""
    from code_puppy.scheduler.config import load_tasks

    tasks = load_tasks()

    if not tasks:
        emit_info("No scheduled tasks configured.")
        emit_info("Use '/scheduler' to create one.")
        return True

    emit_info(f"📅 Scheduled Tasks ({len(tasks)}):\n")

    for task in tasks:
        status = "🟢 enabled" if task.enabled else "🔴 disabled"
        emit_info(f"  [{task.id}] {task.name}")
        emit_info(f"      Status: {status}")
        emit_info(f"      Schedule: {task.schedule_type} ({task.schedule_value})")
        emit_info(f"      Agent: {task.agent}, Model: {task.model or 'default'}")
        if task.last_run:
            emit_info(f"      Last run: {task.last_run[:19]} ({task.last_status})")
        emit_info("")

    return True


def handle_scheduler_run(task_id: str) -> bool:
    """Run a specific task immediately."""
    from code_puppy.scheduler.executor import run_task_by_id

    emit_info(f"Running task {task_id}...")
    success, message = run_task_by_id(task_id)

    if success:
        emit_success(message)
    else:
        emit_error(message)

    return success
