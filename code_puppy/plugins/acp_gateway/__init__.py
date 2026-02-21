"""ACP Gateway Plugin.

Exposes Code Puppy as an ACP (Agent Client Protocol) agent using the
official ``agent-client-protocol`` Python SDK.

The SDK handles all transport concerns (stdio JSON-RPC, session
lifecycle, content blocks).  This plugin provides the bridge between
ACP and Code Puppy's pydantic-ai agent system.

The plugin gracefully degrades — if ``agent-client-protocol`` is not
installed, Code Puppy starts normally with a warning log.
"""

__version__ = "0.2.0"
__description__ = "ACP Gateway plugin for Code Puppy"

from code_puppy.plugins.acp_gateway.agent import CodePuppyAgent, run_code_puppy_agent

__all__ = [
    "CodePuppyAgent",
    "run_code_puppy_agent",
]