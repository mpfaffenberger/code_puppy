"""TIER 4: Proactive token monitoring for GUI Cub.

Provides real-time token usage tracking with threshold-based warnings and
automatic checkpoint generation to prevent context limit failures.

DIRECTORY ISOLATION GUARANTEE:
All files created by this module are stored EXCLUSIVELY in:
    ~/.code_puppy/agents/gui-cub/

No files are EVER written to:
    - ~/.code_puppy/ (root - shared by all agents)
    - ~/.code_puppy/agents/ (agents directory - shared)
    - Any other agent's directory

This ensures GUI Cub monitoring does not interfere with other code-puppy
components or agents.

File Structure:
    ~/.code_puppy/agents/gui-cub/
    ├── gui_cub_knowledge_base.md          (main KB, rotated at 800 lines)
    ├── resume_prompt.md                    (latest resume, replaced each time)
    ├── sessions/
    │   └── session_YYYYMMDD_HHMMSS.md     (session snapshots, kept forever)
    └── gui_cub_knowledge_base_YYYYMMDD_HHMMSS.md  (archived KBs)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from rich.console import Console

console = Console()


def get_gui_cub_base_dir() -> "Path":
    """Get the GUI Cub base directory in user's home, cross-platform.

    ISOLATION: This path is EXCLUSIVELY for GUI Cub and will never interfere
    with other code-puppy agents or global directories.

    Returns the path: ~/.code_puppy/agents/gui-cub/

    Platform-specific paths:
    - Windows: C:/Users/<username>/.code_puppy/agents/gui-cub
    - macOS: /Users/<username>/.code_puppy/agents/gui-cub
    - Linux: /home/<username>/.code_puppy/agents/gui-cub

    All GUI Cub monitoring files (sessions, KBs, resume prompts) are stored
    ONLY in this directory and its subdirectories. No files are written to:
    - ~/.code_puppy/ (root)
    - ~/.code_puppy/agents/ (shared agents dir)
    - Any other agent's directory

    Falls back to environment variables (HOME, USERPROFILE) if needed.
    Last resort: uses temp directory with warning.

    Returns:
        Path object pointing to GUI Cub's base directory
    """
    from pathlib import Path
    import os
    import tempfile

    # Path.home() works correctly on all platforms
    home_dir = Path.home()

    # Fallback to environment variables if Path.home() fails
    if not home_dir or not home_dir.exists():
        # Try common environment variables
        home_str = os.environ.get("HOME") or os.environ.get("USERPROFILE")
        if home_str:
            home_dir = Path(home_str)
        else:
            # Last resort: use temp directory with warning
            home_dir = Path(tempfile.gettempdir())
            console.print(
                "[yellow]Warning: Could not determine home directory, using temp directory[/yellow]"
            )

    # Build the GUI Cub specific path
    gui_cub_dir = home_dir / ".code_puppy" / "agents" / "gui-cub"

    # SAFETY: Ensure path ends with gui-cub to prevent bleeding into other directories
    assert str(gui_cub_dir).endswith("gui-cub"), (
        f"Invalid GUI Cub directory: {gui_cub_dir}"
    )

    return gui_cub_dir


@dataclass
class TokenUsageMetrics:
    """Metrics for token monitoring."""

    warnings_fired: int = 0
    checkpoints_created: int = 0
    emergencies_fired: int = 0
    context_clears_prompted: int = 0


class TokenMonitor:
    """Monitors token usage and triggers threshold actions.

    Thresholds:
    - 70%: Warning message
    - 85%: Auto-checkpoint + suggest context clear
    - 95%: Emergency pause + force checkpoint
    """

    def __init__(self, context_limit: int = 128000):
        """Initialize token monitor.

        Args:
            context_limit: Maximum token limit for the model (default: 128K)
        """
        self.context_limit = context_limit
        self.current_tokens = 0

        # Thresholds (as percentages)
        self.warning_threshold = 0.70  # 70%
        self.checkpoint_threshold = 0.85  # 85%
        self.emergency_threshold = 0.95  # 95%

        # State tracking
        self.warning_fired = False
        self.checkpoint_fired = False
        self.emergency_fired = False

        # Metrics
        self.metrics = TokenUsageMetrics()

    def update(
        self, total_tokens: int
    ) -> Literal["warning", "checkpoint", "emergency"] | None:
        """Update current token count and check thresholds.

        Args:
            total_tokens: Current total token count

        Returns:
            Threshold event name if triggered, None otherwise
        """
        self.current_tokens = total_tokens
        percentage = total_tokens / self.context_limit

        # Check thresholds in order (highest to lowest)
        if percentage >= self.emergency_threshold and not self.emergency_fired:
            self.emergency_fired = True
            self.metrics.emergencies_fired += 1
            return "emergency"

        elif percentage >= self.checkpoint_threshold and not self.checkpoint_fired:
            self.checkpoint_fired = True
            self.metrics.checkpoints_created += 1
            return "checkpoint"

        elif percentage >= self.warning_threshold and not self.warning_fired:
            self.warning_fired = True
            self.metrics.warnings_fired += 1
            return "warning"

        return None

    def get_percentage(self) -> float:
        """Get current context usage percentage."""
        return (self.current_tokens / self.context_limit) * 100

    def get_remaining(self) -> int:
        """Get remaining tokens before limit."""
        return self.context_limit - self.current_tokens

    def reset_threshold_flags(self) -> None:
        """Reset threshold flags after context clear."""
        self.warning_fired = False
        self.checkpoint_fired = False
        self.emergency_fired = False

    def get_metrics(self) -> TokenUsageMetrics:
        """Get monitoring metrics."""
        return self.metrics

    def get_status_display(self) -> str:
        """Get formatted status display string.

        Returns:
            Rich-formatted string with token usage visualization
        """
        percentage = self.get_percentage()

        # Color-coded based on usage
        if percentage < 70:
            color = "green"
            emoji = "✅"
        elif percentage < 85:
            color = "yellow"
            emoji = "⚠️"
        elif percentage < 95:
            color = "orange"
            emoji = "🟠"
        else:
            color = "red"
            emoji = "🚨"

        # Build status string
        status = (
            f"\n[bold]Context Usage:[/bold] [{color}]{emoji} {percentage:.1f}%[/{color}]\n"
            f"[dim]  {self.current_tokens:,} / {self.context_limit:,} tokens "
            f"({self.get_remaining():,} remaining)[/dim]\n"
        )

        # Add visual meter
        bar_width = 40
        filled = int((percentage / 100) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        status += f"[{color}]{bar}[/{color}]"

        return status


def emit_warning_threshold(monitor: TokenMonitor) -> str:
    """Emit 70% threshold warning message.

    Args:
        monitor: TokenMonitor instance

    Returns:
        Formatted warning message
    """
    percentage = monitor.get_percentage()
    remaining = monitor.get_remaining()

    msg = (
        f"\n[bold yellow]⚠️  CONTEXT WARNING[/bold yellow]\n"
        f"[dim]   Usage: {percentage:.1f}% ({monitor.current_tokens:,} / "
        f"{monitor.context_limit:,} tokens)[/dim]\n"
        f"[dim]   Remaining: {remaining:,} tokens[/dim]\n\n"
        f"[yellow]Recommendation:[/yellow]\n"
        f"  • Consider saving progress soon\n"
        f"  • Monitor workflow progress closely\n"
        f"  • Prepare to wrap up or checkpoint if usage continues growing\n"
    )

    console.print(msg)
    return msg


def emit_checkpoint_threshold(monitor: TokenMonitor) -> str:
    """Emit 85% threshold checkpoint suggestion.

    Args:
        monitor: TokenMonitor instance

    Returns:
        Formatted checkpoint message
    """
    percentage = monitor.get_percentage()

    msg = (
        f"\n[bold orange]🟠 CONTEXT HIGH ({percentage:.1f}%)[/bold orange]\n\n"
        f"[yellow]Context usage is getting high. Consider:[/yellow]\n"
        f"  • Wrapping up the current workflow\n"
        f"  • Saving important findings to the knowledge base\n"
        f"  • Starting a fresh session if needed\n\n"
        f"[dim]Continuing much further may hit context limits.[/dim]\n"
    )

    console.print(msg)
    monitor.metrics.context_clears_prompted += 1
    return msg


def emit_emergency_threshold(monitor: TokenMonitor) -> str:
    """Emit 95% threshold emergency warning.

    Args:
        monitor: TokenMonitor instance

    Returns:
        Formatted emergency message
    """
    percentage = monitor.get_percentage()

    msg = (
        f"\n[bold red]🚨 CONTEXT CRITICAL ({percentage:.1f}%)[/bold red]\n\n"
        f"[red]Context usage is critically high![/red]\n\n"
        f"[yellow]URGENT - Recommend:[/yellow]\n"
        f"  • Stop current workflow immediately\n"
        f"  • Save all critical findings to knowledge base\n"
        f"  • Start a new session\n\n"
        f"[dim]Continuing will very likely hit the hard context limit and fail.[/dim]\n"
    )

    console.print(msg)
    return msg


def generate_resume_prompt(agent, current_task: str | None = None) -> str:
    """Generate a resume prompt that captures current context.

    This creates a compressed summary of the agent's current state that can be
    used to resume work after clearing message history.

    Args:
        agent: The GUI Cub agent instance
        current_task: Optional description of the current task

    Returns:
        A resume prompt that captures essential context
    """
    from datetime import datetime

    # Get recent message history to summarize
    messages = agent.get_message_history()

    # Extract key information from recent messages
    recent_context = []
    user_messages = []
    assistant_actions = []

    # Analyze last 10 messages for context
    for msg in messages[-10:]:
        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                user_messages.append(content)
            elif role == "assistant" and content:
                # Extract tool calls or key actions
                if "tool" in str(content).lower() or "click" in str(content).lower():
                    assistant_actions.append(content[:200])  # First 200 chars

    # Build resume prompt
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    resume_prompt = f"""# GUI Cub Context Resume - {timestamp}

