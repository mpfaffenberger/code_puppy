"""
MCP Bind / Unbind Commands - Persistently wire MCP servers to agents.

Unlike ``/mcp start`` (which creates an ephemeral, session-only binding),
``/mcp bind`` writes a persistent entry to ``mcp_agent_bindings.json`` so the
server follows the agent across restarts. ``/mcp unbind`` removes it.
"""

import logging
from typing import List, Optional, Tuple

from rich.text import Text

from code_puppy.mcp_.agent_bindings import remove_binding, set_binding
from code_puppy.messaging import emit_error, emit_info, emit_success

from .base import MCPCommandBase
from .utils import find_server_id_by_name, suggest_similar_servers

# Configure logging
logger = logging.getLogger(__name__)


class _BindCommandBase(MCPCommandBase):
    """Shared plumbing for bind/unbind: arg parsing + name resolution."""

    def _resolve_canonical_server_name(self, server_name: str) -> Optional[str]:
        """Return the config-file casing of ``server_name``, or None if absent.

        Bindings are keyed by the canonical server name so they match what
        the manager/agent look up later — case-insensitive user input is
        normalized here.
        """
        server_id = find_server_id_by_name(self.manager, server_name)
        if not server_id:
            return None
        try:
            for server in self.manager.list_servers():
                if server.id == server_id:
                    return server.name
        except Exception:  # pragma: no cover - defensive
            pass
        return server_name

    def _validate_agent(self, agent_name: str, group_id: str) -> bool:
        """Check that ``agent_name`` is a real, available agent."""
        try:
            from code_puppy.agents.agent_manager import get_available_agents

            available = get_available_agents()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Could not load available agents: {e}")
            # Fail open: don't block a binding just because discovery hiccuped.
            return True

        if agent_name in available:
            return True

        emit_error(f"Unknown agent '{agent_name}'", message_group=group_id)
        emit_info(
            f"Available agents: {', '.join(sorted(available))}",
            message_group=group_id,
        )
        return False

    def _resolve_or_report(
        self, server_name: str, agent_name: str, group_id: str
    ) -> Optional[Tuple[str, str]]:
        """Resolve server + agent, emitting errors on failure.

        Returns ``(canonical_server_name, agent_name)`` on success, else None.
        """
        canonical_name = self._resolve_canonical_server_name(server_name)
        if not canonical_name:
            emit_error(f"Server '{server_name}' not found", message_group=group_id)
            suggest_similar_servers(self.manager, server_name, group_id=group_id)
            return None

        if not self._validate_agent(agent_name, group_id):
            return None

        return canonical_name, agent_name


class BindCommand(_BindCommandBase):
    """
    Command handler for persistently binding an MCP server to an agent.

    Usage::

        /mcp bind <server> <agent>                 # bind + auto-start
        /mcp bind <server> <agent> --no-autostart  # bind, stay dormant
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        if group_id is None:
            group_id = self.generate_group_id()

        # Split flags from positional args so order doesn't matter.
        auto_start = True
        positional: List[str] = []
        for arg in args:
            if arg == "--no-autostart":
                auto_start = False
            elif arg == "--autostart":
                auto_start = True
            else:
                positional.append(arg)

        if len(positional) < 2:
            emit_info(
                Text.from_markup(
                    "[yellow]Usage: /mcp bind <server> <agent> "
                    "[--no-autostart][/yellow]"
                ),
                message_group=group_id,
            )
            return

        server_name, agent_name = positional[0], positional[1]

        try:
            resolved = self._resolve_or_report(server_name, agent_name, group_id)
            if resolved is None:
                return
            canonical_name, agent_name = resolved

            set_binding(agent_name, canonical_name, auto_start=auto_start)

            autostart_note = (
                "[dim](auto-start on)[/dim]"
                if auto_start
                else "[dim](auto-start off)[/dim]"
            )
            emit_success(
                Text.from_markup(
                    f" Bound '{canonical_name}' to agent "
                    f"'{agent_name}' {autostart_note}"
                ),
                message_group=group_id,
            )
        except Exception as e:
            logger.error(f"Error binding '{server_name}' to '{agent_name}': {e}")
            emit_error(f"Failed to bind server: {e}", message_group=group_id)


class UnbindCommand(_BindCommandBase):
    """
    Command handler for removing a persistent MCP server <-> agent binding.

    Usage::

        /mcp unbind <server> <agent>
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        if group_id is None:
            group_id = self.generate_group_id()

        if len(args) < 2:
            emit_info(
                Text.from_markup(
                    "[yellow]Usage: /mcp unbind <server> <agent>[/yellow]"
                ),
                message_group=group_id,
            )
            return

        server_name, agent_name = args[0], args[1]

        try:
            # Resolve to canonical casing if the server still exists, but don't
            # hard-fail if it's already gone — you should still be able to
            # unbind a stale entry pointing at a deleted server.
            canonical_name = (
                self._resolve_canonical_server_name(server_name) or server_name
            )

            removed = remove_binding(agent_name, canonical_name)
            if removed:
                emit_success(
                    Text.from_markup(
                        f" Unbound '{canonical_name}' from agent '{agent_name}'"
                    ),
                    message_group=group_id,
                )
            else:
                emit_info(
                    f"No binding found: '{canonical_name}' → '{agent_name}'",
                    message_group=group_id,
                )
        except Exception as e:
            logger.error(f"Error unbinding '{server_name}' from '{agent_name}': {e}")
            emit_error(f"Failed to unbind server: {e}", message_group=group_id)
