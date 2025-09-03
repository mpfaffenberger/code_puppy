"""
MCP Command Base Classes - Shared functionality for MCP command handlers.

Provides base classes and common utilities used across all MCP command modules.
"""

import logging

from rich.console import Console

from code_puppy.mcp.manager import get_mcp_manager

# Configure logging
logger = logging.getLogger(__name__)


class MCPCommandBase:
    """
    Base class for MCP command handlers.

    Provides common functionality like console access and MCP manager access
    that all command handlers need.
    """

    def __init__(self):
        """Initialize the base command handler."""
        self.console = Console()
        self.manager = get_mcp_manager()
        logger.debug(f"Initialized {self.__class__.__name__}")

    def generate_group_id(self) -> str:
        """Generate a unique group ID for message grouping."""
        import uuid

        return str(uuid.uuid4())
