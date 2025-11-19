"""
Main sandbox command wrapper that integrates filesystem and network isolation.
"""

import logging
import os
from typing import Optional

from .base import SandboxOptions
from .config import SandboxConfig
from .filesystem_isolation import get_filesystem_isolator
from .network_proxy import NetworkProxyServer

logger = logging.getLogger(__name__)


class SandboxCommandWrapper:
    """
    Wraps shell commands with sandboxing (filesystem + network isolation).
    """

    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
        proxy_server: Optional[NetworkProxyServer] = None,
    ):
        """
        Initialize the sandbox command wrapper.

        Args:
            config: Sandbox configuration (creates default if None)
            proxy_server: Network proxy server instance (creates if None)
        """
        self.config = config or SandboxConfig()
        self.proxy_server = proxy_server
        self._isolator = None

    def _get_isolator(self):
        """Get or create the filesystem isolator."""
        if self._isolator is None:
            self._isolator = get_filesystem_isolator()
            logger.info(
                f"Using filesystem isolator: {self._isolator.__class__.__name__} "
                f"(platform: {self._isolator.get_platform()})"
            )
        return self._isolator

    def is_sandboxing_available(self) -> bool:
        """
        Check if sandboxing is available on this system.

        Returns:
            True if sandboxing can be enabled
        """
        isolator = self._get_isolator()
        return isolator.is_available() and isolator.get_platform() != "noop"

    def is_command_excluded(self, command: str) -> bool:
        """
        Check if a command should be excluded from sandboxing.

        Args:
            command: The shell command to check

        Returns:
            True if command matches exclusion list
        """
        # Extract the first word (actual command) from the shell command
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False

        base_command = cmd_parts[0]

        # Check against excluded commands
        for excluded in self.config.excluded_commands:
            if base_command == excluded or base_command.endswith(f"/{excluded}"):
                logger.info(f"Command '{base_command}' is excluded from sandboxing")
                return True

        return False

    def wrap_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ) -> tuple[str, dict[str, str], bool]:
        """
        Wrap a command with sandboxing if enabled.

        Args:
            command: The shell command to wrap
            cwd: Working directory for the command
            env: Environment variables for the command

        Returns:
            Tuple of (wrapped_command, environment_dict, was_excluded)
        """
        # If sandboxing is disabled, return command unchanged
        if not self.config.enabled:
            return command, env or {}, False

        # Check if command is excluded
        if self.is_command_excluded(command):
            return command, env or {}, True

        # Get working directory
        if cwd is None:
            cwd = os.getcwd()

        # Build sandbox options
        options = SandboxOptions(
            filesystem_isolation=self.config.filesystem_isolation,
            network_isolation=self.config.network_isolation,
            allowed_read_paths=self.config.allowed_read_paths,
            allowed_write_paths=self.config.allowed_write_paths,
            denied_read_paths=self.config.denied_read_paths,
            read_scope=self.config.read_scope,
            cwd=cwd,
            env=env,
            max_memory_mb=self.config.max_memory_mb,
            max_cpu_percent=self.config.max_cpu_percent,
            max_execution_time=self.config.max_execution_time,
        )

        # Set proxy socket path if network isolation is enabled
        if self.config.network_isolation and self.proxy_server:
            options.proxy_socket_path = f"127.0.0.1:{self.config.proxy_port}"

        # Wrap with filesystem isolation if enabled
        if self.config.filesystem_isolation:
            isolator = self._get_isolator()

            if isolator.is_available():
                try:
                    wrapped_cmd, wrapped_env = isolator.wrap_command(command, options)
                    logger.debug(f"Wrapped command with {isolator.__class__.__name__}")
                    return wrapped_cmd, wrapped_env, False
                except Exception as e:
                    logger.error(f"Failed to wrap command with sandboxing: {e}")
                    logger.warning("Falling back to unsandboxed execution")
            else:
                logger.warning(
                    f"Filesystem isolation not available "
                    f"({isolator.__class__.__name__}), running unsandboxed"
                )

        return command, env or {}, False

    async def start_network_proxy(self, approval_callback=None):
        """
        Start the network proxy server if network isolation is enabled.

        Args:
            approval_callback: Optional callback for domain approval
        """
        if not self.config.enabled or not self.config.network_isolation:
            return

        if self.proxy_server is None:
            self.proxy_server = NetworkProxyServer(
                allowed_domains=self.config.allowed_domains,
                approval_callback=approval_callback,
                port=self.config.proxy_port,
            )

        if not self.proxy_server.is_running():
            await self.proxy_server.start()
            logger.info("Network proxy started for sandbox")

    async def stop_network_proxy(self):
        """Stop the network proxy server."""
        if self.proxy_server and self.proxy_server.is_running():
            await self.proxy_server.stop()
            logger.info("Network proxy stopped")

    def get_status(self) -> dict:
        """
        Get the current status of sandboxing.

        Returns:
            Dictionary with status information
        """
        isolator = self._get_isolator()

        return {
            **self.config.get_status(),
            "isolator": isolator.__class__.__name__,
            "isolator_platform": isolator.get_platform(),
            "isolator_available": isolator.is_available(),
            "proxy_running": self.proxy_server.is_running() if self.proxy_server else False,
        }
