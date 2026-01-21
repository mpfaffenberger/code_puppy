"""Ralph plugin tools - registered via the register_tools callback."""

from dataclasses import dataclass
from datetime import datetime
from typing import List

from pydantic_ai import RunContext

from .models import ProgressEntry
from .state_manager import get_state_manager

# ============================================================================
# TOOL OUTPUT TYPES
# ============================================================================


@dataclass
class RalphStoryOutput:
    """Output for getting the current story."""

    story_id: str | None
    title: str | None
    description: str | None
    acceptance_criteria: List[str]
    priority: int | None
    requires_ui_verification: bool
    all_complete: bool
    error: str | None = None


@dataclass
class RalphStatusOutput:
    """Output for status checks."""

    success: bool
    message: str
    progress_summary: str | None = None
    stories_remaining: int = 0
    all_complete: bool = False


@dataclass
class RalphPRDOutput:
    """Output for reading the full PRD."""

    success: bool
    project: str | None = None
    branch_name: str | None = None
    description: str | None = None
    stories: List[dict] | None = None
    progress_summary: str | None = None
    error: str | None = None


@dataclass
class RalphPatternsOutput:
    """Output for reading codebase patterns."""

    patterns: str
    has_patterns: bool


# ============================================================================
# TOOL REGISTRATION FUNCTIONS
# ============================================================================


def register_ralph_get_current_story(agent) -> None:
    """Register the tool to get the current story to work on."""

    @agent.tool
    def ralph_get_current_story(context: RunContext) -> RalphStoryOutput:
        """Get the next user story to work on from prd.json.

        This tool reads the prd.json file and returns the highest-priority
        story that hasn't been completed yet (passes=false).

        Returns:
            RalphStoryOutput containing:
            - story_id: The story ID (e.g., "US-001")
            - title: Story title
            - description: Full story description
            - acceptance_criteria: List of criteria to satisfy
            - priority: Story priority (lower = higher priority)
            - requires_ui_verification: True if story needs browser testing
            - all_complete: True if ALL stories are done
            - error: Error message if something went wrong
        """
        manager = get_state_manager()

        if not manager.prd_exists():
            return RalphStoryOutput(
                story_id=None,
                title=None,
                description=None,
                acceptance_criteria=[],
                priority=None,
                requires_ui_verification=False,
                all_complete=False,
                error="No prd.json found in current directory. Create one first with /ralph prd",
            )

        if manager.all_stories_complete():
            return RalphStoryOutput(
                story_id=None,
                title=None,
                description=None,
                acceptance_criteria=[],
                priority=None,
                requires_ui_verification=False,
                all_complete=True,
                error=None,
            )

        story = manager.get_next_story()
        if story is None:
            return RalphStoryOutput(
                story_id=None,
                title=None,
                description=None,
                acceptance_criteria=[],
                priority=None,
                requires_ui_verification=False,
                all_complete=True,
                error=None,
            )

        return RalphStoryOutput(
            story_id=story.id,
            title=story.title,
            description=story.description,
            acceptance_criteria=story.acceptance_criteria,
            priority=story.priority,
            requires_ui_verification=story.has_ui_verification(),
            all_complete=False,
            error=None,
        )


def register_ralph_mark_story_complete(agent) -> None:
    """Register the tool to mark a story as complete."""

    @agent.tool
    def ralph_mark_story_complete(
        context: RunContext,
        story_id: str,
        notes: str | None = None,
    ) -> RalphStatusOutput:
        """Mark a user story as complete (passes=true) in prd.json.

        Call this AFTER you have:
        1. Implemented all the acceptance criteria
        2. Verified the code compiles/typechecks
        3. Run any required tests
        4. Committed the changes

        For UI stories, also ensure browser verification passed.

        Args:
            story_id: The story ID to mark complete (e.g., "US-001")
            notes: Optional notes about the implementation

        Returns:
            RalphStatusOutput with success status and message
        """
        manager = get_state_manager()

        success, message = manager.mark_story_complete(story_id, notes or "")

        prd = manager.read_prd()
        remaining = 0
        all_complete = False
        progress = None

        if prd:
            remaining = sum(1 for s in prd.user_stories if not s.passes)
            all_complete = prd.all_complete()
            progress = prd.get_progress_summary()

        return RalphStatusOutput(
            success=success,
            message=message,
            progress_summary=progress,
            stories_remaining=remaining,
            all_complete=all_complete,
        )


def register_ralph_log_progress(agent) -> None:
    """Register the tool to log progress to progress.txt."""

    @agent.tool
    def ralph_log_progress(
        context: RunContext,
        story_id: str,
        summary: str,
        files_changed: List[str] | None = None,
        learnings: List[str] | None = None,
    ) -> RalphStatusOutput:
        """Append a progress entry to progress.txt.

        Call this after completing a story to record:
        - What was implemented
        - Which files were changed
        - Any learnings for future iterations

        The learnings are especially important for helping future iterations
        understand patterns and avoid mistakes.

        Args:
            story_id: The story ID that was completed
            summary: Brief summary of what was implemented
            files_changed: List of files that were modified
            learnings: List of learnings/patterns discovered

        Returns:
            RalphStatusOutput with success status
        """
        manager = get_state_manager()

        entry = ProgressEntry(
            timestamp=datetime.now(),
            story_id=story_id,
            summary=summary,
            files_changed=files_changed or [],
            learnings=learnings or [],
        )

        success = manager.append_progress(entry)

        return RalphStatusOutput(
            success=success,
            message="Progress logged successfully"
            if success
            else "Failed to log progress",
        )


