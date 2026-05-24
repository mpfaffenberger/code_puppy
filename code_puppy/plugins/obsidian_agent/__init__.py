"""Obsidian Agent plugin.

Registers a specialized agent for safe Obsidian CLI workflows.
"""

from .agent_obsidian import ObsidianAgent

__all__ = ["ObsidianAgent"]
