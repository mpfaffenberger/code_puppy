"""Command registry for dynamic command discovery.

This module provides a decorator-based registration system for commands,
enabling automatic help generation and eliminating static command lists.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class CommandInfo:
    """Metadata for a registered command."""

    name: str
    description: str
    handler: Callable[[str], bool]
    usage: str = ""
    aliases: List[str] = field(default_factory=list)
    category: str = "core"
    detailed_help: Optional[str] = None

    def __post_init__(self):
        """Set default usage if not provided."""
        if not self.usage:
            self.usage = f"/{self.name}"


# Global registry: maps command name/alias -> CommandInfo
_COMMAND_REGISTRY: Dict[str, CommandInfo] = {}


def register_command(
    name: str,
    description: str,
    usage: str = "",
    aliases: Optional[List[str]] = None,
    category: str = "core",
    detailed_help: Optional[str] = None,
):
    """Decorator to register a command handler.

    This decorator registers a command function so it can be:
    - Auto-discovered by the help system
    - Invoked by handle_command() dynamically
    - Grouped by category
    - Documented with aliases and detailed help

    Args:
        name: Primary command name (without leading /)
        description: Short one-line description for help text
        usage: Full usage string (e.g., "/cd <dir>"). Defaults to "/{name}"
        aliases: List of alternative names (without leading /)
        category: Grouping category ("core", "session", "config", etc.)
        detailed_help: Optional detailed help text for /help <command>

    Example:
        >>> @register_command(
        ...     name="session",
        ...     description="Show or rotate autosave session ID",
        ...     usage="/session [id|new]",
        ...     aliases=["s"],
        ...     category="session",
        ... )
        ... def handle_session(command: str) -> bool:
        ...     return True

    Returns:
        The decorated function, unchanged
    """

    def decorator(func: Callable[[str], bool]) -> Callable[[str], bool]:
        # Create CommandInfo instance
        cmd_info = CommandInfo(
            name=name,
            description=description,
            handler=func,
            usage=usage,
            aliases=aliases or [],
            category=category,
            detailed_help=detailed_help,
        )

        # Register primary name
        _COMMAND_REGISTRY[name] = cmd_info

        # Register all aliases pointing to the same CommandInfo
        for alias in aliases or []:
            _COMMAND_REGISTRY[alias] = cmd_info

        return func

    return decorator


def get_all_commands() -> Dict[str, CommandInfo]:
    """Get all registered commands.

    Returns:
        Dictionary mapping command names/aliases to CommandInfo objects.
        Note: Aliases point to the same CommandInfo as their primary command.
    """
    return _COMMAND_REGISTRY.copy()


def get_unique_commands() -> List[CommandInfo]:
    """Get unique registered commands (no duplicates from aliases).

    Returns:
        List of unique CommandInfo objects (one per primary command).
    """
    seen = set()
    unique = []
    for cmd_info in _COMMAND_REGISTRY.values():
        # Use object id to avoid duplicates from aliases
        if id(cmd_info) not in seen:
            seen.add(id(cmd_info))
            unique.append(cmd_info)
    return unique


def get_command(name: str) -> Optional[CommandInfo]:
    """Get command info by name or alias (case-insensitive).

    First tries exact match for backward compatibility, then falls back to
    case-insensitive matching.

    Args:
        name: Command name or alias (without leading /)

    Returns:
        CommandInfo if found, None otherwise
    """
    # First try exact match (for backward compatibility)
    exact_match = _COMMAND_REGISTRY.get(name)
    if exact_match is not None:
        return exact_match

    # If no exact match, try case-insensitive matching
    name_lower = name.lower()
    for registered_name, cmd_info in _COMMAND_REGISTRY.items():
        if registered_name.lower() == name_lower:
            return cmd_info

    return None


def clear_registry():
    """Clear all registered commands. Useful for testing."""
    _COMMAND_REGISTRY.clear()
