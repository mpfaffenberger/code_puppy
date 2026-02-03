"""Scheduler tools for the Scheduler Agent.

These tools allow the scheduler agent to manage scheduled tasks,
control the daemon, and view logs.
"""

import os

from pydantic import Field

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.common import generate_group_id


def register_scheduler_list_tasks(agent):
    """Register the scheduler_list_tasks tool."""

    def scheduler_list_tasks() -> str:
        """List all scheduled tasks with their status and daemon info.

        Returns a formatted overview of:
        - Daemon status (running/stopped)
        - All configured tasks with their schedules
        - Last run status for each task
        """
        from code_puppy.scheduler import load_tasks
        from code_puppy.scheduler.daemon import get_daemon_pid

        group_id = generate_group_id("scheduler_list_tasks")
        emit_info("📅 SCHEDULER LIST TASKS", message_group=group_id)

        tasks = load_tasks()
        pid = get_daemon_pid()

        lines = []
        lines.append("## Scheduler Status")
        lines.append(
            f"**Daemon:** {'🟢 Running (PID ' + str(pid) + ')' if pid else '🔴 Stopped'}"
        )
        lines.append(f"**Total Tasks:** {len(tasks)}")
        lines.append("")

        if not tasks:
            lines.append("No scheduled tasks configured yet.")
            lines.append("")
            lines.append("Use `scheduler_create_task` to create one!")
            return "\n".join(lines)

        lines.append("## Tasks")
        lines.append("")

        for task in tasks:
            status_icon = "🟢" if task.enabled else "🔴"
            run_status = ""
            if task.last_status == "success":
                run_status = " ✅"
            elif task.last_status == "failed":
                run_status = " ❌"
            elif task.last_status == "running":
                run_status = " ⏳"

            lines.append(f"### {status_icon} {task.name} (`{task.id}`){run_status}")
            lines.append(
                f"- **Schedule:** {task.schedule_type} ({task.schedule_value})"
            )
            lines.append(f"- **Agent:** {task.agent}")
            lines.append(f"- **Model:** {task.model or '(default)'}")
            lines.append(
                f"- **Prompt:** {task.prompt[:100]}{'...' if len(task.prompt) > 100 else ''}"
            )
            lines.append(f"- **Directory:** {task.working_directory}")
            if task.last_run:
                lines.append(
                    f"- **Last Run:** {task.last_run[:19]} (exit code: {task.last_exit_code})"
                )
            lines.append("")

        return "\n".join(lines)

    agent.tool_plain(scheduler_list_tasks)


def register_scheduler_create_task(agent):
    """Register the scheduler_create_task tool."""

    def scheduler_create_task(
        name: str = Field(description="Human-readable name for the task"),
        prompt: str = Field(description="The prompt to execute"),
        agent: str = Field(
            default="code-puppy",
            description="Agent to use (e.g., code-puppy, code-reviewer, security-auditor)",
        ),
        model: str = Field(
            default="", description="Model to use (empty string for default)"
        ),
        schedule_type: str = Field(
            default="interval",
            description="Schedule type: 'interval', 'hourly', or 'daily'",
        ),
        schedule_value: str = Field(
            default="1h",
            description="Schedule value (e.g., '30m', '2h', '1d' for intervals)",
        ),
        working_directory: str = Field(
            default=".", description="Working directory for the task"
        ),
    ) -> str:
        """Create a new scheduled task.

        Creates a task that will run automatically according to the specified schedule.
        The daemon must be running for tasks to execute.
        """
        from code_puppy.scheduler import ScheduledTask, add_task
        from code_puppy.scheduler.daemon import get_daemon_pid

        group_id = generate_group_id("scheduler_create_task", name)
        emit_info(f"📅 SCHEDULER CREATE TASK → {name}", message_group=group_id)

        task = ScheduledTask(
            name=name,
            prompt=prompt,
            agent=agent,
            model=model,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            working_directory=working_directory,
        )

        add_task(task)
        emit_success(f"Created task: {name} ({task.id})", message_group=group_id)

        result = f"""✅ **Task Created Successfully!**

**ID:** `{task.id}`
**Name:** {task.name}
**Schedule:** {task.schedule_type} ({task.schedule_value})
**Agent:** {task.agent}
**Model:** {task.model or "(default)"}
**Directory:** {task.working_directory}
**Log File:** `{task.log_file}`

**Prompt:**
```
{task.prompt}
```
"""

        pid = get_daemon_pid()
        if not pid:
            result += "\n⚠️ **Note:** The scheduler daemon is not running. Use `scheduler_start_daemon` to start it!"
        else:
            result += f"\n🟢 Daemon is running (PID {pid}). Task will execute according to schedule."

        return result

    agent.tool_plain(scheduler_create_task)


