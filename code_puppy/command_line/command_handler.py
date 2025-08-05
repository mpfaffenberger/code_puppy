import os

from code_puppy.command_line.model_picker_completion import (
    load_model_names,
    update_model_in_input,
)
from code_puppy.command_line.motd import print_motd
from code_puppy.command_line.utils import make_directory_table
from code_puppy.config import get_config_keys
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.tools.tools_content import tools_content

COMMANDS_HELP = """
[bold magenta]Commands Help[/bold magenta]
/help, /h             Show this help message
/cd <dir>             Change directory or show directories
/codemap <dir>        Show code structure for <dir>
/exit, /quit          Exit interactive mode
/generate-pr-description [@dir]  Generate comprehensive PR description
/m <model>            Set active model
/motd                 Show the latest message of the day (MOTD)
/show                 Show puppy config key-values
/set                  Set puppy config key-values
/tools                Show available tools and capabilities
/<unknown>            Show unknown command warning
"""


def handle_command(command: str):
    """
    Handle commands prefixed with '/'.

    Args:
        command: The command string to handle

    Returns:
        True if the command was handled, False if not, or a string to be processed as user input
    """
    command = command.strip()

    if command.strip().startswith("/motd"):
        print_motd(force=True)
        return True

    # /codemap (code structure visualization)
    if command.startswith("/codemap"):
        from code_puppy.tools.ts_code_map import make_code_map

        tokens = command.split()
        if len(tokens) > 1:
            target_dir = os.path.expanduser(tokens[1])
        else:
            target_dir = os.getcwd()
        try:
            make_code_map(target_dir, ignore_tests=True)
        except Exception as e:
            emit_error(f"Error generating code map: {e}")
        return True

    if command.startswith("/cd"):
        tokens = command.split()
        if len(tokens) == 1:
            try:
                table = make_directory_table()
                emit_info(table)
            except Exception as e:
                emit_error(f"Error listing directory: {e}")
            return True
        elif len(tokens) == 2:
            dirname = tokens[1]
            target = os.path.expanduser(dirname)
            if not os.path.isabs(target):
                target = os.path.join(os.getcwd(), target)
            if os.path.isdir(target):
                os.chdir(target)
                emit_success(f"Changed directory to: {target}")
            else:
                emit_error(f"Not a directory: {dirname}")
            return True

    if command.strip().startswith("/show"):
        from code_puppy.command_line.model_picker_completion import get_active_model
        from code_puppy.config import (
            get_message_history_limit,
            get_owner_name,
            get_puppy_name,
            get_yolo_mode,
        )

        puppy_name = get_puppy_name()
        owner_name = get_owner_name()
        model = get_active_model()
        yolo_mode = get_yolo_mode()
        msg_limit = get_message_history_limit()
        status_msg = f"""[bold magenta]🐶 Puppy Status[/bold magenta]

[bold]puppy_name:[/bold]     [cyan]{puppy_name}[/cyan]
[bold]owner_name:[/bold]     [cyan]{owner_name}[/cyan]
[bold]model:[/bold]          [green]{model}[/green]
[bold]YOLO_MODE:[/bold]      {"[red]ON[/red]" if yolo_mode else "[yellow]off[/yellow]"}
[bold]message_history_limit:[/bold]   Keeping last [cyan]{msg_limit}[/cyan] messages in context
"""
        emit_info(status_msg)
        return True

    if command.startswith("/set"):
        # Syntax: /set KEY=VALUE or /set KEY VALUE
        from code_puppy.config import set_config_value

        tokens = command.split(None, 2)
        argstr = command[len("/set") :].strip()
        key = None
        value = None
        if "=" in argstr:
            key, value = argstr.split("=", 1)
            key = key.strip()
            value = value.strip()
        elif len(tokens) >= 3:
            key = tokens[1]
            value = tokens[2]
        elif len(tokens) == 2:
            key = tokens[1]
            value = ""
        else:
            emit_warning(
                f"Usage: /set KEY=VALUE or /set KEY VALUE\nConfig keys: {', '.join(get_config_keys())}"
            )
            return True
        if key:
            set_config_value(key, value)
            emit_success(f'🌶 Set {key} = "{value}" in puppy.cfg!')
        else:
            emit_error("You must supply a key.")
        return True

    if command.startswith("/tools"):
        # Display the tools_content.py file content with markdown formatting
        from rich.markdown import Markdown

        markdown_content = Markdown(tools_content)
        emit_info(markdown_content)
        return True

    if command.startswith("/m"):
        # Try setting model and show confirmation
        new_input = update_model_in_input(command)
        if new_input is not None:
            from code_puppy.agent import get_code_generation_agent
            from code_puppy.command_line.model_picker_completion import get_active_model

            model = get_active_model()
            # Make sure this is called for the test
            get_code_generation_agent(force_reload=True)
            emit_success(f"Active model set and loaded: {model}")
            return True
        # If no model matched, show available models
        model_names = load_model_names()
        emit_warning("Usage: /m <model-name>")
        emit_warning(f"Available models: {', '.join(model_names)}")
        return True
    if command in ("/help", "/h"):
        emit_info(COMMANDS_HELP)
        return True

    if command.startswith("/generate-pr-description"):
        # Parse directory argument (e.g., /generate-pr-description @some/dir)
        tokens = command.split()
        directory_context = ""
        for t in tokens:
            if t.startswith("@"):
                directory_context = f" Please work in the directory: {t[1:]}"
                break

        # Hard-coded prompt from user requirements
        pr_prompt = f"""Generate a comprehensive PR description for my current branch changes. Follow these steps:

 1 Discover the changes: Use git CLI to find the base branch (usually main/master/develop) and get the list of changed files, commits, and diffs.
 2 Analyze the code: Read and analyze all modified files to understand:
    • What functionality was added/changed/removed
    • The technical approach and implementation details
    • Any architectural or design pattern changes
    • Dependencies added/removed/updated
 3 Generate a structured PR description with these sections:
    • Title: Concise, descriptive title (50 chars max)
    • Summary: Brief overview of what this PR accomplishes
    • Changes Made: Detailed bullet points of specific changes
    • Technical Details: Implementation approach, design decisions, patterns used
    • Files Modified: List of key files with brief description of changes
    • Testing: What was tested and how (if applicable)
    • Breaking Changes: Any breaking changes (if applicable)
    • Additional Notes: Any other relevant information
 4 Create a markdown file: Generate a PR_DESCRIPTION.md file with proper GitHub markdown formatting that I can directly copy-paste into GitHub's PR
   description field. Use proper markdown syntax with headers, bullet points, code blocks, and formatting.
 5 Make it review-ready: Ensure the description helps reviewers understand the context, approach, and impact of the changes.
6. If you have Github MCP, or gh cli is installed and authenticated to gecgithub01.walmart.com then find the PR for the branch we analyzed and update the PR description there and then delete the PR_DESCRIPTION.md file. (If you have a better name (title) for the PR, go ahead and update the title too.{directory_context}"""

        # Return the prompt to be processed by the main chat system
        return pr_prompt

    if command in ("/exit", "/quit"):
        emit_success("Goodbye!")
        # Signal to the main app that we want to exit
        # The actual exit handling is done in main.py
        return True
    if command.startswith("/"):
        name = command[1:].split()[0] if len(command) > 1 else ""
        if name:
            emit_warning(
                f"Unknown command: {command}\n[dim]Type /help for options.[/dim]"
            )
        else:
            # Show current model ONLY here
            from code_puppy.command_line.model_picker_completion import get_active_model

            current_model = get_active_model()
            emit_info(
                f"[bold green]Current Model:[/bold green] [cyan]{current_model}[/cyan]"
            )
        return True

    return False