def register_ralph_check_all_complete(agent) -> None:
    """Register the tool to check if all stories are complete."""

    @agent.tool
    def ralph_check_all_complete(context: RunContext) -> RalphStatusOutput:
        """Check if all user stories in prd.json are complete.

        Use this to determine if the Ralph loop should exit.
        When all stories are complete, you should output:
        <promise>COMPLETE</promise>

        Returns:
            RalphStatusOutput with all_complete flag
        """
        manager = get_state_manager()

        if not manager.prd_exists():
            return RalphStatusOutput(
                success=False,
                message="No prd.json found",
                all_complete=False,
            )

        prd = manager.read_prd()
        if prd is None:
            return RalphStatusOutput(
                success=False,
                message="Failed to read prd.json",
                all_complete=False,
            )

        all_complete = prd.all_complete()
        remaining = sum(1 for s in prd.user_stories if not s.passes)

        return RalphStatusOutput(
            success=True,
            message="All stories complete!"
            if all_complete
            else f"{remaining} stories remaining",
            progress_summary=prd.get_progress_summary(),
            stories_remaining=remaining,
            all_complete=all_complete,
        )


def register_ralph_read_prd(agent) -> None:
    """Register the tool to read the full PRD."""

    @agent.tool
    def ralph_read_prd(context: RunContext) -> RalphPRDOutput:
        """Read the full prd.json file and return its contents.

        Use this to understand the overall project and see all stories.

        Returns:
            RalphPRDOutput with project details and all stories
        """
        manager = get_state_manager()

        if not manager.prd_exists():
            return RalphPRDOutput(
                success=False,
                error="No prd.json found in current directory",
            )

        prd = manager.read_prd()
        if prd is None:
            return RalphPRDOutput(
                success=False,
                error="Failed to parse prd.json",
            )

        return RalphPRDOutput(
            success=True,
            project=prd.project,
            branch_name=prd.branch_name,
            description=prd.description,
            stories=[s.to_dict() for s in prd.user_stories],
            progress_summary=prd.get_progress_summary(),
        )


def register_ralph_read_patterns(agent) -> None:
    """Register the tool to read codebase patterns from progress.txt."""

    @agent.tool
    def ralph_read_patterns(context: RunContext) -> RalphPatternsOutput:
        """Read the Codebase Patterns section from progress.txt.

        These patterns were discovered by previous iterations and contain
        important context about the codebase. Read this BEFORE starting
        work on a new story.

        Returns:
            RalphPatternsOutput with patterns text
        """
        manager = get_state_manager()
        patterns = manager.read_codebase_patterns()

        return RalphPatternsOutput(
            patterns=patterns if patterns else "No patterns recorded yet.",
            has_patterns=bool(patterns),
        )


def register_ralph_add_pattern(agent) -> None:
    """Register the tool to add a codebase pattern."""

    @agent.tool
    def ralph_add_pattern(context: RunContext, pattern: str) -> RalphStatusOutput:
        """Add a reusable pattern to the Codebase Patterns section.

        Only add patterns that are GENERAL and REUSABLE, not story-specific.

        Good examples:
        - "Use `sql<number>` template for aggregations"
        - "Always use `IF NOT EXISTS` for migrations"
        - "Export types from actions.ts for UI components"

        Bad examples (too specific):
        - "Added login button to header" (story-specific)
        - "Fixed bug in user.ts" (not a pattern)

        Args:
            pattern: The pattern to record

        Returns:
            RalphStatusOutput with success status
        """
        manager = get_state_manager()
        success = manager.add_codebase_pattern(pattern)

        return RalphStatusOutput(
            success=success,
            message="Pattern added" if success else "Failed to add pattern",
        )


# ============================================================================
# TOOL PROVIDER FOR CALLBACK
# ============================================================================


def get_ralph_tools() -> List[dict]:
    """Get all Ralph tools for registration via the register_tools callback.

    Returns:
        List of tool definitions with name and register_func.
    """
    return [
        {
            "name": "ralph_get_current_story",
            "register_func": register_ralph_get_current_story,
        },
        {
            "name": "ralph_mark_story_complete",
            "register_func": register_ralph_mark_story_complete,
        },
        {"name": "ralph_log_progress", "register_func": register_ralph_log_progress},
        {
            "name": "ralph_check_all_complete",
            "register_func": register_ralph_check_all_complete,
        },
        {"name": "ralph_read_prd", "register_func": register_ralph_read_prd},
        {"name": "ralph_read_patterns", "register_func": register_ralph_read_patterns},
        {"name": "ralph_add_pattern", "register_func": register_ralph_add_pattern},
    ]