def register_scheduler_delete_task(agent):
    """Register the scheduler_delete_task tool."""

    def scheduler_delete_task(
        task_id: str = Field(description="The ID of the task to delete"),
    ) -> str:
        """Delete a scheduled task by its ID.

        Permanently removes the task from the schedule.
        The task's log file is NOT deleted.
        """
        from code_puppy.scheduler import delete_task, get_task

        group_id = generate_group_id("scheduler_delete_task", task_id)
        emit_info(f"📅 SCHEDULER DELETE TASK → {task_id}", message_group=group_id)

        task = get_task(task_id)
        if not task:
            emit_warning(f"Task not found: {task_id}", message_group=group_id)
            return f"❌ Task not found: `{task_id}`"

        task_name = task.name
        if delete_task(task_id):
            emit_success(f"Deleted task: {task_name}", message_group=group_id)
            return f"✅ Deleted task: **{task_name}** (`{task_id}`)"
        else:
            return f"❌ Failed to delete task: `{task_id}`"

    agent.tool_plain(scheduler_delete_task)


def register_scheduler_toggle_task(agent):
    """Register the scheduler_toggle_task tool."""

    def scheduler_toggle_task(
        task_id: str = Field(description="The ID of the task to enable/disable"),
    ) -> str:
        """Toggle a task's enabled/disabled state.

        Disabled tasks remain in the schedule but won't run until re-enabled.
        """
        from code_puppy.scheduler import get_task, toggle_task

        group_id = generate_group_id("scheduler_toggle_task", task_id)
        emit_info(f"📅 SCHEDULER TOGGLE TASK → {task_id}", message_group=group_id)

        task = get_task(task_id)
        if not task:
            emit_warning(f"Task not found: {task_id}", message_group=group_id)
            return f"❌ Task not found: `{task_id}`"

        task_name = task.name
        new_state = toggle_task(task_id)

        if new_state is None:
            return f"❌ Failed to toggle task: `{task_id}`"

        status = "🟢 **Enabled**" if new_state else "🔴 **Disabled**"
        status_msg = "enabled" if new_state else "disabled"
        emit_success(f"Task {task_name} {status_msg}", message_group=group_id)
        return f"Task **{task_name}** (`{task_id}`) is now {status}"

    agent.tool_plain(scheduler_toggle_task)


def register_scheduler_daemon_status(agent):
    """Register the scheduler_daemon_status tool."""

    def scheduler_daemon_status() -> str:
        """Check if the scheduler daemon is running.

        Returns detailed status including PID and task counts.
        """
        from code_puppy.scheduler import load_tasks
        from code_puppy.scheduler.daemon import get_daemon_pid

        group_id = generate_group_id("scheduler_daemon_status")
        emit_info("📅 SCHEDULER DAEMON STATUS", message_group=group_id)

        pid = get_daemon_pid()
        tasks = load_tasks()
        enabled_count = sum(1 for t in tasks if t.enabled)

        if pid:
            return f"""🟢 **Daemon is RUNNING**

**PID:** {pid}
**Total Tasks:** {len(tasks)}
**Enabled Tasks:** {enabled_count}

The scheduler is actively monitoring and running tasks according to their schedules."""
        else:
            return f"""🔴 **Daemon is STOPPED**

**Total Tasks:** {len(tasks)}
**Enabled Tasks:** {enabled_count}

The scheduler daemon is not running. Scheduled tasks will NOT execute until you start it.

Use `scheduler_start_daemon` to start the daemon."""

    agent.tool_plain(scheduler_daemon_status)


def register_scheduler_start_daemon(agent):
    """Register the scheduler_start_daemon tool."""

    def scheduler_start_daemon() -> str:
        """Start the scheduler daemon in the background.

        The daemon runs independently and will continue even after
        Code Puppy exits. It checks for and runs scheduled tasks.
        """
        from code_puppy.scheduler.daemon import get_daemon_pid, start_daemon_background

        group_id = generate_group_id("scheduler_start_daemon")
        emit_info("📅 SCHEDULER START DAEMON", message_group=group_id)

        pid = get_daemon_pid()
        if pid:
            emit_warning(f"Daemon already running (PID {pid})", message_group=group_id)
            return f"ℹ️ Daemon is already running (PID {pid})"

        if start_daemon_background():
            new_pid = get_daemon_pid()
            emit_success(f"Daemon started (PID {new_pid})", message_group=group_id)
            return f"✅ **Daemon started successfully!** (PID {new_pid})\n\nScheduled tasks will now run automatically."
        else:
            emit_warning("Failed to start daemon", message_group=group_id)
            return "❌ **Failed to start daemon.** Check the logs for errors."

    agent.tool_plain(scheduler_start_daemon)


