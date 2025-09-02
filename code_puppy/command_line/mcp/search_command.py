"""
MCP Search Command - Searches for pre-configured MCP servers in the registry.
"""

import logging
from typing import List, Optional

from rich.table import Table

from code_puppy.messaging import emit_info, emit_system_message

from .base import MCPCommandBase

# Configure logging
logger = logging.getLogger(__name__)


class SearchCommand(MCPCommandBase):
    """
    Command handler for searching MCP server registry.

    Searches for pre-configured MCP servers with optional query terms.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Search for pre-configured MCP servers in the registry.

        Args:
            args: Search query terms
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        try:
            from code_puppy.mcp.server_registry_catalog import catalog

            if not args:
                # Show popular servers if no query
                emit_info(
                    "[bold cyan]Popular MCP Servers:[/bold cyan]\n",
                    message_group=group_id,
                )
                servers = catalog.get_popular(15)
            else:
                query = " ".join(args)
                emit_info(
                    f"[bold cyan]Searching for: {query}[/bold cyan]\n",
                    message_group=group_id,
                )
                servers = catalog.search(query)

            if not servers:
                emit_info(
                    "[yellow]No servers found matching your search[/yellow]",
                    message_group=group_id,
                )
                emit_info(
                    "Try: /mcp search database, /mcp search file, /mcp search git",
                    message_group=group_id,
                )
                return

            # Create results table
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("ID", style="cyan", width=20)
            table.add_column("Name", style="green")
            table.add_column("Category", style="yellow")
            table.add_column("Description", style="white")
            table.add_column("Tags", style="dim")

            for server in servers[:20]:  # Limit to 20 results
                tags = ", ".join(server.tags[:3])  # Show first 3 tags
                if len(server.tags) > 3:
                    tags += "..."

                # Add verified/popular indicators
                indicators = []
                if server.verified:
                    indicators.append("✓")
                if server.popular:
                    indicators.append("⭐")
                name_display = server.display_name
                if indicators:
                    name_display += f" {''.join(indicators)}"

                table.add_row(
                    server.id,
                    name_display,
                    server.category,
                    server.description[:50] + "..."
                    if len(server.description) > 50
                    else server.description,
                    tags,
                )

            # The first message established the group, subsequent messages will auto-group
            emit_system_message(table, message_group=group_id)
            emit_info("\n[dim]✓ = Verified  ⭐ = Popular[/dim]", message_group=group_id)
            emit_info(
                "[yellow]To install:[/yellow] /mcp install <id>", message_group=group_id
            )
            emit_info(
                "[yellow]For details:[/yellow] /mcp search <specific-term>",
                message_group=group_id,
            )

        except ImportError:
            emit_info(
                "[red]Server registry not available[/red]", message_group=group_id
            )
        except Exception as e:
            logger.error(f"Error searching server registry: {e}")
            emit_info(
                f"[red]Error searching servers: {e}[/red]", message_group=group_id
            )