## Session Continuation
This session is resuming after an automatic context clear at {agent.token_monitor.get_percentage():.1f}% token usage.

## Current Task
{current_task or "Continuing previous workflow automation task"}

## Recent Context
"""

    if user_messages:
        resume_prompt += "\n### Recent User Requests:\n"
        for i, msg in enumerate(user_messages[-3:], 1):  # Last 3 user messages
            resume_prompt += f"{i}. {msg[:300]}\n"  # First 300 chars

    if assistant_actions:
        resume_prompt += "\n### Recent Actions Performed:\n"
        for i, action in enumerate(assistant_actions[-5:], 1):  # Last 5 actions
            resume_prompt += f"{i}. {action}\n"

    resume_prompt += """\n## Instructions
Continue the task from where we left off. Check the knowledge base at `~/.code_puppy/agents/gui-cub/gui_cub_knowledge_base.md` for:
- Element discoveries and locators
- Workflow patterns
- Recent findings saved before context clear

Proceed with the next logical step in the workflow.
"""

    return resume_prompt


def auto_save_and_resume(agent, current_task: str | None = None) -> tuple[bool, str]:
    """Automatically save context to knowledge base and resume with fresh context.

    TIER 4.5: Autonomous context self-management.
    When token usage hits 85%, automatically:
    1. Save session snapshot to unique file (never deleted)
    2. Replace resume_prompt.md with latest resume
    3. Append brief entry to main KB (with auto-rotation at 800 lines)
    4. Clear message history
    5. Load resume prompt as first message

    Storage Strategy (all in ~/.code_puppy/agents/gui-cub/):
    - gui_cub_knowledge_base.md: Main KB (kept < 1000 lines, rotates when > 800)
    - resume_prompt.md: Current resume (REPLACED each time, not appended)
    - sessions/session_YYYYMMDD_HHMMSS.md: Session snapshots (kept forever)
    - gui_cub_knowledge_base_YYYYMMDD_HHMMSS.md: Archived KBs (when rotated)

    Args:
        agent: The GUI Cub agent instance
        current_task: Optional description of current task

    Returns:
        Tuple of (success: bool, message: str)
    """
    from pathlib import Path

    try:
        # Get cross-platform base directory
        # Windows: C:\Users\<username>\.code_puppy\agents\gui-cub
        # macOS: /Users/<username>/.code_puppy/agents/gui-cub
        # Linux: /home/<username>/.code_puppy/agents/gui-cub
        base_dir = get_gui_cub_base_dir()
        base_dir.mkdir(parents=True, exist_ok=True)

        sessions_dir = base_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        kb_path = base_dir / "gui_cub_knowledge_base.md"
        resume_path = base_dir / "resume_prompt.md"

        # Create unique session ID
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = sessions_dir / f"session_{session_id}.md"

        # SAFETY: Ensure all paths are within gui-cub directory
        assert kb_path.is_relative_to(base_dir), (
            f"KB path {kb_path} is outside base_dir {base_dir}"
        )
        assert resume_path.is_relative_to(base_dir), (
            f"Resume path {resume_path} is outside base_dir {base_dir}"
        )
        assert session_path.is_relative_to(base_dir), (
            f"Session path {session_path} is outside base_dir {base_dir}"
        )

        # Step 1: Generate resume prompt BEFORE clearing
        resume_prompt = generate_resume_prompt(agent, current_task)

        # Step 2: Save session snapshot (kept for history, never deleted)
        session_entry = f"""# GUI Cub Session - {session_id}