def register_scheduler_stop_daemon(agent):
    """Register the scheduler_stop_daemon tool."""

    def scheduler_stop_daemon() -> str:
        """Stop the scheduler daemon.

        Stops the background process. No scheduled tasks will run
        until the daemon is started again.
        """
        from code_puppy.scheduler.daemon import get_daemon_pid, stop_daemon

        group_id = generate_group_id("scheduler_stop_daemon")
        emit_info("📅 SCHEDULER STOP DAEMON", message_group=group_id)

        pid = get_daemon_pid()
        if not pid:
            emit_warning("Daemon is not running", message_group=group_id)
            return "ℹ️ Daemon is not running."

        if stop_daemon():
            emit_success(f"Daemon stopped (was PID {pid})", message_group=group_id)
            return f"✅ **Daemon stopped.** (was PID {pid})\n\nScheduled tasks will NOT run until you start the daemon again."
        else:
            emit_warning(f"Failed to stop daemon (PID {pid})", message_group=group_id)
            return f"❌ **Failed to stop daemon** (PID {pid}). You may need to kill it manually."

    agent.tool_plain(scheduler_stop_daemon)


def register_scheduler_run_task(agent):
    """Register the scheduler_run_task tool."""

    def scheduler_run_task(
        task_id: str = Field(description="The ID of the task to run immediately"),
    ) -> str:
        """Run a scheduled task immediately.

        Executes the task right now, regardless of its schedule.
        Useful for testing or one-off runs.
        """
        from code_puppy.scheduler import get_task
        from code_puppy.scheduler.executor import run_task_by_id

        group_id = generate_group_id("scheduler_run_task", task_id)
        emit_info(f"📅 SCHEDULER RUN TASK → {task_id}", message_group=group_id)

        task = get_task(task_id)
        if not task:
            emit_warning(f"Task not found: {task_id}", message_group=group_id)
            return f"❌ Task not found: `{task_id}`"

        emit_info(f"Running: {task.name}...", message_group=group_id)
        result = f"⏳ Running task **{task.name}** (`{task_id}`)...\n\n"

        success, message = run_task_by_id(task_id)

        if success:
            emit_success(f"Task completed: {task.name}", message_group=group_id)
            result += f"✅ **Task completed successfully!**\n\n{message}\n\nView the log with `scheduler_view_log`."
        else:
            emit_warning(f"Task failed: {task.name}", message_group=group_id)
            result += f"❌ **Task failed.**\n\n{message}\n\nCheck the log with `scheduler_view_log` for details."

        return result

    agent.tool_plain(scheduler_run_task)


def register_scheduler_view_log(agent):
    """Register the scheduler_view_log tool."""

    def scheduler_view_log(
        task_id: str = Field(description="The ID of the task whose log to view"),
        lines: int = Field(
            default=50, description="Number of lines to show from the end of the log"
        ),
    ) -> str:
        """View the log file for a scheduled task.

        Shows the most recent output from task executions.
        Each run appends to the log file.
        """
        from code_puppy.scheduler import get_task

        group_id = generate_group_id("scheduler_view_log", task_id)
        emit_info(
            f"📅 SCHEDULER VIEW LOG → {task_id} (last {lines} lines)",
            message_group=group_id,
        )

        task = get_task(task_id)
        if not task:
            emit_warning(f"Task not found: {task_id}", message_group=group_id)
            return f"❌ Task not found: `{task_id}`"

        log_file = task.log_file
        if not os.path.exists(log_file):
            return f"📄 **No log file yet for task:** {task.name} (`{task_id}`)\n\nThe log will be created when the task runs for the first time."

        try:
            with open(log_file, "r") as f:
                content = f.read()

            log_lines = content.split("\n")
            if len(log_lines) > lines:
                log_lines = log_lines[-lines:]

            truncated_content = "\n".join(log_lines)

            return f"""📄 **Log for task:** {task.name} (`{task_id}`)
**File:** `{log_file}`
**Showing:** last {lines} lines

```
{truncated_content}
```"""
        except Exception as e:
            return f"❌ Error reading log file: {e}"

    agent.tool_plain(scheduler_view_log)
