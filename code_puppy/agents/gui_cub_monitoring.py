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
    remaining = monitor.get_remaining()

    msg = (
        f"\n[bold orange]🟠 CONTEXT HIGH ({percentage:.1f}%)[/bold orange]\n\n"
        f"[dim]   Usage: {percentage:.1f}% ({monitor.current_tokens:,} / "
        f"{monitor.context_limit:,} tokens)[/dim]\n"
        f"[dim]   Remaining: {remaining:,} tokens[/dim]\n\n"
        f"[yellow]Recommendations:[/yellow]\n"
        f"  • Consider wrapping up the current task\n"
        f"  • Summarize key findings to the knowledge base\n"
        f"  • You can continue to 95%, but plan accordingly\n"
        f"  • Start a fresh session when ready\n\n"
        f"[dim]Note: Context will NOT be cleared automatically. You're in control.[/dim]\n"
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


def get_session_backups_dir() -> "Path":
    """Get the session backups directory.
    
    Returns:
        Path to ~/.code_puppy/agents/gui-cub/sessions/
    """
    from pathlib import Path
    home_dir = Path.home()
    return home_dir / ".code_puppy" / "agents" / "gui-cub" / "sessions"


def list_recent_session_backups(limit: int = 5) -> list[dict]:
    """List recent session backups with summaries.
    
    Args:
        limit: Maximum number of backups to return (default: 5)
        
    Returns:
        List of dicts with keys: filename, timestamp, token_usage, message_count, summary
    """
    from pathlib import Path
    import re
    from datetime import datetime
    
    sessions_dir = get_session_backups_dir()
    
    if not sessions_dir.exists():
        return []
    
    backups = []
    
    # Get all session files sorted by modification time (newest first)
    session_files = sorted(
        sessions_dir.glob("session_*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    for session_file in session_files[:limit]:
        try:
            # Read the file
            content = session_file.read_text(encoding="utf-8")
            
            # Extract metadata
            timestamp_match = re.search(r"\*\*Timestamp:\*\* (.+)", content)
            token_match = re.search(r"\*\*Token Usage:\*\* ([0-9.]+)% \(([0-9,]+) tokens\)", content)
            message_match = re.search(r"\*\*Message Count:\*\* (\d+) messages", content)
            
            # Extract first 2 lines of context summary as a brief summary
            summary_section = re.search(r"## Context Summary\n\n(.+?)\n\n", content, re.DOTALL)
            summary = "No summary available"
            if summary_section:
                lines = summary_section.group(1).strip().split("\n")
                summary = " ".join(lines[:2])  # First 2 sentences
            
            backups.append({
                "filename": session_file.name,
                "path": str(session_file),
                "timestamp": timestamp_match.group(1) if timestamp_match else "Unknown",
                "token_usage": token_match.group(1) if token_match else "Unknown",
                "tokens": token_match.group(2) if token_match else "Unknown",
                "message_count": message_match.group(1) if message_match else "Unknown",
                "summary": summary,
            })
        except Exception:
            # Skip files we can't parse
            continue
    
    return backups


def get_most_recent_backup_summary() -> dict | None:
    """Get a summary of the most recent session backup.
    
    Returns:
        Dict with backup info, or None if no backups exist
    """
    backups = list_recent_session_backups(limit=1)
    return backups[0] if backups else None


def extract_workflow_files(messages: list) -> list[dict]:
    """Extract workflow files that were saved during the session.
    
    Args:
        messages: Full message history
        
    Returns:
        List of dicts with workflow file info: {path, type, timestamp}
    """
    from pydantic_ai.messages import ToolCallPart
    import re
    
    workflows = []
    
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    if part.tool_name == "edit_file":
                        if hasattr(part, "args") and isinstance(part.args, dict):
                            path = part.args.get("file_path", "")
                            # Check if it's a workflow file (.yaml, .yml, .json workflow)
                            if path and (path.endswith('.yaml') or path.endswith('.yml') or 
                                       'workflow' in path.lower() or 'recipe' in path.lower()):
                                workflows.append({
                                    "path": path,
                                    "type": "workflow",
                                })
    
    # Return unique workflows
    seen = set()
    unique_workflows = []
    for w in workflows:
        if w["path"] not in seen:
            seen.add(w["path"])
            unique_workflows.append(w)
    
    return unique_workflows


def save_session_backup(agent) -> tuple[bool, str]:
    """Save or update the session backup file for this session.

    This maintains ONE session file per session, updating it as the session progresses.
    Uses agent.session_id to identify the consistent file for this session.

    Workflow deduplication:
    - If workflows were saved (e.g., login.yaml), replaces verbose steps with:
      "Created login.yaml workflow at PATH"
    - Agent can read the workflow file later for details

    The backup is saved to sessions/ directory and can be read later to resume work.
    This does NOT clear message history - the agent continues with full context.

    Args:
        agent: The GUI-Cub agent instance

    Returns:
        Tuple of (success: bool, message: str)
    """
    from datetime import datetime
    from pathlib import Path

    try:
        # Get the base directory
        sessions_dir = get_session_backups_dir()
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Use consistent session file (one file per session)
        session_path = sessions_dir / f"{agent.session_id}.md"
        is_update = session_path.exists()

        # Get metadata
        messages = agent.get_message_history()
        message_count = len(messages)
        token_count = agent.token_monitor.current_tokens
        percentage = agent.token_monitor.get_percentage()
        
        # Check for workflow files that were saved
        workflow_files = extract_workflow_files(messages)
        
        # Generate concise context (max 600 lines)
        # If workflows exist, the context will be compressed
        context = generate_resume_prompt(agent)
        
        # Create compact header
        action = "Updated" if is_update else "Created"
        header = f"""# GUI-Cub Session - {agent.session_id}
**Last Updated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Tokens:** {percentage:.1f}% ({token_count:,}) | Messages: {message_count}
**Status:** Active session ({action} at {percentage:.1f}% threshold)
---
"""
        
        # Add workflow references if any were saved (deduplication)
        workflow_section = ""
        if workflow_files:
            workflow_section = "## Workflows Created\n"
            for wf in workflow_files:
                workflow_section += f"- Created workflow: {wf['path']}\n"
            workflow_section += "(Read workflow files for detailed steps - not duplicated here)\n---\n"
        
        # Combine header + workflows + context
        session_entry = header + workflow_section + context

        # Add footer
        session_entry += f"\n---\n**Location:** ~/.code_puppy/agents/gui-cub/sessions/{agent.session_id}.md\n**Resume:** Read this file to continue from this point"
        
        # Enforce 600-line hard limit
        entry_lines = session_entry.split("\n")
        if len(entry_lines) > 600:
            # Truncate and note
            session_entry = "\n".join(entry_lines[:597])
            session_entry += "\n[Truncated at 600 lines]\n---"
            session_entry += f"\n**Location:** ~/.code_puppy/agents/gui-cub/sessions/{agent.session_id}.md"

        # Write the backup (overwrite if updating)
        with open(session_path, "w", encoding="utf-8") as f:
            f.write(session_entry)
        
        # Mark that backup was created
        agent.session_backup_created = True

        action_verb = "updated" if is_update else "created"
        success_msg = f"[dim]📁 Session backup {action_verb}: sessions/{agent.session_id}.md[/dim]\n"
        console.print(success_msg)

        return True, success_msg

    except Exception as e:
        error_msg = f"Failed to save session backup: {str(e)}"
        console.print(f"[yellow]⚠️  {error_msg}[/yellow]")
        # Don't fail hard - backup is optional
        return False, error_msg


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


def extract_file_paths(messages: list) -> list[str]:
    """Extract file paths that were read or edited during the session.
    
    Args:
        messages: Full message history
        
    Returns:
        List of unique file paths
    """
    from pydantic_ai.messages import ToolCallPart
    
    file_paths = set()
    
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    if part.tool_name in ["read_file", "edit_file", "grep"]:
                        if hasattr(part, "args") and isinstance(part.args, dict):
                            # Extract file_path or directory
                            path = part.args.get("file_path") or part.args.get("directory")
                            if path and isinstance(path, str):
                                file_paths.add(path)
    
    return sorted(list(file_paths))


def extract_agent_reasoning_and_decisions(messages: list) -> dict:
    """Extract the agent's reasoning, decisions, and understanding from responses.
    
    This captures what the agent THINKS, not what was said.
    
    Args:
        messages: Message history
        
    Returns:
        Dict with: goals, strategies, learnings, decisions, blockers
    """
    state = {
        "current_goals": [],
        "strategies_approaches": [],
        "learnings_insights": [],
        "decisions_made": [],
        "blockers_challenges": [],
        "next_planned_steps": [],
    }
    
    # Extract from agent responses (their reasoning)
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if hasattr(part, "content"):
                    content = str(part.content).strip()
                    if not content:
                        continue
                    
                    content_lower = content.lower()
                    
                    # Extract goals/objectives
                    if any(kw in content_lower for kw in ["goal", "objective", "trying to", "need to", "will", "going to"]):
                        if len(content) < 300:
                            state["current_goals"].append(content)
                    
                    # Extract strategies/approaches
                    if any(kw in content_lower for kw in ["approach", "strategy", "using", "via", "method", "technique"]):
                        if len(content) < 300:
                            state["strategies_approaches"].append(content)
                    
                    # Extract learnings/insights
                    if any(kw in content_lower for kw in ["found", "discovered", "learned", "observed", "noticed"]):
                        if len(content) < 300:
                            state["learnings_insights"].append(content)
                    
                    # Extract decisions
                    if any(kw in content_lower for kw in ["decided", "choosing", "opted", "selected", "will use"]):
                        if len(content) < 300:
                            state["decisions_made"].append(content)
                    
                    # Extract blockers/challenges
                    if any(kw in content_lower for kw in ["issue", "problem", "error", "failed", "challenge", "blocker"]):
                        if len(content) < 300:
                            state["blockers_challenges"].append(content)
                    
                    # Extract next steps
                    if any(kw in content_lower for kw in ["next", "then", "after", "will now", "proceeding to"]):
                        if len(content) < 300:
                            state["next_planned_steps"].append(content)
    
    # Deduplicate and limit
    for key in state:
        state[key] = list(dict.fromkeys(state[key]))  # Remove duplicates
        state[key] = state[key][-20:]  # Keep last 20 per category
    
    return state


def extract_work_artifacts(messages: list) -> dict:
    """Extract concrete artifacts created/modified during the session.
    
    Args:
        messages: Message history
        
    Returns:
        Dict with: files_modified, code_snippets, workflows_created, etc.
    """
    from pydantic_ai.messages import ToolCallPart
    
    artifacts = {
        "files_edited": {},  # file -> list of what was done
        "files_read": [],
        "searches_performed": [],
        "code_snippets": [],
    }
    
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    if part.tool_name == "edit_file" and hasattr(part, "args"):
                        file_path = part.args.get("file_path")
                        if file_path:
                            if file_path not in artifacts["files_edited"]:
                                artifacts["files_edited"][file_path] = []
                            # Try to extract what was done
                            replacements = part.args.get("replacements", [])
                            if replacements:
                                for repl in replacements[:3]:  # First 3 changes
                                    old = repl.get("old_str", "")[:100]
                                    new = repl.get("new_str", "")[:100]
                                    artifacts["files_edited"][file_path].append(f"Changed: {old}... -> {new}...")
                    
                    elif part.tool_name == "read_file" and hasattr(part, "args"):
                        file_path = part.args.get("file_path")
                        if file_path and file_path not in artifacts["files_read"]:
                            artifacts["files_read"].append(file_path)
                    
                    elif part.tool_name == "grep" and hasattr(part, "args"):
                        search = part.args.get("search_string", "")
                        if search:
                            artifacts["searches_performed"].append(search)
    
    return artifacts


def generate_resume_prompt(agent, current_task: str | None = None) -> str:
    """Generate agent's internal state and self-reflection.

    This is NOT a conversation transcript (code-puppy already saves that).
    This is the agent's WORKING MEMORY:
    - What am I trying to accomplish?
    - What's my current understanding/strategy?
    - What have I learned/discovered?
    - What decisions have I made?
    - What's the current state of work?
    - What are my concrete next steps?

    Fills up to 600 lines with dense, useful state information.

    Args:
        agent: The GUI-Cub agent instance
        current_task: Optional task override

    Returns:
        Agent's internal state dump (max 600 lines)
    """
    from datetime import datetime

    try:
        messages = agent.get_message_history()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        percentage = agent.token_monitor.get_percentage()
        
        # Extract agent's internal state (not conversation)
        agent_state = extract_agent_reasoning_and_decisions(messages)
        artifacts = extract_work_artifacts(messages)
        file_paths = extract_file_paths(messages)
        discoveries = extract_key_findings(messages)
        
        # Build agent's working memory dump
        lines = []
        lines.append(f"# GUI-Cub Agent State - {timestamp}")
        lines.append(f"**Context:** {percentage:.1f}% tokens | {len(messages)} messages")
        lines.append("**Note:** This is the agent's working memory, not conversation transcript")
        lines.append("---")
        
        # CURRENT OBJECTIVES - What am I trying to do?
        lines.append("## CURRENT OBJECTIVES")
        if agent_state["current_goals"]:
            for i, goal in enumerate(agent_state["current_goals"][-10:], 1):
                lines.append(f"{i}. {goal}")
        else:
            lines.append("No explicit goals captured yet")
        lines.append("---")
        
        # STRATEGY & APPROACH - How am I approaching this?
        lines.append("## STRATEGY & APPROACH")
        if agent_state["strategies_approaches"]:
            for approach in agent_state["strategies_approaches"][-15:]:
                lines.append(f"- {approach}")
        else:
            lines.append("No strategy notes captured yet")
        lines.append("---")
        
        # DECISIONS MADE - What choices have I locked in?
        lines.append("## DECISIONS MADE")
        if agent_state["decisions_made"]:
            for decision in agent_state["decisions_made"][-15:]:
                lines.append(f"- {decision}")
        else:
            lines.append("No explicit decisions captured yet")
        lines.append("---")
        
        # LEARNINGS & INSIGHTS - What have I discovered?
        lines.append("## LEARNINGS & INSIGHTS")
        if agent_state["learnings_insights"]:
            for learning in agent_state["learnings_insights"][-20:]:
                lines.append(f"- {learning}")
        else:
            lines.append("No learnings captured yet")
        
        # Add technical discoveries
        if discoveries["element_locators"]:
            lines.append("**Element Locators Found:**")
            for loc in discoveries["element_locators"][:10]:
                lines.append(f"- {loc}")
        if discoveries["keyboard_shortcuts"]:
            lines.append("**Keyboard Shortcuts Used:**")
            for shortcut in discoveries["keyboard_shortcuts"][:10]:
                lines.append(f"- {shortcut}")
        if discoveries["timing_info"]:
            lines.append("**Timing Observations:**")
            for timing in discoveries["timing_info"][:10]:
                lines.append(f"- {timing}")
        
        lines.append("---")
        
        # BLOCKERS & CHALLENGES - What's in my way?
        lines.append("## BLOCKERS & CHALLENGES")
        if agent_state["blockers_challenges"]:
            for blocker in agent_state["blockers_challenges"][-10:]:
                lines.append(f"- {blocker}")
        else:
            lines.append("No blockers captured")
        lines.append("---")
        
        # WORK ARTIFACTS - What have I created/modified?
        lines.append("## WORK ARTIFACTS")
        if artifacts["files_edited"]:
            lines.append("**Files Edited:**")
            for file_path, changes in list(artifacts["files_edited"].items())[:20]:
                lines.append(f"- {file_path}")
                for change in changes[:3]:  # First 3 changes per file
                    lines.append(f"  {change}")
        
        if artifacts["files_read"]:
            lines.append("**Files Read:**")
            for file_path in artifacts["files_read"][:20]:
                lines.append(f"- {file_path}")
        
        if artifacts["searches_performed"]:
            lines.append("**Searches Performed:**")
            for search in artifacts["searches_performed"][:10]:
                lines.append(f"- grep: {search}")
        
        lines.append("---")
        
        # NEXT PLANNED STEPS - What should I do when I resume?
        lines.append("## NEXT PLANNED STEPS")
        if agent_state["next_planned_steps"]:
            for i, step in enumerate(agent_state["next_planned_steps"][-10:], 1):
                lines.append(f"{i}. {step}")
        else:
            lines.append("No next steps explicitly captured")
        
        # Add inferred next step from context
        lines.append("**Inferred from context:**")
        lines.append("Resume by continuing with the current task objectives listed above.")
        lines.append("Review files edited and learnings to understand current state.")
        
        lines.append("---")
        lines.append(f"**Total state lines:** {len(lines)}")
        lines.append("**Resume strategy:** Read this state dump, then ask user for current request")
        
        # Enforce 600-line limit (but use all available space)
        if len(lines) > 600:
            lines = lines[:597]
            lines.append("---")
            lines.append("[State truncated at 600 lines]")
            lines.append("Review objectives, decisions, and next steps above to resume")
        
        return "\n".join(lines)
    
    except Exception as e:
        console.print(f"[yellow]State generation failed ({e}), using fallback[/yellow]")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"# GUI-Cub Agent State - {timestamp}\n**Error:** State extraction failed\n**Action:** Review full message history to resume"


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


def append_to_knowledge_base(
    context: str,
    discovery: str,
    what_worked: str | None = None,
    what_failed: str | None = None,
    reusable: str | None = None,
    tags: str | None = None,
) -> tuple[bool, str]:
    """Append a diary-style entry to the knowledge base.
    
    The KB is a living document - accumulates reusable learnings across sessions.
    When it reaches 1000 lines, oldest entries are pruned (FIFO).
    
    Args:
        context: What was the agent doing? (e.g., "Automating Calculator app")
        discovery: What did the agent learn that's reusable?
        what_worked: Successful approaches (optional)
        what_failed: Failed approaches to avoid (optional)
        reusable: Links to workflows/files created (optional)
        tags: Searchable keywords like "#calculator #timing" (optional)
        
    Returns:
        Tuple of (success: bool, message: str)
        
    Example:
        append_to_knowledge_base(
            context="Calculator app automation",
            discovery="Requires 0.3s delay between button clicks",
            what_worked="Accessibility API with AXButton elements",
            what_failed="OCR unreliable for small number buttons",
            reusable="workflows/calculator_operations.yaml",
            tags="#calculator #accessibility #timing"
        )
    """
    try:
        base_dir = get_gui_cub_base_dir()
        kb_path = base_dir / "gui_cub_knowledge_base.md"
        
        # Build diary entry
        date_str = datetime.now().strftime("%Y-%m-%d")
        entry_lines = []
        entry_lines.append(f"## {date_str} | {context}")
        entry_lines.append(f"**Discovery:** {discovery}")
        
        if what_worked:
            entry_lines.append(f"**What worked:** {what_worked}")
        
        if what_failed:
            entry_lines.append(f"**What failed:** {what_failed}")
        
        if reusable:
            entry_lines.append(f"**Reusable:** {reusable}")
        
        if tags:
            entry_lines.append(f"**Tags:** {tags}")
        
        entry_lines.append("---")
        entry = "\n".join(entry_lines) + "\n"
        
        # Initialize KB if it doesn't exist
        if not kb_path.exists():
            header = "# GUI-Cub Knowledge Base\n"
            header += "Accumulated learnings across sessions - searchable, reusable wisdom\n\n"
            header += "---\n\n"
            kb_path.write_text(header, encoding="utf-8")
        
        # Read current KB
        current_content = kb_path.read_text(encoding="utf-8")
        lines = current_content.split("\n")
        
        # Append new entry
        updated_content = current_content + entry
        
        # FIFO pruning: if > 1000 lines, remove oldest diary entry
        if len(updated_content.split("\n")) > 1000:
            # Find first diary entry (## YYYY-MM-DD)
            first_entry_idx = None
            second_entry_idx = None
            
            for i, line in enumerate(lines):
                if line.startswith("## 20"):  # Diary entries start with ## 20XX-XX-XX
                    if first_entry_idx is None:
                        first_entry_idx = i
                    elif second_entry_idx is None:
                        second_entry_idx = i
                        break
            
            # Remove first entry (between first_entry_idx and second_entry_idx)
            if first_entry_idx is not None and second_entry_idx is not None:
                # Keep header + everything after first entry
                pruned_lines = lines[:first_entry_idx] + lines[second_entry_idx:]
                updated_content = "\n".join(pruned_lines) + "\n" + entry
                console.print("[dim]📝 Knowledge base pruned (FIFO): removed oldest entry[/dim]")
            elif first_entry_idx is not None:
                # Only one entry exists, keep it and add new one
                pass
        
        # Write updated KB
        kb_path.write_text(updated_content, encoding="utf-8")
        
        success_msg = f"[dim]📚 Knowledge base updated: {context}[/dim]"
        console.print(success_msg)
        return True, success_msg
        
    except Exception as e:
        error_msg = f"Failed to update knowledge base: {e}"
        console.print(f"[yellow]⚠️  {error_msg}[/yellow]")
        return False, error_msg


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
        # Use resolve() to handle Windows paths correctly
        base_dir_resolved = base_dir.resolve()
        kb_path_resolved = kb_path.resolve()
        resume_path_resolved = resume_path.resolve()
        session_path_resolved = session_path.resolve()
        
        try:
            kb_path_resolved.relative_to(base_dir_resolved)
            resume_path_resolved.relative_to(base_dir_resolved)
            session_path_resolved.relative_to(base_dir_resolved)
        except ValueError as e:
            error_msg = f"Path validation failed: {e}"
            console.print(f"[red]❌ {error_msg}[/red]")
            return False, error_msg

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

        # Step 2: Write session snapshot
        try:
            with open(session_path, "w", encoding="utf-8") as f:
                f.write(session_entry)
        except Exception as e:
            # Non-critical, log but continue
            pass

        # Step 3: REPLACE resume prompt file (CRITICAL - must succeed!)
        # File is written to session-specific directory (active_sessions/{session_id}/)
        try:
            with open(resume_path, "w", encoding="utf-8") as f:
                f.write(resume_prompt)
        except Exception as e:
            error_msg = f"CRITICAL: Failed to save resume prompt to {resume_path}: {e}"
            console.print(f"[red]❌ {error_msg}[/red]")
            return False, error_msg

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
