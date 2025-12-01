import logging
from typing import Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

# Configure logging
logger = logging.getLogger(__name__)


def load_server_names():
    """Load server names from the MCP manager."""
    try:
        from code_puppy.mcp_.manager import MCPManager

        manager = MCPManager()
        servers = manager.list_servers()
        return [server.name for server in servers]
    except Exception as e:
        logger.debug(f"Could not load server names: {e}")
        return []


class MCPCompleter(Completer):
    """
    A completer that triggers on '/mcp' to show available MCP subcommands
    and server names where appropriate.
    """

    def __init__(self, trigger: str = "/mcp"):
        self.trigger = trigger

        # Define all available MCP subcommands
        # Subcommands that take server names as arguments
        self.server_subcommands = {
            "start": "Start a specific MCP server",
            "stop": "Stop a specific MCP server",
            "restart": "Restart a specific MCP server",
            "status": "Show status of a specific MCP server",
            "logs": "Show logs for a specific MCP server",
            "edit": "Edit an existing MCP server config",
            "remove": "Remove an MCP server",
        }

        # Subcommands that don't take server names
        self.general_subcommands = {
            "list": "List all registered MCP servers",
            "start-all": "Start all MCP servers",
            "stop-all": "Stop all MCP servers",
            "test": "Test MCP server connection",
            "add": "Add a new MCP server",
            "install": "Install MCP servers from a list",
            "search": "Search for available MCP servers",
            "help": "Show help for MCP commands",
        }

        # All subcommands combined for completion when no subcommand is typed yet
        self.all_subcommands = {**self.server_subcommands, **self.general_subcommands}

        # Cache server names to avoid repeated lookups
        self._server_names_cache = None
        self._cache_timestamp = None

    def _get_server_names(self):
        """Get server names with caching."""
        import time

        # Cache for 30 seconds to avoid repeated manager calls
        current_time = time.time()
        if (
            self._server_names_cache is None
            or self._cache_timestamp is None
            or current_time - self._cache_timestamp > 30
        ):
            self._server_names_cache = load_server_names()
            self._cache_timestamp = current_time

        return self._server_names_cache or []

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        text = document.text
        cursor_position = document.cursor_position
        text_before_cursor = text[:cursor_position]

        # Only trigger if /mcp is at the very beginning of the line
        stripped_text = text_before_cursor.lstrip()
        if not stripped_text.startswith(self.trigger):
            return

        # Find where /mcp actually starts (after any leading whitespace)
        mcp_pos = text_before_cursor.find(self.trigger)
        mcp_end = mcp_pos + len(self.trigger)

        # Require a space after /mcp before showing completions
        if mcp_end >= len(text_before_cursor) or text_before_cursor[mcp_end] != " ":
            return

        # Extract everything after /mcp (and after the space)
        after_mcp = text_before_cursor[mcp_end + 1 :].strip()

        # If nothing after /mcp, show all available subcommands
        if not after_mcp:
            for subcommand, description in sorted(self.all_subcommands.items()):
                yield Completion(
                    subcommand,
                    start_position=0,
                    display=subcommand,
                    display_meta=description,
                )
            return

        # Parse what's been typed after /mcp
        # Split by space but be careful with what we're currently typing
        parts = after_mcp.split()

        # Priority: Check for server name completion first when appropriate
        # This handles cases like '/mcp start ' where the space indicates ready for server name
        if len(parts) >= 1:
            subcommand = parts[0].lower()

            # Only complete server names for specific subcommands
            if subcommand in self.server_subcommands:
                # Case 1: Exactly the subcommand followed by a space (ready for server name)
                if len(parts) == 1 and text.endswith(" "):
                    partial_server = ""
                    start_position = 0

                    server_names = self._get_server_names()
                    for server_name in sorted(server_names):
                        yield Completion(
                            server_name,
                            start_position=start_position,
                            display=server_name,
                            display_meta="MCP Server",
                        )
                    return

                # Case 2: Subcommand + partial server name (require space after subcommand)
                elif len(parts) == 2 and cursor_position > (
                    mcp_end + 1 + len(subcommand) + 1
                ):
                    partial_server = parts[1]
                    start_position = -(len(partial_server))

                    server_names = self._get_server_names()
                    for server_name in sorted(server_names):
                        if server_name.lower().startswith(partial_server.lower()):
                            yield Completion(
                                server_name,
                                start_position=start_position,
                                display=server_name,
                                display_meta="MCP Server",
                            )
                    return

        # If we only have one part and haven't returned above, show subcommand completions
        # This includes cases like '/mcp start' where they might want 'start-all'
        # But NOT when there's a space after the subcommand (which indicates they want arguments)
        if len(parts) == 1 and not text.endswith(" "):
            partial_subcommand = parts[0]
            for subcommand, description in sorted(self.all_subcommands.items()):
                if subcommand.startswith(partial_subcommand):
                    yield Completion(
                        subcommand,
                        start_position=-(len(partial_subcommand)),
                        display=subcommand,
                        display_meta=description,
                    )
            return

        # For general subcommands, we don't provide argument completion
        # They may have their own specific completions in the future
