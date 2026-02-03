"""Interactive TUI for managing scheduled tasks.

Launch with /scheduler to browse, create, edit, and manage scheduled prompts.
Built with prompt_toolkit for proper interactive split-panel interface.
"""

import os
import sys
import time
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.messaging import emit_error, emit_success, emit_warning
from code_puppy.scheduler.config import (
    ScheduledTask,
    add_task,
    delete_task,
    load_tasks,
    toggle_task,
)
from code_puppy.scheduler.daemon import (
    get_daemon_pid,
    start_daemon_background,
    stop_daemon,
)
from code_puppy.scheduler.executor import run_task_by_id
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 12


class SchedulerMenu:
    """Interactive TUI for managing scheduled tasks."""

    def __init__(self):
        """Initialize the scheduler menu."""
        self.tasks: List[ScheduledTask] = []
        self.selected_idx = 0
        self.current_page = 0
        self.result = None
        self.menu_control: Optional[FormattedTextControl] = None
        self.preview_control: Optional[FormattedTextControl] = None
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Refresh tasks from disk."""
        try:
            self.tasks = load_tasks()
        except Exception as e:
            emit_error(f"Failed to load tasks: {e}")
            self.tasks = []

    def _get_current_task(self) -> Optional[ScheduledTask]:
        """Get the currently selected task."""
        if 0 <= self.selected_idx < len(self.tasks):
            return self.tasks[self.selected_idx]
        return None

    def _get_status_icon(self, task: ScheduledTask) -> tuple:
        """Get status icon and color for a task."""
        if not task.enabled:
            return ("⏸", "fg:ansiyellow")
        if task.last_status == "running":
            return ("⏳", "fg:ansicyan")
        if task.last_status == "success":
            return ("✓", "fg:ansigreen")
        if task.last_status == "failed":
            return ("✗", "fg:ansired")
        return ("○", "fg:ansibrightblack")

    def _render_task_list(self) -> List:
        """Render the task list panel."""
        lines = []

        # Header with daemon status
        daemon_pid = get_daemon_pid()
        if daemon_pid:
            lines.append(
                ("fg:ansigreen bold", f" 🐕 Daemon: RUNNING (PID {daemon_pid})")
            )
        else:
            lines.append(("fg:ansired bold", " 🐕 Daemon: STOPPED"))
        lines.append(("", "\n\n"))

        if not self.tasks:
            lines.append(("fg:ansiyellow", "  No scheduled tasks.\n"))
            lines.append(("fg:ansibrightblack", "  Press 'n' to create one.\n"))
            self._render_navigation_hints(lines)
            return lines

        # Pagination
        total_pages = (len(self.tasks) + PAGE_SIZE - 1) // PAGE_SIZE
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, len(self.tasks))

        for i in range(start_idx, end_idx):
            task = self.tasks[i]
            is_selected = i == self.selected_idx
            icon, icon_color = self._get_status_icon(task)

            prefix = " > " if is_selected else "   "
            style = "bold" if is_selected else ""

            lines.append((style, prefix))
            lines.append((icon_color, icon))
            lines.append((style, f" {task.name[:25]}"))
            lines.append(("", "\n"))

        lines.append(("", "\n"))
        lines.append(
            ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}\n")
        )
        self._render_navigation_hints(lines)
        return lines

    def _render_navigation_hints(self, lines: List) -> None:
        """Render navigation hints."""
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ j/k "))
        lines.append(("", "Navigate  "))
        lines.append(("fg:ansibrightblack", "←/→ "))
        lines.append(("", "Page\n"))
        lines.append(("fg:ansigreen", "  Space "))
        lines.append(("", "Toggle  "))
        lines.append(("fg:ansicyan", "  n "))
        lines.append(("", "New Task\n"))
        lines.append(("fg:ansiyellow", "  r "))
        lines.append(("", "Run Now  "))
        lines.append(("fg:ansimagenta", "  t "))
        lines.append(("", "Tail Log\n"))
        lines.append(("fg:ansired", "  d "))
        lines.append(("", "Delete  "))
        lines.append(("fg:ansibrightblack", "  s "))
        lines.append(("", "Start/Stop Daemon\n"))
        lines.append(("fg:ansired", "  q "))
        lines.append(("", "Exit"))

    def _render_task_details(self) -> List:
        """Render the task details panel."""
        lines = []
        lines.append(("dim cyan", " TASK DETAILS\n\n"))

        task = self._get_current_task()
        if not task:
            lines.append(("fg:ansiyellow", "  No task selected.\n\n"))
            lines.append(("fg:ansibrightblack", "  Select a task or press 'n'\n"))
            lines.append(("fg:ansibrightblack", "  to create a new one."))
            return lines

        # Status
        icon, color = self._get_status_icon(task)
        status_text = "Enabled" if task.enabled else "Disabled"
        lines.append(("bold", "  Status: "))
        lines.append((color, f"{icon} {status_text}\n\n"))

        # Name
        lines.append(("bold", f"  {task.name}\n\n"))

        # Schedule
        lines.append(("bold", "  Schedule: "))
        lines.append(("", f"{task.schedule_type} ({task.schedule_value})\n\n"))

        # Agent & Model
        lines.append(("bold", "  Agent: "))
        lines.append(("fg:ansicyan", f"{task.agent}\n"))
        if task.model:
            lines.append(("bold", "  Model: "))
            lines.append(("fg:ansicyan", f"{task.model}\n"))
        lines.append(("", "\n"))

        # Prompt (truncated)
        lines.append(("bold", "  Prompt:\n"))
        prompt_preview = (
            task.prompt[:150] + "..." if len(task.prompt) > 150 else task.prompt
        )
        for line in prompt_preview.split("\n")[:4]:
            lines.append(("fg:ansibrightblack", f"    {line}\n"))
        lines.append(("", "\n"))

        # Last run
        if task.last_run:
            lines.append(("bold", "  Last Run: "))
            lines.append(("fg:ansibrightblack", f"{task.last_run[:19]}\n"))
            lines.append(("bold", "  Exit Code: "))
            code_color = "fg:ansigreen" if task.last_exit_code == 0 else "fg:ansired"
            lines.append((code_color, f"{task.last_exit_code}\n"))

        # Log file
        lines.append(("", "\n"))
        lines.append(("bold", "  Log: "))
        log_short = task.log_file[-40:] if len(task.log_file) > 40 else task.log_file
        lines.append(("fg:ansibrightblack", f"...{log_short}"))

        return lines

    def update_display(self) -> None:
        """Update the display."""
        if self.menu_control:
            self.menu_control.text = self._render_task_list()
        if self.preview_control:
            self.preview_control.text = self._render_task_details()

    def run(self) -> Optional[str]:
        """Run the interactive menu."""
        self.result = None
        self.menu_control = FormattedTextControl(text="")
        self.preview_control = FormattedTextControl(text="")

        menu_window = Window(
            content=self.menu_control, wrap_lines=True, width=Dimension(weight=40)
        )
        preview_window = Window(
            content=self.preview_control, wrap_lines=True, width=Dimension(weight=60)
        )
        menu_frame = Frame(menu_window, title="📅 Scheduled Tasks")
        preview_frame = Frame(preview_window, title="Details")
        root_container = VSplit([menu_frame, preview_frame])

        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _(event):
            if self.selected_idx > 0:
                self.selected_idx -= 1
                self.current_page = self.selected_idx // PAGE_SIZE
            self.update_display()

        @kb.add("down")
        @kb.add("j")
        def _(event):
            if self.selected_idx < len(self.tasks) - 1:
                self.selected_idx += 1
                self.current_page = self.selected_idx // PAGE_SIZE
            self.update_display()

        @kb.add("left")
        def _(event):
            if self.current_page > 0:
                self.current_page -= 1
                self.selected_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("right")
        def _(event):
            total_pages = (len(self.tasks) + PAGE_SIZE - 1) // PAGE_SIZE
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self.selected_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("space")
        def _(event):
            task = self._get_current_task()
            if task:
                toggle_task(task.id)
                self._refresh_data()
                self.result = "changed"
            self.update_display()

        @kb.add("n")
        def _(event):
            self.result = "new_task"
            event.app.exit()

        @kb.add("r")
        def _(event):
            self.result = "run_task"
            event.app.exit()

        @kb.add("t")
        def _(event):
            self.result = "tail_log"
            event.app.exit()

        @kb.add("d")
        def _(event):
            self.result = "delete_task"
            event.app.exit()

        @kb.add("s")
        def _(event):
            self.result = "toggle_daemon"
            event.app.exit()

        @kb.add("q")
        @kb.add("escape")
        def _(event):
            self.result = "quit"
            event.app.exit()

        @kb.add("c-c")
        def _(event):
            self.result = "quit"
            event.app.exit()

        layout = Layout(root_container)
        app = Application(
            layout=layout, key_bindings=kb, full_screen=False, mouse_support=False
        )

        set_awaiting_user_input(True)
        sys.stdout.write("\033[?1049h")  # Enter alternate buffer
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            self.update_display()
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            app.run(in_thread=True)
        finally:
            sys.stdout.write("\033[?1049l")  # Exit alternate buffer
            sys.stdout.flush()
            try:
                import termios

                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except (ImportError, Exception):
                pass
            time.sleep(0.1)
            set_awaiting_user_input(False)

        return self.result


def _create_new_task() -> Optional[ScheduledTask]:
    """Interactive TUI wizard to create a new task."""
    from code_puppy.command_line.scheduler_wizard import create_task_wizard

    result = create_task_wizard()
    if not result:
        return None

    return ScheduledTask(
        name=result["name"],
        prompt=result["prompt"],
        agent=result["agent"],
        model=result["model"],
        schedule_type=result["schedule_type"],
        schedule_value=result["schedule_value"],
        working_directory=result["working_directory"],
    )


def _tail_log_file(log_file: str) -> None:
    """Interactive log file viewer with proper keybindings."""
    import threading

    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    from code_puppy.command_line.utils import safe_input
    from code_puppy.tools.command_runner import set_awaiting_user_input

    if not os.path.exists(log_file):
        print(f"\n⚠️ Log file not found: {log_file}")
        safe_input("\nPress Enter to continue...")
        return

    # Read initial content
    try:
        with open(log_file, "r") as f:
            content = f.read()
            # Keep last 200 lines
            lines = content.split("\n")
            if len(lines) > 200:
                lines = lines[-200:]
            content = "\n".join(lines)
    except Exception as e:
        print(f"\n⚠️ Error reading log: {e}")
        safe_input("\nPress Enter to continue...")
        return

    # State
    log_content = [content]
    stop_tailing = [False]

    def render_log():
        lines = []
        lines.append(("bold fg:ansicyan", f"📄 Log: {log_file}\n"))
        lines.append(("fg:ansiyellow", "Press q, Esc, or d to close\n"))
        lines.append(("fg:ansibrightblack", "-" * 60 + "\n\n"))
        lines.append(("", log_content[0]))
        return lines

    control = FormattedTextControl(text=render_log)
    window = Window(content=control, wrap_lines=True)

    kb = KeyBindings()

    @kb.add("q")
    @kb.add("d")
    @kb.add("escape")
    @kb.add("c-c")
    def _(event):
        stop_tailing[0] = True
        event.app.exit()

    layout = Layout(window)
    app = Application(
        layout=layout, key_bindings=kb, full_screen=False, mouse_support=False
    )

    # Background thread to tail the file
    def tail_thread():
        try:
            with open(log_file, "r") as f:
                f.seek(0, 2)  # Go to end
                while not stop_tailing[0]:
                    line = f.readline()
                    if line:
                        log_content[0] += line
                        # Keep only last 200 lines
                        lines = log_content[0].split("\n")
                        if len(lines) > 200:
                            log_content[0] = "\n".join(lines[-200:])
                        try:
                            app.invalidate()
                        except Exception:
                            pass
                    else:
                        time.sleep(0.3)
        except Exception:
            pass

    # Start tail thread
    tailer = threading.Thread(target=tail_thread, daemon=True)
    tailer.start()

    set_awaiting_user_input(True)
    try:
        app.run(in_thread=True)
    finally:
        stop_tailing[0] = True
        set_awaiting_user_input(False)


def show_scheduler_menu() -> bool:
    """Launch the interactive scheduler TUI menu."""
    changes_made = False

    while True:
        menu = SchedulerMenu()
        result = menu.run()
        task = menu._get_current_task()

        if result == "new_task":
            new_task = _create_new_task()
            if new_task:
                add_task(new_task)
                emit_success(f"Created task: {new_task.name}")
                changes_made = True
            continue

        elif result == "run_task":
            if task:
                print(f"\n⏳ Running task: {task.name}...")
                success, msg = run_task_by_id(task.id)
                if success:
                    emit_success(msg)
                else:
                    emit_error(msg)
                from code_puppy.command_line.utils import safe_input

                safe_input("\nPress Enter to continue...")
                changes_made = True
            continue

        elif result == "tail_log":
            if task and task.log_file:
                _tail_log_file(task.log_file)
            continue

        elif result == "delete_task":
            if task:
                from code_puppy.command_line.utils import safe_input

                confirm = safe_input(f"\nDelete '{task.name}'? (y/N): ").strip().lower()
                if confirm in ("y", "yes"):
                    delete_task(task.id)
                    emit_warning(f"Deleted task: {task.name}")
                    changes_made = True
            continue

        elif result == "toggle_daemon":
            pid = get_daemon_pid()
            if pid:
                print("\n⏳ Stopping daemon...")
                if stop_daemon():
                    emit_success("Daemon stopped")
                else:
                    emit_error("Failed to stop daemon")
            else:
                print("\n⏳ Starting daemon in background...")
                if start_daemon_background():
                    emit_success("Daemon started")
                else:
                    emit_error("Failed to start daemon")
            from code_puppy.command_line.utils import safe_input

            safe_input("\nPress Enter to continue...")
            continue

        elif result == "changed":
            changes_made = True
            continue

        elif result == "quit":
            break
        else:
            break

    return changes_made
