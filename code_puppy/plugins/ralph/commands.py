"""Ralph plugin slash commands - registered via custom_command callback."""

from typing import Any, List, Optional, Tuple

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from .state_manager import get_state_manager


def get_ralph_help() -> List[Tuple[str, str]]:
    """Get help entries for Ralph commands.

    Returns:
        List of (command_name, description) tuples.
    """
    return [
        ("ralph", "Show Ralph help and usage"),
        ("ralph status", "Show current prd.json status"),
        ("ralph prd", "Switch to PRD Generator agent to create a new PRD"),
        ("ralph convert", "Switch to Ralph Converter agent to convert PRD to JSON"),
        (
            "ralph start",
            "Switch to Ralph Orchestrator agent to run the autonomous loop",
        ),
        ("ralph reset", "Archive current run and reset for a new PRD"),
    ]


def handle_ralph_command(command: str, name: str) -> Optional[Any]:
    """Handle /ralph commands.

    Args:
        command: Full command string (e.g., "/ralph status")
        name: Command name without slash (e.g., "ralph")

    Returns:
        - True if handled (no further action)
        - String to process as agent input
        - None if not a ralph command
    """
    if not name.startswith("ralph"):
        return None

    # Parse subcommand
    parts = command.strip().split(maxsplit=2)
    subcommand = parts[1] if len(parts) > 1 else "help"
    args = parts[2] if len(parts) > 2 else ""

    # Route to handler
    handlers = {
        "help": _handle_help,
        "status": _handle_status,
        "prd": _handle_prd,
        "convert": _handle_convert,
        "start": _handle_start,
        "reset": _handle_reset,
    }

    handler = handlers.get(subcommand, _handle_help)
    return handler(args)


def _handle_help(args: str) -> bool:
    """Show Ralph help."""
    help_text = """
🐺 **Ralph - Autonomous AI Agent Loop**

Ralph runs AI coding agents repeatedly until all PRD items are complete.
Based on Geoffrey Huntley's Ralph pattern: https://ghuntley.com/ralph/

**Commands:**

  `/ralph status`     - Show current prd.json status and progress
  `/ralph prd`        - Create a new PRD (Product Requirements Document)
  `/ralph convert`    - Convert a markdown PRD to prd.json format
  `/ralph start`      - Start the autonomous execution loop
  `/ralph reset`      - Archive current run and start fresh

**Workflow:**

  1. `/ralph prd` - Create a detailed PRD with user stories
  2. `/ralph convert` - Convert it to prd.json format
  3. `/ralph start` - Let Ralph autonomously implement each story

**Key Files:**

  - `prd.json` - User stories with completion status
  - `progress.txt` - Learnings and patterns for future iterations
  - `archive/` - Previous runs (auto-archived on branch change)
"""
    emit_info(help_text)
    return True


def _handle_status(args: str) -> bool:
    """Show PRD status."""
    manager = get_state_manager()

    if not manager.prd_exists():
        emit_warning("No prd.json found in current directory.")
        emit_info(
            "Use `/ralph prd` to create a PRD, then `/ralph convert` to generate prd.json"
        )
        return True

    status = manager.get_status_summary()
    emit_info(status)

    # Also show patterns if any
    patterns = manager.read_codebase_patterns()
    if patterns and "<!--" not in patterns:  # Skip if just the placeholder
        emit_info("\n**Codebase Patterns:**")
        emit_info(patterns)

    return True


def _handle_prd(args: str) -> str:
    """Switch to PRD Generator agent."""
    emit_info("🐺 Switching to Ralph PRD Generator...")

    # Return a prompt to switch agent and start PRD generation
    return "/agent ralph-prd-generator\nI want to create a new PRD. Please help me define the requirements."


def _handle_convert(args: str) -> str:
    """Switch to Ralph Converter agent."""
    emit_info("🐺 Switching to Ralph Converter...")

    # Check if a file was specified
    if args:
        return f"/agent ralph-converter\nPlease convert the PRD in {args} to prd.json format."
    else:
        return (
            "/agent ralph-converter\nPlease help me convert my PRD to prd.json format."
        )


def _handle_start(args: str) -> str:
    """Switch to Ralph Orchestrator agent."""
    manager = get_state_manager()

    if not manager.prd_exists():
        emit_error("No prd.json found!")
        emit_info(
            "First create a PRD with `/ralph prd` and convert it with `/ralph convert`"
        )
        return True

    # Check if there's work to do
    prd = manager.read_prd()
    if prd and prd.all_complete():
        emit_success("🎉 All stories are already complete!")
        return True

    emit_info("🐺 Starting Ralph autonomous loop...")
    if prd:
        emit_info(f"📊 {prd.get_progress_summary()}")

    # Parse max iterations if provided
    max_iter = "10"
    if args:
        try:
            max_iter = str(int(args))
        except ValueError:
            pass

    # Return prompt to switch to orchestrator and start
    return (
        f"/agent ralph-orchestrator\nStart the Ralph loop. Max iterations: {max_iter}"
    )


def _handle_reset(args: str) -> bool:
    """Archive current run and reset."""
    manager = get_state_manager()

    if not manager.prd_exists():
        emit_info("Nothing to reset - no prd.json found.")
        return True

    # Archive if there's content
    progress = manager.read_progress()
    if progress and len(progress) > 100:
        archive_path = manager.archive_current_run()
        if archive_path:
            emit_success(f"📦 Archived to: {archive_path}")

    # Reset
    manager.reset_for_new_run()

    # Delete prd.json
    if manager.prd_file.exists():
        manager.prd_file.unlink()
        emit_info("🗑️ Removed prd.json")

    emit_success("✨ Reset complete! Ready for a new PRD.")
    return True
