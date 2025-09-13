"""
MCP Install Command - Installs pre-configured MCP servers from the registry.
"""

import logging
from typing import List, Optional

from code_puppy.messaging import emit_info
from code_puppy.state_management import is_tui_mode

from .base import MCPCommandBase
from .wizard_utils import run_interactive_install_wizard

# Configure logging
logger = logging.getLogger(__name__)


class InstallCommand(MCPCommandBase):
    """
    Command handler for installing MCP servers from registry.

    Installs pre-configured MCP servers with optional interactive wizard.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Install a pre-configured MCP server from the registry.

        Args:
            args: Server ID and optional custom name
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        try:
            # If in TUI mode, show message to use Ctrl+T
            if is_tui_mode():
                emit_info(
                    "In TUI mode, use Ctrl+T to open the MCP Install Wizard",
                    message_group=group_id,
                )
                return

            # In interactive mode, use the comprehensive installer
            if not args:
                # No args - launch interactive wizard
                success = run_interactive_install_wizard(self.manager, group_id)
                if success:
                    try:
                        from code_puppy.agent import reload_mcp_servers

                        reload_mcp_servers()
                    except ImportError:
                        pass
                return

            # Has args - install directly from catalog
            server_id = args[0]
            success = self._install_from_catalog(server_id, group_id)
            if success:
                try:
                    from code_puppy.agent import reload_mcp_servers

                    reload_mcp_servers()
                except ImportError:
                    pass
            return

        except ImportError:
            emit_info("Server registry not available", message_group=group_id)
        except Exception as e:
            logger.error(f"Error installing server: {e}")
            emit_info(f"Installation failed: {e}", message_group=group_id)

    def _install_from_catalog(self, server_name_or_id: str, group_id: str) -> bool:
        """Install a server directly from the catalog by name or ID."""
        try:
            from code_puppy.mcp.server_registry_catalog import catalog
            from code_puppy.messaging import emit_prompt

            from .utils import find_server_id_by_name
            from .wizard_utils import install_server_from_catalog

            # Try to find server by ID first, then by name/search
            selected_server = catalog.get_by_id(server_name_or_id)

            if not selected_server:
                # Try searching by name
                results = catalog.search(server_name_or_id)
                if not results:
                    emit_info(
                        f"❌ No server found matching '{server_name_or_id}'",
                        message_group=group_id,
                    )
                    emit_info(
                        "Try '/mcp install' to browse available servers",
                        message_group=group_id,
                    )
                    return False
                elif len(results) == 1:
                    selected_server = results[0]
                else:
                    # Multiple matches, show them
                    emit_info(
                        f"🔍 Multiple servers found matching '{server_name_or_id}':",
                        message_group=group_id,
                    )
                    for i, server in enumerate(results[:5]):
                        indicators = []
                        if server.verified:
                            indicators.append("✓")
                        if server.popular:
                            indicators.append("⭐")

                        indicator_str = ""
                        if indicators:
                            indicator_str = " " + "".join(indicators)

                        emit_info(
                            f"  {i + 1}. {server.display_name}{indicator_str}",
                            message_group=group_id,
                        )
                        emit_info(f"     ID: {server.id}", message_group=group_id)

                    emit_info(
                        "Please use the exact server ID: '/mcp install <server_id>'",
                        message_group=group_id,
                    )
                    return False

            # Show what we're installing
            emit_info(
                f"📦 Installing: {selected_server.display_name}", message_group=group_id
            )
            description = (
                selected_server.description
                if selected_server.description
                else "No description available"
            )
            emit_info(f"Description: {description}", message_group=group_id)
            emit_info("", message_group=group_id)

            # Get custom name (default to server name)
            server_name = emit_prompt(
                f"Enter custom name for this server [{selected_server.name}]: "
            ).strip()
            if not server_name:
                server_name = selected_server.name

            # Check if name already exists
            existing_server = find_server_id_by_name(self.manager, server_name)
            if existing_server:
                override = emit_prompt(
                    f"Server '{server_name}' already exists. Override it? [y/N]: "
                )
                if not override.lower().startswith("y"):
                    emit_info("Installation cancelled", message_group=group_id)
                    return False

            # Collect environment variables and command line arguments
            env_vars = {}
            cmd_args = {}

            # Get environment variables
            required_env_vars = selected_server.get_environment_vars()
            if required_env_vars:
                emit_info(
                    "\n[yellow]Required Environment Variables:[/yellow]",
                    message_group=group_id,
                )
                for var in required_env_vars:
                    # Check if already set in environment
                    import os

                    current_value = os.environ.get(var, "")
                    if current_value:
                        emit_info(
                            f"  {var}: [green]Already set[/green]",
                            message_group=group_id,
                        )
                        env_vars[var] = current_value
                    else:
                        value = emit_prompt(f"  Enter value for {var}: ").strip()
                        if value:
                            env_vars[var] = value

            # Get command line arguments
            required_cmd_args = selected_server.get_command_line_args()
            if required_cmd_args:
                emit_info(
                    "\n[yellow]Command Line Arguments:[/yellow]", message_group=group_id
                )
                for arg_config in required_cmd_args:
                    name = arg_config.get("name", "")
                    prompt = arg_config.get("prompt", name)
                    default = arg_config.get("default", "")
                    required = arg_config.get("required", True)

                    # If required or has default, prompt user
                    if required or default:
                        arg_prompt = f"  {prompt}"
                        if default:
                            arg_prompt += f" [{default}]"
                        if not required:
                            arg_prompt += " (optional)"

                        value = emit_prompt(f"{arg_prompt}: ").strip()
                        if value:
                            cmd_args[name] = value
                        elif default:
                            cmd_args[name] = default

            # Install the server
            return install_server_from_catalog(
                self.manager, selected_server, server_name, env_vars, cmd_args, group_id
            )

        except ImportError:
            emit_info("Server catalog not available", message_group=group_id)
            return False
        except Exception as e:
            logger.error(f"Error installing from catalog: {e}")
            emit_info(f"[red]Installation error: {e}[/red]", message_group=group_id)
            return False
