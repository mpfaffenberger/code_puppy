"""TUI-based wizard for creating scheduled tasks.

Provides interactive menus with arrow-key navigation for selecting
schedule type, agent, model, and other task parameters.
"""

from typing import List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from code_puppy.tools.command_runner import set_awaiting_user_input


class SelectionMenu:
    """Simple arrow-key selection menu."""

    def __init__(
        self, title: str, choices: List[str], descriptions: Optional[List[str]] = None
    ):
        self.title = title
        self.choices = choices
        self.descriptions = descriptions or [""] * len(choices)
        self.selected_idx = 0
        self.result: Optional[str] = None
        self.cancelled = False

    def _render(self) -> List:
        """Render the menu."""
        lines = []

        # Title
        lines.append(("bold fg:ansicyan", f"\n  {self.title}\n\n"))

        # Choices
        for i, choice in enumerate(self.choices):
            is_selected = i == self.selected_idx
            prefix = " ❯ " if is_selected else "   "

            if is_selected:
                lines.append(("bold fg:ansigreen", prefix))
                lines.append(("bold fg:ansigreen", f"{choice}"))
            else:
                lines.append(("", prefix))
                lines.append(("fg:ansibrightblack", f"{choice}"))

            # Show description for selected item
            if is_selected and self.descriptions[i]:
                lines.append(("fg:ansibrightblack", f"  - {self.descriptions[i]}"))

            lines.append(("", "\n"))

        # Help text
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ Navigate  "))
        lines.append(("fg:ansigreen", "Enter "))
        lines.append(("fg:ansibrightblack", "Select  "))
        lines.append(("fg:ansired", "Ctrl+C "))
        lines.append(("fg:ansibrightblack", "Cancel"))

        return lines

    def run(self) -> Optional[str]:
        """Run the selection menu. Returns selected choice or None if cancelled."""
        control = FormattedTextControl(text="")
        window = Window(content=control, wrap_lines=True)

        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _(event):
            if self.selected_idx > 0:
                self.selected_idx -= 1
            control.text = self._render()

        @kb.add("down")
        @kb.add("j")
        def _(event):
            if self.selected_idx < len(self.choices) - 1:
                self.selected_idx += 1
            control.text = self._render()

        @kb.add("enter")
        def _(event):
            self.result = self.choices[self.selected_idx]
            event.app.exit()

        @kb.add("c-c")
        @kb.add("escape")
        def _(event):
            self.cancelled = True
            event.app.exit()

        layout = Layout(window)
        app = Application(layout=layout, key_bindings=kb, full_screen=False)

        set_awaiting_user_input(True)
        try:
            control.text = self._render()
            app.run(in_thread=True)
        finally:
            set_awaiting_user_input(False)

        if self.cancelled:
            return None
        return self.result


class TextInputMenu:
    """Simple text input with TUI styling."""

    def __init__(self, title: str, default: str = "", placeholder: str = ""):
        self.title = title
        self.default = default
        self.placeholder = placeholder

    def run(self) -> Optional[str]:
        """Run text input. Returns entered text or None if cancelled."""
        from code_puppy.command_line.utils import safe_input

        try:
            prompt = f"  {self.title}"
            if self.default:
                prompt += f" [{self.default}]"
            prompt += ": "

            value = safe_input(prompt).strip()
            if not value and self.default:
                return self.default
            return value if value else None
        except (KeyboardInterrupt, EOFError):
            return None


class MultilineInputMenu:
    """Multi-line text input for prompts."""

    def __init__(self, title: str):
        self.title = title

    def run(self) -> Optional[str]:
        """Run multiline input. Returns entered text or None if cancelled."""
        from code_puppy.command_line.utils import safe_input

        print(f"\n  {self.title}")
        print("  (Enter an empty line to finish, Ctrl+C to cancel)\n")

        lines = []
        try:
            while True:
                line = safe_input("  > ")
                if not line:
                    break
                lines.append(line)
        except (KeyboardInterrupt, EOFError):
            print("\n  Cancelled.")
            return None

        return "\n".join(lines) if lines else None


def get_available_agents_list() -> List[Tuple[str, str]]:
    """Get list of available agents with descriptions."""
    try:
        from code_puppy.agents import get_agent_descriptions, get_available_agents

        agents = get_available_agents()
        descriptions = get_agent_descriptions()

        result = []
        for agent_name in sorted(agents.keys()):
            desc = descriptions.get(agent_name, agents.get(agent_name, ""))
            result.append((agent_name, desc))
        return result
    except Exception:
        return [("code-puppy", "Default agent")]


def get_available_models_list() -> List[str]:
    """Get list of available models."""
    try:
        from code_puppy.command_line.model_picker_completion import load_model_names

        models = load_model_names()
        return models if models else ["(default)"]
    except Exception:
        return ["(default)"]


