"""Shell command safety assessment agent.

This agent provides rapid risk assessment of shell commands before execution.
It's designed to be ultra-lightweight with a concise prompt (<200 tokens) and
uses structured output for reliable parsing.
"""

from typing import TYPE_CHECKING, List

from code_puppy.agents.base_agent import BaseAgent

if TYPE_CHECKING:
    pass


class ShellSafetyAgent(BaseAgent):
    """Lightweight agent for assessing shell command safety risks.

    This agent evaluates shell commands for potential risks including:
    - File system destruction (rm -rf, dd, format, mkfs)
    - Database operations (DROP, TRUNCATE, unfiltered UPDATE/DELETE)
    - Privilege escalation (sudo, su, chmod 777)
    - Network operations (wget/curl to unknown hosts)
    - Data exfiltration patterns

    The agent returns structured output with a risk level and brief reasoning.
    """

    @property
    def name(self) -> str:
        """Agent name for internal use."""
        return "shell_safety_checker"

    @property
    def display_name(self) -> str:
        """User-facing display name."""
        return "Shell Safety Checker 🛡️"

    @property
    def description(self) -> str:
        """Agent description."""
        return "Lightweight agent that assesses shell command safety risks"

    def get_system_prompt(self) -> str:
        """Get the ultra-concise system prompt for shell safety assessment.

        This prompt is kept under 200 tokens for fast inference and low cost.
        """
        return """You are a shell command safety analyzer. Assess risk levels concisely.

**Risk Levels:**
- none: Completely safe (ls, pwd, echo, cat readonly files)
- low: Minimal risk (mkdir, touch, git status, read-only queries)
- medium: Moderate risk (file edits, package installs, service restarts)
- high: Significant risk (rm files, UPDATE/DELETE without WHERE, TRUNCATE, chmod dangerous permissions)
- critical: Severe/destructive (rm -rf, DROP TABLE/DATABASE, dd, format, mkfs, bq delete dataset, unfiltered mass deletes)

**Evaluate:**
- Scope (single file vs. entire system)
- Reversibility (can it be undone?)
- Data loss potential
- Privilege requirements
- Database destruction patterns

**Output:** Risk level + reasoning (max 1 sentence)."""

    def get_available_tools(self) -> List[str]:
        """This agent uses no tools - pure reasoning only."""
        return []
