"""
MCP Command Handler - Main router for MCP server management commands.

This module provides the MCPCommandHandler class that routes MCP commands
to their respective command modules.
"""

import logging
import shlex

from code_puppy.messaging import emit_info

from .add_command import AddCommand
from .base import MCPCommandBase
from .help_command import HelpCommand
from .install_command import InstallCommand

# Import all command modules
from .list_command import ListCommand
from .logs_command import LogsCommand
from .remove_command import RemoveCommand
from .restart_command import RestartCommand
from .search_command import SearchCommand
from .start_all_command import StartAllCommand
from .start_command import StartCommand
from .status_command import StatusCommand
from .stop_all_command import StopAllCommand
from .stop_command import StopCommand
from .test_command import TestCommand

# Configure logging
logger = logging.getLogger(__name__)


class MCPCommandHandler(MCPCommandBase):
    """
    Main command handler for MCP server management operations.

    Routes MCP commands to their respective command modules.
    Each command is implemented in its own module for better maintainability.

    Example usage:
        handler = MCPCommandHandler()
        handler.handle_mcp_command("/mcp list")
        handler.handle_mcp_command("/mcp start filesystem")
        handler.handle_mcp_command("/mcp status filesystem")
    """

    def __init__(self):
        """Initialize the MCP command handler."""
        super().__init__()

        # Initialize command handlers
        self._commands = {
            "list": ListCommand(),
            "start": StartCommand(),
            "start-all": StartAllCommand(),
            "stop": StopCommand(),
            "stop-all": StopAllCommand(),
            "restart": RestartCommand(),
            "status": StatusCommand(),
            "test": TestCommand(),
            "add": AddCommand(),
            "remove": RemoveCommand(),
            "logs": LogsCommand(),
            "search": SearchCommand(),
            "install": InstallCommand(),
            "help": HelpCommand(),
        }

        logger.info("MCPCommandHandler initialized with all command modules")

    def handle_mcp_command(self, command: str) -> bool:
        """
        Handle MCP commands and route to appropriate handler.

        Args:
            command: The full command string (e.g., "/mcp list", "/mcp start server")

        Returns:
            True if command was handled successfully, False otherwise
        """
        group_id = self.generate_group_id()

        try:
            # Remove /mcp prefix and parse arguments
            command = command.strip()
            if not command.startswith("/mcp"):
                return False

            # Remove the /mcp prefix
            args_str = command[4:].strip()

            # If no subcommand, show status dashboard
            if not args_str:
                self._commands["list"].execute([], group_id=group_id)
                return True

            # Parse arguments using shlex for proper handling of quoted strings
            try:
                args = shlex.split(args_str)
            except ValueError as e:
                emit_info(
                    f"[red]Invalid command syntax: {e}[/red]", message_group=group_id
                )
                return True

            if not args:
                self._commands["list"].execute([], group_id=group_id)
                return True

            subcommand = args[0].lower()
            sub_args = args[1:] if len(args) > 1 else []

            # Route to appropriate command handler
            command_handler = self._commands.get(subcommand)
            if command_handler:
                command_handler.execute(sub_args, group_id=group_id)
                return True
            else:
                emit_info(
                    f"[yellow]Unknown MCP subcommand: {subcommand}[/yellow]",
                    message_group=group_id,
                )
                emit_info(
                    "Type '/mcp help' for available commands", message_group=group_id
                )
                return True

        except Exception as e:
            logger.error(f"Error handling MCP command '{command}': {e}")
            emit_info(f"Error executing MCP command: {e}", message_group=group_id)
            return True