def create_task_wizard() -> Optional[dict]:
    """Run the full task creation wizard.

    Returns:
        dict with task parameters, or None if cancelled.
    """
    print("\n" + "=" * 60)
    print("📅 CREATE NEW SCHEDULED TASK")
    print("=" * 60)

    # Step 1: Task Name
    name_input = TextInputMenu("Task name", placeholder="e.g., Daily Code Review")
    task_name = name_input.run()
    if not task_name:
        print("\n  ❌ Cancelled - task name required.")
        return None

    # Step 2: Schedule Type
    schedule_menu = SelectionMenu(
        "Select schedule type:",
        choices=[
            "Every 15 minutes",
            "Every 30 minutes",
            "Every hour",
            "Every 2 hours",
            "Every 6 hours",
            "Daily",
            "Custom interval...",
        ],
        descriptions=[
            "Run 4 times per hour",
            "Run twice per hour",
            "Run once per hour",
            "Run 12 times per day",
            "Run 4 times per day",
            "Run once per day",
            "Specify custom interval like 45m, 3h, 2d",
        ],
    )
    schedule_choice = schedule_menu.run()
    if not schedule_choice:
        print("\n  ❌ Cancelled.")
        return None

    # Map choice to schedule type and value
    schedule_map = {
        "Every 15 minutes": ("interval", "15m"),
        "Every 30 minutes": ("interval", "30m"),
        "Every hour": ("hourly", "1h"),
        "Every 2 hours": ("interval", "2h"),
        "Every 6 hours": ("interval", "6h"),
        "Daily": ("daily", "24h"),
    }

    if schedule_choice == "Custom interval...":
        interval_input = TextInputMenu(
            "Enter interval (e.g., 45m, 3h, 2d)", default="1h"
        )
        custom_interval = interval_input.run()
        if not custom_interval:
            print("\n  ❌ Cancelled.")
            return None
        schedule_type = "interval"
        schedule_value = custom_interval
    else:
        schedule_type, schedule_value = schedule_map[schedule_choice]

    # Step 3: Agent Selection
    agents = get_available_agents_list()
    agent_names = [a[0] for a in agents]
    agent_descs = [a[1] for a in agents]

    # Put code-puppy first if it exists
    if "code-puppy" in agent_names:
        idx = agent_names.index("code-puppy")
        agent_names.insert(0, agent_names.pop(idx))
        agent_descs.insert(0, agent_descs.pop(idx))

    agent_menu = SelectionMenu(
        "Select agent:", choices=agent_names, descriptions=agent_descs
    )
    selected_agent = agent_menu.run()
    if not selected_agent:
        print("\n  ❌ Cancelled.")
        return None

    # Step 4: Model Selection
    models = get_available_models_list()
    models.insert(0, "(use default model)")

    model_menu = SelectionMenu("Select model:", choices=models, descriptions=None)
    selected_model = model_menu.run()
    if selected_model is None:
        print("\n  ❌ Cancelled.")
        return None

    if selected_model == "(use default model)":
        selected_model = ""

    # Step 5: Prompt
    print()
    prompt_input = MultilineInputMenu("Enter the prompt for this task:")
    task_prompt = prompt_input.run()
    if not task_prompt:
        print("\n  ❌ Cancelled - prompt required.")
        return None

    # Step 6: Working Directory
    workdir_input = TextInputMenu(
        "Working directory", default=".", placeholder="current directory"
    )
    working_dir = workdir_input.run()
    if working_dir is None:
        print("\n  ❌ Cancelled.")
        return None

    # Summary
    print("\n" + "-" * 60)
    print("📋 TASK SUMMARY")
    print("-" * 60)
    print(f"  Name:      {task_name}")
    print(f"  Schedule:  {schedule_type} ({schedule_value})")
    print(f"  Agent:     {selected_agent}")
    print(f"  Model:     {selected_model or '(default)'}")
    print(f"  Directory: {working_dir}")
    print(f"  Prompt:    {task_prompt[:50]}{'...' if len(task_prompt) > 50 else ''}")
    print("-" * 60)

    # Confirm
    from code_puppy.command_line.utils import safe_input

    try:
        confirm = safe_input("\n  Create this task? (Y/n): ").strip().lower()
        if confirm and confirm not in ("y", "yes"):
            print("\n  ❌ Cancelled.")
            return None
    except (KeyboardInterrupt, EOFError):
        print("\n  ❌ Cancelled.")
        return None

    return {
        "name": task_name,
        "prompt": task_prompt,
        "agent": selected_agent,
        "model": selected_model,
        "schedule_type": schedule_type,
        "schedule_value": schedule_value,
        "working_directory": working_dir,
    }
