"""Continuity-oriented message-history compaction.

Continuity is intentionally wired through the core compaction path instead of
the current plugin system. Code Puppy plugins can register commands, tools,
model types, prompts, and tool/run hooks, but they do not have a first-class
extension point for replacing the history processor's compaction decision or
mutating pydantic-ai message history while preserving tool-call/tool-return
ordering. Until such an extension point exists, keeping this strategy in the
core compaction path is safer than monkeypatching compaction from a plugin.
"""

from code_puppy.agents.continuity_compaction.engine import compact_continuity

__all__ = ["compact_continuity"]
