"""Commands API endpoints for slash command execution and autocomplete.

This router provides REST endpoints for:
- Listing all available slash commands
- Getting info about specific commands
- Executing slash commands
- Autocomplete suggestions for partial commands
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Thread pool for blocking command execution
_executor = ThreadPoolExecutor(max_workers=4)

# Timeout for command execution (seconds)
COMMAND_TIMEOUT = 30.0

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================


class CommandInfo(BaseModel):
    """Information about a registered command."""

    name: str
    description: str
    usage: str
    aliases: List[str] = []
    category: str = "core"
    detailed_help: Optional[str] = None


class CommandExecuteRequest(BaseModel):
    """Request to execute a slash command."""

    command: str  # Full command string, e.g., "/set model=gpt-4o"


class CommandExecuteResponse(BaseModel):
    """Response from executing a slash command."""

    success: bool
    result: Any = None
    error: Optional[str] = None


class AutocompleteRequest(BaseModel):
    """Request for command autocomplete."""

    partial: str  # Partial command string, e.g., "/se" or "/set mo"


class AutocompleteResponse(BaseModel):
    """Response with autocomplete suggestions."""

    suggestions: List[str]


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/")
async def list_commands() -> List[CommandInfo]:
    """List all available slash commands.

    Returns a sorted list of all unique commands (no alias duplicates),
    with their metadata including name, description, usage, aliases,
    category, and detailed help.

    Returns:
        List[CommandInfo]: Sorted list of command information.
    """
    from code_puppy.command_line.command_registry import get_unique_commands

    commands = []
    for cmd in get_unique_commands():
        commands.append(
            CommandInfo(
                name=cmd.name,
                description=cmd.description,
                usage=cmd.usage,
                aliases=cmd.aliases,
                category=cmd.category,
                detailed_help=cmd.detailed_help,
            )
        )
    return sorted(commands, key=lambda c: c.name)


@router.get("/{name}")
async def get_command_info(name: str) -> CommandInfo:
    """Get detailed info about a specific command.

    Looks up a command by name or alias (case-insensitive).

    Args:
        name: Command name or alias (without leading /).

    Returns:
        CommandInfo: Full command information.

    Raises:
        HTTPException: 404 if command not found.
    """
    from code_puppy.command_line.command_registry import get_command

    cmd = get_command(name)
    if not cmd:
        raise HTTPException(404, f"Command '/{name}' not found")

    return CommandInfo(
        name=cmd.name,
        description=cmd.description,
        usage=cmd.usage,
        aliases=cmd.aliases,
        category=cmd.category,
        detailed_help=cmd.detailed_help,
    )


@router.post("/execute")
async def execute_command(request: CommandExecuteRequest) -> CommandExecuteResponse:
    """Execute a slash command.

    Takes a command string (with or without leading /) and executes it
    using the command handler. Runs in a thread pool to avoid blocking
    the event loop, with a timeout to prevent hangs.

    Args:
        request: CommandExecuteRequest with the command to execute.

    Returns:
        CommandExecuteResponse: Result of command execution.
    """
    from code_puppy.command_line.command_handler import handle_command

    command = request.command
    if not command.startswith("/"):
        command = "/" + command

    loop = asyncio.get_running_loop()

    try:
        # Run blocking command in thread pool with timeout
        result = await asyncio.wait_for(
            loop.run_in_executor(_executor, handle_command, command),
            timeout=COMMAND_TIMEOUT,
        )
        return CommandExecuteResponse(success=True, result=result)
    except asyncio.TimeoutError:
        return CommandExecuteResponse(
            success=False, error=f"Command timed out after {COMMAND_TIMEOUT}s"
        )
    except Exception as e:
        return CommandExecuteResponse(success=False, error=str(e))


@router.post("/autocomplete")
async def autocomplete_command(request: AutocompleteRequest) -> AutocompleteResponse:
    """Get autocomplete suggestions for a partial command.

    Provides intelligent autocomplete based on partial input:
    - Empty input: returns all command names
    - Partial command name: returns matching commands and aliases
    - Complete command with args: returns usage hint

    Args:
        request: AutocompleteRequest with partial command string.

    Returns:
        AutocompleteResponse: List of autocomplete suggestions.
    """
    from code_puppy.command_line.command_registry import (
        get_command,
        get_unique_commands,
    )

    partial = request.partial.lstrip("/")

    # If empty, return all command names
    if not partial:
        suggestions = [f"/{cmd.name}" for cmd in get_unique_commands()]
        return AutocompleteResponse(suggestions=sorted(suggestions))

    # Split into command name and args
    parts = partial.split(maxsplit=1)
    cmd_partial = parts[0].lower()

    # If just the command name (no space yet), suggest matching commands
    if len(parts) == 1:
        suggestions = []
        for cmd in get_unique_commands():
            if cmd.name.startswith(cmd_partial):
                suggestions.append(f"/{cmd.name}")
            for alias in cmd.aliases:
                if alias.startswith(cmd_partial):
                    suggestions.append(f"/{alias}")
        return AutocompleteResponse(suggestions=sorted(set(suggestions)))

    # Command name complete, suggest based on command type
    # (For now, just return the command usage as a hint)
    cmd = get_command(cmd_partial)
    if cmd:
        return AutocompleteResponse(suggestions=[cmd.usage])

    return AutocompleteResponse(suggestions=[])
