"""The Pack - Specialized sub-agents coordinated by Pack Leader 🐺

This package contains the specialized agents that work together under
Pack Leader's coordination for parallel multi-agent workflows:

- **Bloodhound** 🩸 - Issue tracking specialist (bd + gh issues)
- **Terrier** 🐕 - Worktree management (git worktree)
- **Retriever** 🎾 - PR lifecycle management (gh pr)
- **Husky** 🐺 - Task execution (coding work in worktrees)

Each agent is designed to do one thing well, following the Unix philosophy.
Pack Leader orchestrates them to execute complex parallel workflows.
"""

from .bloodhound import BloodhoundAgent
from .husky import HuskyAgent
from .retriever import RetrieverAgent
from .terrier import TerrierAgent

__all__ = ["BloodhoundAgent", "TerrierAgent", "RetrieverAgent", "HuskyAgent"]
