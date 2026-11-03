"""
MCP Search Command - Searches for pre-configured MCP servers in the registry.
"""

import logging
from typing import List, Optional

from rich.table import Table
from rich.text import Text

from code_puppy.i18n import t
from code_puppy.messaging import emit_info, emit_system_message, emit_warning

from .base import MCPCommandBase

# Configure logging
logger = logging.getLogger(__name__)

_SEARCH_EXAMPLES = "/mcp search database, /mcp search file, /mcp search git"


def _hint(label_key: str, command: str) -> Text:
    """A translated yellow label followed by a literal command."""
    return Text.assemble((t(label_key), "yellow"), f" {command}")


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
            from code_puppy.mcp_.server_registry_catalog import catalog

            if not args:
                # Show popular servers if no query
                emit_info(t("mcp.search.popular_title"), message_group=group_id)
                servers = catalog.get_popular(15)
            else:
                query = " ".join(args)
                emit_info(
                    t("mcp.search.searching", query=query), message_group=group_id
                )
                servers = catalog.search(query)

            if not servers:
                emit_warning(t("mcp.search.no_results"), message_group=group_id)
                emit_info(
                    t("mcp.search.try", examples=_SEARCH_EXAMPLES),
                    message_group=group_id,
                )
                return

            # Create results table
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column(Text(t("mcp.search.column.id")), style="cyan", width=20)
            table.add_column(Text(t("mcp.search.column.name")), style="green")
            table.add_column(Text(t("mcp.search.column.category")), style="yellow")
            table.add_column(Text(t("mcp.search.column.description")), style="white")
            table.add_column(Text(t("mcp.search.column.tags")), style="dim")

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
            emit_info(t("mcp.search.legend"), message_group=group_id)
            emit_info(
                _hint("mcp.search.install_label", "/mcp install <id>"),
                message_group=group_id,
            )
            emit_info(
                _hint("mcp.search.details_label", "/mcp search <specific-term>"),
                message_group=group_id,
            )

        except ImportError:
            emit_info(
                Text(t("mcp.search.registry_unavailable"), style="red"),
                message_group=group_id,
            )
        except Exception as e:
            logger.error(f"Error searching server registry: {e}")
            emit_info(
                Text(t("mcp.search.failed", error=e), style="red"),
                message_group=group_id,
            )
