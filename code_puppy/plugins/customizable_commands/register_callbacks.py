from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error, emit_info

# Global cache for loaded commands
_custom_commands: Dict[str, str] = {}
_command_descriptions: Dict[str, str] = {}
_commands_loaded: bool = False  # Sentinel to track if commands have been loaded

# Directories to scan for commands (in priority order - later directories override earlier)
_COMMAND_DIRECTORIES = [
    "~/.code-puppy/commands",  # Global commands (all projects)
    ".claude/commands",
    ".github/prompts",
    ".agents/commands",
]


class MarkdownCommandResult:
    """Special marker for markdown command results that should be processed as input."""

    def __init__(self, content: str):
        self.content = content

    def __str__(self) -> str:
        return self.content

    def __repr__(self) -> str:
        return f"MarkdownCommandResult({len(self.content)} chars)"


def _load_markdown_commands() -> None:
    """Load markdown command files from the configured directories.

    Scans for *.md files in the configured directories and loads them
    as custom commands. Later directories override earlier ones with the
    same command name (project commands override global).
    """
    global _custom_commands, _command_descriptions, _commands_loaded

    _custom_commands.clear()
    _command_descriptions.clear()
    _commands_loaded = True  # Mark as loaded even if directories are empty

    # Process directories in order - later directories override earlier ones
    for directory in _COMMAND_DIRECTORIES:
        dir_path = Path(directory).expanduser()
        if not dir_path.exists():
            continue

        # Look for markdown files
        pattern = "*.md" if directory != ".github/prompts" else "*.prompt.md"
        # Sort within directory for consistent ordering
        md_files = sorted(dir_path.glob(pattern))

        for md_file in md_files:
            try:
                # Extract command name from filename
                if md_file.name.endswith(".prompt.md"):
                    base_name = md_file.name[: -len(".prompt.md")]
                else:
                    base_name = md_file.stem

                # Read file content
                content = md_file.read_text(encoding="utf-8").strip()
                if not content:
                    continue

                # Extract first line as description (or use filename)
                lines = content.split("\n")
                description = base_name.replace("_", " ").replace("-", " ").title()

                # Try to get description from first non-empty line that's not a heading
                for line in lines:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        # Truncate long descriptions
                        description = stripped[:50] + (
                            "..." if len(stripped) > 50 else ""
                        )
                        break

                # Later directories override earlier ones (project > global)
                _custom_commands[base_name] = content
                _command_descriptions[base_name] = description

            except Exception as e:
                emit_error(f"Failed to load command from {md_file}: {e}")


def _custom_help() -> List[Tuple[str, str]]:
    """Return help entries for loaded markdown commands."""
    # Reload commands to pick up any changes
    _load_markdown_commands()

    help_entries = []
    for name, description in sorted(_command_descriptions.items()):
        help_entries.append((name, f"Execute markdown command: {description}"))

    return help_entries


def _handle_custom_command(command: str, name: str) -> Optional[Any]:
    """Handle a markdown-based custom command.

    Args:
        command: The full command string
        name: The command name without leading slash

    Returns:
        MarkdownCommandResult with content to be processed as input,
        or None if not found
    """
    if not name:
        return None

    # Ensure commands are loaded (use sentinel, not dict emptiness)
    if not _commands_loaded:
        _load_markdown_commands()

    # Look up the command
    content = _custom_commands.get(name)
    if content is None:
        return None

    # Extract any additional arguments from the command
    parts = command.split(maxsplit=1)
    args = parts[1] if len(parts) > 1 else ""

    # If there are arguments, append them to the prompt
    if args:
        prompt = f"{content}\n\nAdditional context: {args}"
    else:
        prompt = content

    # Emit info message and return the special marker
    emit_info(f"📝 Executing markdown command: {name}")
    return MarkdownCommandResult(prompt)


# Register callbacks
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)

# Make the result class available for the command handler
# Import this in command_handler.py to check for this type
__all__ = ["MarkdownCommandResult"]

# Load commands at import time
_load_markdown_commands()