**Timestamp:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Token Usage:** {agent.token_monitor.get_percentage():.1f}% ({agent.token_monitor.current_tokens:,} tokens)
**Resume Count:** {agent.token_monitor.metrics.checkpoints_created}

## Context at Clear

{resume_prompt}

---

## Message History Summary

Total messages: {len(agent.get_message_history())}

---
"""

        try:
            with open(session_path, "w", encoding="utf-8") as f:
                f.write(session_entry)
        except Exception:
            pass  # Non-critical

        # Step 3: REPLACE resume prompt file (not append!)
        try:
            with open(resume_path, "w", encoding="utf-8") as f:
                f.write(resume_prompt)
        except Exception:
            pass  # Non-critical

        # Step 4: Append brief entry to main KB (keep it small!)
        kb_entry = f"""\n## Auto-Resume {session_id}
**Tokens:** {agent.token_monitor.current_tokens:,} → Cleared  
**Session:** See `sessions/session_{session_id}.md`  
**Resume:** See `resume_prompt.md`\n
"""

        try:
            # Check KB size and rotate if needed (keep < 1000 lines)
            if kb_path.exists():
                with open(kb_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                # If KB > 800 lines, archive and start fresh
                if len(lines) > 800:
                    archive_path = base_dir / f"gui_cub_knowledge_base_{session_id}.md"
                    kb_path.rename(archive_path)
                    # Start fresh KB
                    with open(kb_path, "w", encoding="utf-8") as f:
                        f.write(f"# GUI Cub Knowledge Base\n\n")
                        f.write(
                            f"**Previous KB archived:** `gui_cub_knowledge_base_{session_id}.md`\n\n"
                        )

            # Append brief entry
            with open(kb_path, "a", encoding="utf-8") as f:
                f.write(kb_entry)
        except Exception:
            pass  # Non-critical

        # Step 5: Clear message history
        agent.clear_message_history()

        # Step 6: Load resume prompt as first message
        agent.append_to_message_history({"role": "user", "content": resume_prompt})

        # Step 7: Reset threshold flags since we cleared context
        agent.token_monitor.reset_threshold_flags()

        success_msg = (
            f"\n[bold green]✅ CONTEXT AUTO-RESUMED[/bold green]\n\n"
            f"[green]Autonomous context management successful:[/green]\n"
            f"  • Session saved: sessions/session_{session_id}.md\n"
            f"  • Resume prompt: resume_prompt.md (replaced)\n"
            f"  • Message history cleared\n"
            f"  • Token usage reset to ~{agent.token_monitor.current_tokens:,} tokens\n"
            f"  • Continuing task seamlessly\n\n"
            f"[dim]Location: ~/.code_puppy/agents/gui-cub/[/dim]\n"
        )

        console.print(success_msg)
        return True, success_msg

    except Exception as e:
        error_msg = f"Failed to auto-resume: {str(e)}"
        console.print(f"[red]❌ {error_msg}[/red]")
        return False, error_msg
