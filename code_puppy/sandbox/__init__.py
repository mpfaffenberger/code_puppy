"""
Sandboxing module for code-puppy.

Provides filesystem and network isolation for shell command execution,
inspired by Anthropic's Claude Code sandboxing approach.

Supports:
- Linux: bubblewrap (bwrap) for filesystem isolation
- macOS: sandbox-exec for filesystem isolation
- All platforms: Network proxy for domain restriction
- Resource limits: CPU and memory constraints
- Retry mechanism: dangerouslyDisableSandbox for failed commands
"""

from .command_wrapper import SandboxCommandWrapper
from .config import SandboxConfig
from .filesystem_isolation import get_filesystem_isolator
from .retry_handler import SandboxRetryHandler

__all__ = [
    "SandboxCommandWrapper",
    "SandboxConfig",
    "get_filesystem_isolator",
    "SandboxRetryHandler",
]
