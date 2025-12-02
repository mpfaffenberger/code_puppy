"""
Factory for creating platform-specific filesystem isolators.
"""

from typing import Optional

from .base import FilesystemIsolator, get_current_platform
from .linux_isolator import BubblewrapIsolator
from .macos_isolator import SandboxExecIsolator


class NoOpIsolator(FilesystemIsolator):
    """No-op isolator for platforms without sandboxing or when disabled."""

    def is_available(self) -> bool:
        """Always available as a fallback."""
        return True

    def get_platform(self) -> str:
        """Platform-agnostic."""
        return "noop"

    def wrap_command(self, command: str, options) -> tuple[str, dict[str, str]]:
        """Return command unchanged."""
        return command, options.env or {}


def get_filesystem_isolator(platform: Optional[str] = None) -> FilesystemIsolator:
    """
    Get the appropriate filesystem isolator for the current platform.

    Args:
        platform: Override platform detection (mainly for testing)

    Returns:
        FilesystemIsolator instance for the current platform
    """
    if platform is None:
        platform = get_current_platform()

    # Try platform-specific isolators
    isolators = [
        BubblewrapIsolator(),
        SandboxExecIsolator(),
    ]

    for isolator in isolators:
        if isolator.get_platform() == platform and isolator.is_available():
            return isolator

    # Fallback to no-op isolator
    return NoOpIsolator()
