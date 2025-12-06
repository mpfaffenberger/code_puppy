"""ACP (Agent Client Protocol) support for Code Puppy.

This module implements the Agent Client Protocol, allowing Code Puppy
to be used with Zed editor and other ACP-compatible clients.

Usage: code-puppy --acp
"""

from code_puppy.acp.main import run_acp_agent

__all__ = ["run_acp_agent"]
