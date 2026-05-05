"""The Pack - Specialized sub-agents coordinated by Pack Leader 🐺

This package contains the specialized agents that work together under
Pack Leader's coordination for parallel multi-agent workflows:

- **Bloodhound** 🐕‍🦺 - Issue tracking specialist (bd only)
- **Terrier** 🐕 - Worktree management (git worktree from base branch)
- **Code-Puppy** 🐶 - Task execution (coding work in worktrees, including clones)
- **Shepherd** 🐕 - Code review critic (quality gatekeeper)
- **Watchdog** 🐕‍🦺 - QA critic (tests, coverage, quality)
- **Retriever** 🦮 - Local branch merging (git merge to base branch)

All work happens locally - no GitHub PRs or remote pushes.
Everything merges to a declared base branch.

Each agent is designed to do one thing well, following the Unix philosophy.
Pack Leader orchestrates them to execute complex parallel workflows.
"""

from .bloodhound import BloodhoundAgent
from .retriever import RetrieverAgent
from .shepherd import ShepherdAgent
from .terrier import TerrierAgent
from .watchdog import WatchdogAgent

__all__ = [
    "BloodhoundAgent",
    "TerrierAgent",
    "RetrieverAgent",
    "ShepherdAgent",
    "WatchdogAgent",
]
