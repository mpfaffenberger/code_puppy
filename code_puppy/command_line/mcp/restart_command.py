"""
MCP Restart Command - Restarts a specific MCP server.
"""

import asyncio
import logging
from typing import List, Optional

from rich.text import Text

from code_puppy.messaging import emit_info
from code_puppy.i18n import t
from rich.markup import escape

from .base import MCPCommandBase
from .utils import find_server_id_by_name, suggest_similar_servers

# Configure logging
logger = logging.getLogger(__name__)


class RestartCommand(MCPCommandBase):
    """
    Command handler for restarting MCP servers.

    Stops, reloads configuration, and starts a specific MCP server.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Restart a specific MCP server.

        Args:
            args: Command arguments, expects [server_name]
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        if not args:
            emit_info("Usage: /mcp restart <server_name>", message_group=group_id)
            return

        server_name = args[0]

        try:
            # Find server by name
            server_id = find_server_id_by_name(self.manager, server_name)
            if not server_id:
                emit_info(f"Server '{server_name}' not found", message_group=group_id)
                suggest_similar_servers(self.manager, server_name, group_id=group_id)
                return

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                emit_info(t("mcp.restart.no_loop"), message_group=group_id)
                return
            pending = getattr(self.manager, "_pending_restart_tasks", None)
            if not isinstance(pending, dict):
                pending = self.manager._pending_restart_tasks = {}
            if server_id in pending and not pending[server_id].done():
                emit_info(
                    t("mcp.restart.pending", name=escape(server_name)),
                    message_group=group_id,
                )
                return
            from code_puppy.agents import get_current_agent

            agent = (
                get_current_agent()
            )  # rebind the requesting agent, not a later switch

            async def restart():
                success = False
                try:
                    success = await self.manager.restart_server(server_id)
                except Exception:
                    logger.exception("MCP restart failed for %s", server_id)
                finally:
                    # Failed replacement must not leave old toolsets cached. Do not
                    # rebuild on failure: the builder could autostart the failed server.
                    agent._code_generation_agent = None
                    agent.pydantic_agent = None
                if success:
                    try:
                        agent.reload_code_generation_agent()
                        agent.update_mcp_tool_cache_sync()
                    except Exception:
                        agent._code_generation_agent = None
                        agent.pydantic_agent = None
                        logger.exception("MCP restarted but agent rebuild failed")
                        emit_info(
                            t("mcp.restart.rebind_failed", name=escape(server_name)),
                            message_group=group_id,
                        )
                        return
                key = "mcp.restart.done" if success else "mcp.restart.failed"
                emit_info(t(key, name=escape(server_name)), message_group=group_id)

            task = loop.create_task(restart(), name=f"mcp_restart_{server_id}")
            pending[server_id] = task

            def finished(done):
                if pending.get(server_id) is done:
                    pending.pop(server_id, None)
                if not done.cancelled() and done.exception() is not None:
                    logger.error("MCP restart completion failed for %s", server_id)

            task.add_done_callback(finished)
            emit_info(
                t("mcp.restart.scheduled", name=escape(server_name)),
                message_group=group_id,
            )

        except Exception as e:
            logger.error(f"Error restarting server '{server_name}': {e}")
            emit_info(
                Text.from_markup(f"[red]Failed to restart server: {e}[/red]"),
                message_group=group_id,
            )
