"""TIER 4: Proactive token monitoring for GUI-Cub.

Provides real-time token usage tracking with threshold-based warnings and
automatic checkpoint generation to prevent context limit failures.

DIRECTORY ISOLATION GUARANTEE:
All files created by this module are stored EXCLUSIVELY in:
    ~/.code_puppy/agents/gui-cub/

No files are EVER written to:
    - ~/.code_puppy/ (root - shared by all agents)
    - ~/.code_puppy/agents/ (agents directory - shared)
    - Any other agent's directory

This ensures GUI-Cub monitoring does not interfere with other code-puppy
agents and state management.

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
from pathlib import Path
from typing import Literal

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart
from rich.console import Console

console = Console()


def get_gui_cub_base_dir() -> Path:
    """Get the GUI-Cub base directory in user's home, cross-platform.

    ISOLATION: This path is EXCLUSIVELY for GUI-Cub and will never interfere
    with other code-puppy agents or global directories.

    Returns the path: ~/.code_puppy/agents/gui-cub/

    Platform-specific paths:
    - Windows: C:/Users/<username>/.code_puppy/agents/gui-cub
    - macOS: /Users/<username>/.code_puppy/agents/gui-cub
    - Linux: /home/<username>/.code_puppy/agents/gui-cub

    All GUI-Cub monitoring files (sessions, KBs, resume prompts) are stored
    ONLY in this directory and its subdirectories. No files are written to:
    - ~/.code_puppy/ (root)
    - ~/.code_puppy/agents/ (shared agents dir)
    - Any other agent's directory

    Falls back to environment variables (HOME, USERPROFILE) if needed.
    Last resort: uses temp directory with warning.

    Returns:
        Path object pointing to GUI-Cub's base directory
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

    # Build the GUI-Cub specific path
    gui_cub_dir = home_dir / ".code_puppy" / "agents" / "gui-cub"

    # SAFETY: Ensure path ends with gui-cub to prevent bleeding into other directories
    assert str(gui_cub_dir).endswith("gui-cub"), (
        f"Invalid GUI-Cub directory: {gui_cub_dir}"
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


# ============================================================================
# HELPER FUNCTIONS FOR INTELLIGENT CONTEXT EXTRACTION
# ============================================================================


def _extract_text_from_message(msg) -> list[str]:
    """Extract text content from a message's parts.

    Args:
        msg: ModelRequest or ModelResponse message

    Returns:
        List of text strings found in the message
    """
    texts = []
    if hasattr(msg, "parts"):
        for part in msg.parts:
            if hasattr(part, "content"):
                content = str(part.content)
                if content.strip():
                    texts.append(content)
    return texts


def extract_user_goal(messages: list) -> str:
    """Extract the user's primary goal from message history.

    Looks for user messages containing task descriptions, goals, or requests.
    Prioritizes recent messages but scans broadly for context.

    Args:
        messages: Full message history

    Returns:
        User goal as clear sentence, or "Unknown task" if unclear
    """
    goal_keywords = [
        "automate",
        "workflow",
        "task",
        "goal",
        "want to",
        "need to",
        "can you",
        "help me",
        "i need",
        "let's",
        "please",
        "trying to",
        "create",
        "build",
        "make",
        "generate",
        "extract",
        "process",
    ]

    # Look at last 50 user messages for goal
    user_goals = []
    for msg in messages[-100:]:
        if isinstance(msg, ModelRequest):
            texts = _extract_text_from_message(msg)
            for text in texts:
                text_lower = text.lower()
                # Check if this message contains goal-indicating keywords
                if any(keyword in text_lower for keyword in goal_keywords):
                    # Extract first sentence or first 200 chars
                    first_sentence = text.split(".")[0].split("\n")[0].strip()
                    if 10 < len(first_sentence) < 300:
                        user_goals.append(first_sentence)

    if user_goals:
        # Return the most recent meaningful goal
        return user_goals[-1]

    # Fallback: look for any substantial user message
    for msg in reversed(messages[-50:]):
        if isinstance(msg, ModelRequest):
            texts = _extract_text_from_message(msg)
            for text in texts:
                if len(text.strip()) > 20:
                    return text.strip()[:200]

    return "Continue previous automation task"


def analyze_progress(messages: list) -> dict:
    """Analyze workflow progress from message history.

    Tracks completed actions, in-progress work, and potential next steps.

    Args:
        messages: Full message history

    Returns:
        Dictionary with completed, in_progress, and remaining steps
    """
    from pydantic_ai.messages import ToolCallPart

    completed_actions = []
    recent_tools = []

    # Analyze last 50 messages for progress indicators
    for msg in messages[-50:]:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                # Track tool usage
                if isinstance(part, ToolCallPart):
                    tool_name = part.tool_name
                    recent_tools.append(tool_name)

                    # Infer completion based on tool type
                    action_desc = _infer_action_from_tool(tool_name, part)
                    if action_desc:
                        completed_actions.append(action_desc)

                # Look for text content indicating progress
                elif hasattr(part, "content"):
                    content = str(part.content).lower()
                    if any(
                        phrase in content
                        for phrase in ["completed", "done", "finished", "success"]
                    ):
                        # Extract what was completed
                        lines = str(part.content).split("\n")
                        for line in lines[:5]:
                            if any(
                                p in line.lower()
                                for p in ["completed", "done", "finished"]
                            ):
                                completed_actions.append(line.strip()[:150])

    # Estimate completion percentage based on action density
    total_actions = len(completed_actions)
    percentage = min(75, total_actions * 10) if total_actions > 0 else 10

    return {
        "completed": completed_actions[-10:],  # Last 10 completed items
        "in_progress": ["Executing current step"],
        "remaining": ["Complete remaining workflow steps"],
        "percentage": percentage,
        "recent_tools": recent_tools[-10:],
    }


def _infer_action_from_tool(tool_name: str, part) -> str | None:
    """Infer human-readable action from tool call.

    Args:
        tool_name: Name of the tool called
        part: ToolCallPart with arguments

    Returns:
        Human-readable action description or None
    """
    # Map tool names to action descriptions
    action_map = {
        "desktop_click": "Clicked UI element",
        "desktop_type_text": "Typed text input",
        "desktop_keyboard_press": "Pressed keyboard shortcut",
        "desktop_screenshot": "Captured screen",
        "ocr_extract_text": "Extracted text via OCR",
        "desktop_sleep": "Waited for UI update",
        "edit_file": "Modified file",
        "read_file": "Read file contents",
    }

    base_action = action_map.get(tool_name, f"Executed {tool_name}")

    # Try to extract specific details from args
    if hasattr(part, "args"):
        args = part.args
        if isinstance(args, dict):
            # Add context from common arg patterns
            if "text" in args and args["text"]:
                return f"{base_action}: '{args['text'][:50]}'"
            if "key" in args or "hotkey" in args:
                key = args.get("key") or args.get("hotkey")
                return f"{base_action}: {key}"
            if "x" in args and "y" in args:
                return f"{base_action} at ({args['x']}, {args['y']})"

    return base_action


def extract_key_findings(messages: list) -> dict:
    """Extract important discoveries from message history.

    Looks for element locators, keyboard shortcuts, timing info, and patterns.

    Args:
        messages: Full message history

    Returns:
        Dictionary of categorized discoveries
    """
    from pydantic_ai.messages import ToolCallPart

    discoveries = {
        "element_locators": [],
        "keyboard_shortcuts": [],
        "timing_info": [],
        "patterns": [],
        "successful_approaches": [],
        "failed_approaches": [],
    }

    # Scan last 100 messages for discoveries
    for msg in messages[-100:]:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                # Extract keyboard shortcuts used
                if (
                    isinstance(part, ToolCallPart)
                    and part.tool_name == "desktop_keyboard_press"
                ):
                    if hasattr(part, "args") and isinstance(part.args, dict):
                        key = part.args.get("hotkey") or part.args.get("key")
                        if key and key not in discoveries["keyboard_shortcuts"]:
                            discoveries["keyboard_shortcuts"].append(key)

                # Extract coordinate-based locators
                elif (
                    isinstance(part, ToolCallPart) and part.tool_name == "desktop_click"
                ):
                    if hasattr(part, "args") and isinstance(part.args, dict):
                        x, y = part.args.get("x"), part.args.get("y")
                        if x and y:
                            locator = f"Click target at ({x}, {y})"
                            if locator not in discoveries["element_locators"]:
                                discoveries["element_locators"].append(locator)

                # Extract timing information
                elif (
                    isinstance(part, ToolCallPart) and part.tool_name == "desktop_sleep"
                ):
                    if hasattr(part, "args") and isinstance(part.args, dict):
                        seconds = part.args.get("seconds")
                        if seconds:
                            timing = f"Wait {seconds}s for UI update"
                            if timing not in discoveries["timing_info"]:
                                discoveries["timing_info"].append(timing)

                # Extract text-based findings from responses
                elif hasattr(part, "content"):
                    content = str(part.content)
                    # Look for success/failure indicators
                    if "success" in content.lower():
                        if len(content) < 200:
                            discoveries["successful_approaches"].append(content.strip())
                    elif "error" in content.lower() or "fail" in content.lower():
                        if len(content) < 200:
                            discoveries["failed_approaches"].append(content.strip())

    # Limit each category to top 5 items
    for key in discoveries:
        discoveries[key] = discoveries[key][:5]

    return discoveries


def infer_next_action(messages: list, progress: dict) -> str:
    """Determine the next logical step to take.

    Based on recent context and progress, infer what should happen next.

    Args:
        messages: Full message history
        progress: Progress analysis from analyze_progress()

    Returns:
        Clear, actionable next step description
    """

    # Check if there's an explicit next step mentioned
    for msg in reversed(messages[-20:]):
        if isinstance(msg, ModelRequest):
            texts = _extract_text_from_message(msg)
            for text in texts:
                text_lower = text.lower()
                if "next" in text_lower or "then" in text_lower:
                    # Extract sentence containing "next"
                    sentences = text.split(".")
                    for sentence in sentences:
                        if "next" in sentence.lower() or "then" in sentence.lower():
                            return sentence.strip()[:200]

    # Infer based on last tool used
    recent_tools = progress.get("recent_tools", [])
    if recent_tools:
        last_tool = recent_tools[-1]

        if "screenshot" in last_tool:
            return "Analyze screenshot and identify next UI element to interact with"
        elif "click" in last_tool:
            return "Wait for UI response and verify action completed"
        elif "type" in last_tool or "keyboard" in last_tool:
            return "Verify input accepted and proceed to next field or action"
        elif "sleep" in last_tool:
            return "Check if UI update completed and continue workflow"

    return "Continue with next step in the workflow"


def summarize_recent_activity(messages: list, limit: int = 10) -> list[str]:
    """Create intelligent summary of recent actions.

    Summarizes groups of similar actions rather than listing every tool call.

    Args:
        messages: Message history
        limit: Max number of summary items

    Returns:
        List of summarized actions (not raw tool calls)
    """
    from pydantic_ai.messages import ToolCallPart

    actions = []
    consecutive_types = {}

    # Group consecutive similar actions
    for msg in messages[-30:]:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    tool_name = part.tool_name

                    # Group consecutive similar tools
                    if tool_name in consecutive_types:
                        consecutive_types[tool_name] += 1
                    else:
                        # Flush previous group if exists
                        if consecutive_types:
                            for prev_tool, count in consecutive_types.items():
                                if count > 1:
                                    actions.append(
                                        f"Performed {prev_tool} {count} times"
                                    )
                                else:
                                    action = _infer_action_from_tool(prev_tool, part)
                                    actions.append(action or prev_tool)
                        consecutive_types = {tool_name: 1}

    # Flush remaining
    for tool, count in consecutive_types.items():
        if count > 1:
            actions.append(f"Performed {tool} {count} times")
        else:
            actions.append(tool)

    return actions[-limit:]


def generate_resume_prompt(agent, current_task: str | None = None) -> str:
    """Generate an intelligent, context-rich resume prompt.

    This creates a comprehensive summary of the agent's current state with:
    - User's primary goal/task
    - Progress summary (completed, in-progress, remaining)
    - Key discoveries (element locators, patterns, timing)
    - Important context and decisions
    - Recent activity summary
    - Next action to take

    The resume is designed to enable seamless continuation after context clear,
    providing enough information to resume work without losing critical details.

    Args:
        agent: The GUI-Cub agent instance
        current_task: Optional task override (if None, extracts from messages)

    Returns:
        Structured resume prompt (target: 200-800 lines, max: 1000 lines)
    """
    from datetime import datetime

    try:
        # Get full message history
        messages = agent.get_message_history()

        # Extract context using helper functions
        user_goal = current_task or extract_user_goal(messages)
        progress = analyze_progress(messages)
        discoveries = extract_key_findings(messages)
        next_action = infer_next_action(messages, progress)
        recent_activity = summarize_recent_activity(messages, limit=10)

        # Build timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        percentage = agent.token_monitor.get_percentage()

        # Build comprehensive resume prompt
        lines = []
        lines.append(f"# GUI-Cub Context Resume - {timestamp}")
        lines.append("")
        lines.append("## Session Continuation")
        lines.append(
            f"This session is resuming after an automatic context clear at {percentage:.1f}% token usage."
        )
        lines.append("")
        lines.append("---")
        lines.append("")

        # PRIMARY TASK section
        lines.append("## 🎯 PRIMARY TASK")
        lines.append("")
        lines.append(f"**User Goal:** {user_goal}")
        lines.append("")
        lines.append(f"**Current Status:** {progress['percentage']}% complete")
        lines.append("")
        lines.append(f"**Next Immediate Action:** {next_action}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # PROGRESS SUMMARY section
        lines.append("## 📊 PROGRESS SUMMARY")
        lines.append("")

        if progress["completed"]:
            lines.append("### Completed ✅")
            for item in progress["completed"]:
                lines.append(f"- {item}")
            lines.append("")

        if progress["in_progress"]:
            lines.append("### In Progress ⏳")
            for item in progress["in_progress"]:
                lines.append(f"- {item}")
            lines.append("")

        if progress["remaining"]:
            lines.append("### Remaining ⏸️")
            for item in progress["remaining"]:
                lines.append(f"- {item}")
            lines.append("")

        lines.append("---")
        lines.append("")

        # KEY DISCOVERIES section
        lines.append("## 🔍 KEY DISCOVERIES")
        lines.append("")

        has_discoveries = any(discoveries.values())

        if discoveries["element_locators"]:
            lines.append("### Element Locators")
            for item in discoveries["element_locators"]:
                lines.append(f"- {item}")
            lines.append("")

        if discoveries["keyboard_shortcuts"]:
            lines.append("### Keyboard Shortcuts")
            for item in discoveries["keyboard_shortcuts"]:
                lines.append(f"- {item}")
            lines.append("")

        if discoveries["timing_info"]:
            lines.append("### Timing & Delays")
            for item in discoveries["timing_info"]:
                lines.append(f"- {item}")
            lines.append("")

        if discoveries["patterns"]:
            lines.append("### Workflow Patterns")
            for item in discoveries["patterns"]:
                lines.append(f"- {item}")
            lines.append("")

        if discoveries["successful_approaches"]:
            lines.append("### Successful Approaches")
            for item in discoveries["successful_approaches"]:
                lines.append(f"- {item}")
            lines.append("")

        if discoveries["failed_approaches"]:
            lines.append("### Failed Approaches (Avoid)")
            for item in discoveries["failed_approaches"]:
                lines.append(f"- {item}")
            lines.append("")

        if not has_discoveries:
            lines.append("*No specific discoveries documented yet*")
            lines.append("")

        lines.append("---")
        lines.append("")

        # RECENT ACTIVITY section
        lines.append("## 📝 RECENT ACTIVITY SUMMARY")
        lines.append("")
        if recent_activity:
            for i, activity in enumerate(recent_activity, 1):
                lines.append(f"{i}. {activity}")
        else:
            lines.append("*No recent activity recorded*")
        lines.append("")
        lines.append("---")
        lines.append("")

        # RESUME INSTRUCTIONS section
        lines.append("## 🚀 RESUME INSTRUCTIONS")
        lines.append("")
        lines.append("1. Review the PRIMARY TASK and current status above")
        lines.append("2. Check KEY DISCOVERIES for element locators and patterns")
        lines.append("3. Execute the NEXT IMMEDIATE ACTION")
        lines.append("4. Continue following the workflow until goal is achieved")
        lines.append(
            "5. Refer to knowledge base if needed: `~/.code_puppy/agents/gui-cub/gui_cub_knowledge_base.md`"
        )
        lines.append("")
        lines.append(f"**Ready to continue from:** {next_action}")
        lines.append("")

        # Join and enforce length limit
        resume_prompt = "\n".join(lines)

        # Enforce hard cap of 1000 lines
        line_count = len(lines)
        if line_count > 1000:
            # Trim to 1000 lines, prioritizing essential sections
            # Keep header, task, progress, instructions
            # Trim discoveries and recent activity if needed
            trimmed_lines = lines[:50]  # Header + PRIMARY TASK
            trimmed_lines.extend(lines[-30:])  # RESUME INSTRUCTIONS
            resume_prompt = "\n".join(trimmed_lines)
            resume_prompt += (
                "\n\n[Note: Resume prompt was trimmed to stay under 1000 lines]\n"
            )

        return resume_prompt

    except Exception as e:
        # Graceful fallback: return basic resume if analysis fails
        console.print(
            f"[yellow]Warning: Resume generation failed ({e}), using fallback[/yellow]"
        )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""# GUI-Cub Context Resume - {timestamp}

## Session Continuation
This session is resuming after an automatic context clear at {agent.token_monitor.get_percentage():.1f}% token usage.

## Current Task
{current_task or "Continue previous automation task"}

## Instructions
Continue the task from where we left off. Check the knowledge base at `~/.code_puppy/agents/gui-cub/gui_cub_knowledge_base.md` for context.
"""


def cleanup_old_sessions(ttl_days: int = 14) -> tuple[int, int]:
    """Clean up stale session directories older than TTL.

    Active session directories are ephemeral and tied to process IDs.
    Once a process ends, the directory becomes stale. This function
    removes old session directories to prevent disk bloat.

    Args:
        ttl_days: Time-to-live in days. Directories older than this are deleted.
                  Default is 14 days (2 weeks).

    Returns:
        Tuple of (directories_removed, errors_encountered)
    """
    from datetime import datetime, timedelta
    import shutil

    try:
        base_dir = get_gui_cub_base_dir()
        active_sessions_dir = base_dir / "active_sessions"

        if not active_sessions_dir.exists():
            return 0, 0  # Nothing to clean

        now = datetime.now()
        cutoff_time = now - timedelta(days=ttl_days)
        removed_count = 0
        error_count = 0

        # Iterate through session directories
        for session_dir in active_sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue  # Skip non-directories

            try:
                # Get directory modification time
                mtime = datetime.fromtimestamp(session_dir.stat().st_mtime)

                # Remove if older than TTL
                if mtime < cutoff_time:
                    shutil.rmtree(session_dir)
                    removed_count += 1

            except Exception:
                error_count += 1
                continue  # Skip problematic directories

        return removed_count, error_count

    except Exception:
        # If cleanup fails entirely, don't crash - just return 0
        return 0, 1


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
        agent: The GUI-Cub agent instance
        current_task: Optional description of current task

    Returns:
        Tuple of (success: bool, message: str)
    """

    from rich.console import Console
    console = Console()

    try:
        # STEP 0: Clean up old session directories (14-day TTL)
        # This runs ONLY during auto-resume (when hitting 85% tokens),
        # not on every GUI-Cub initialization, for performance
        removed, errors = cleanup_old_sessions(ttl_days=14)
        if removed > 0:
            console.print(
                f"[dim]Cleaned up {removed} stale session director{'y' if removed == 1 else 'ies'} "
                f"(older than 14 days)[/dim]"
            )

        # Get cross-platform base directory
        # Windows: C:\Users\<username>\.code_puppy\agents\gui-cub
        # macOS: /Users/<username>/.code_puppy/agents/gui-cub
        # Linux: /home/<username>/.code_puppy/agents/gui-cub
        base_dir = get_gui_cub_base_dir()
        base_dir.mkdir(parents=True, exist_ok=True)

        # Session snapshots directory (permanent archive)
        sessions_dir = base_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # Active sessions directory (ephemeral, per-process)
        active_sessions_dir = base_dir / "active_sessions"
        active_sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # This session's specific directory (based on process ID)
        session_dir = active_sessions_dir / agent.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        kb_path = base_dir / "gui_cub_knowledge_base.md"
        resume_path = session_dir / "resume_prompt.md"  # Session-specific!

        # Create unique session ID for archival snapshot
        snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = sessions_dir / f"session_{snapshot_id}.md"

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
        session_entry = f"""# GUI-Cub Session - {snapshot_id}

**Timestamp:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Process ID:** {agent.session_id}
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
        # File is written to session-specific directory (active_sessions/{session_id}/)
        try:
            with open(resume_path, "w", encoding="utf-8") as f:
                f.write(resume_prompt)
        except Exception:
            pass  # Non-critical

        # Step 4: Append brief entry to main KB (keep it small!)
        kb_entry = f"""\n## Auto-Resume {snapshot_id}
**Tokens:** {agent.token_monitor.current_tokens:,} → Cleared  
**Process:** {agent.session_id}  
**Session:** See `sessions/session_{snapshot_id}.md`  
**Resume:** See `active_sessions/{agent.session_id}/resume_prompt.md`\n
"""

        try:
            # Check KB size and rotate if needed (keep < 1000 lines)
            if kb_path.exists():
                with open(kb_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                # If KB > 800 lines, archive and start fresh
                if len(lines) > 800:
                    archive_path = base_dir / f"gui_cub_knowledge_base_{snapshot_id}.md"
                    # SAFETY: Copy instead of rename to avoid data loss on error
                    import shutil

                    shutil.copy2(kb_path, archive_path)
                    # Start fresh KB (overwrites original)
                    with open(kb_path, "w", encoding="utf-8") as f:
                        f.write("# GUI-Cub Knowledge Base\n\n")
                        f.write(
                            f"**Previous KB archived:** `gui_cub_knowledge_base_{snapshot_id}.md`\n\n"
                        )

            # Append brief entry
            with open(kb_path, "a", encoding="utf-8") as f:
                f.write(kb_entry)
        except Exception:
            pass  # Non-critical

        # Step 5: Clear message history
        agent.clear_message_history()

        # Step 6: Load resume prompt as first message
        # Use proper ModelRequest instead of dict to match pydantic_ai message format
        resume_message = ModelRequest([TextPart(resume_prompt)])
        agent.append_to_message_history(resume_message)

        # Step 7: Reset threshold flags since we cleared context
        agent.token_monitor.reset_threshold_flags()

        # Step 8: Recalculate token count with new resume message
        new_token_count = sum(
            agent.estimate_tokens_for_message(msg)
            for msg in agent.get_message_history()
        )
        agent.token_monitor.update(new_token_count)

        success_msg = (
            f"\n[bold green]✅ CONTEXT AUTO-RESUMED[/bold green]\n\n"
            f"[green]Autonomous context management successful:[/green]\n"
            f"  • Session saved: sessions/session_{snapshot_id}.md\n"
            f"  • Resume prompt: active_sessions/{agent.session_id}/resume_prompt.md\n"
            f"  • Message history cleared\n"
            f"  • Token usage reset to ~{new_token_count:,} tokens\n"
            f"  • Continuing task seamlessly\n\n"
            f"[dim]Location: ~/.code_puppy/agents/gui-cub/[/dim]\n"
        )

        console.print(success_msg)
        return True, success_msg

    except Exception as e:
        error_msg = f"Failed to auto-resume: {str(e)}"
        console.print(f"[red]❌ {error_msg}[/red]")
        return False, error_msg
