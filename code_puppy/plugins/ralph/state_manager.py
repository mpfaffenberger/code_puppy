"""State management for Ralph plugin - handles prd.json and progress.txt."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from .models import PRDConfig, ProgressEntry, UserStory


class RalphStateManager:
    """Manages Ralph's persistent state files."""

    def __init__(self, working_dir: Optional[str] = None):
        """Initialize the state manager.

        Args:
            working_dir: Directory containing prd.json and progress.txt.
                        Defaults to current working directory.
        """
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.prd_file = self.working_dir / "prd.json"
        self.progress_file = self.working_dir / "progress.txt"
        self.archive_dir = self.working_dir / "archive"
        self.last_branch_file = self.working_dir / ".ralph-last-branch"

    # =========================================================================
    # PRD.JSON OPERATIONS
    # =========================================================================

    def prd_exists(self) -> bool:
        """Check if prd.json exists."""
        return self.prd_file.exists()

    def read_prd(self) -> Optional[PRDConfig]:
        """Read and parse prd.json.

        Returns:
            PRDConfig if file exists and is valid, None otherwise.
        """
        if not self.prd_file.exists():
            return None

        try:
            with open(self.prd_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PRDConfig.from_dict(data)
        except (json.JSONDecodeError, IOError):
            return None

    def write_prd(self, prd: PRDConfig) -> bool:
        """Write PRDConfig to prd.json.

        Args:
            prd: The PRD configuration to write.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with open(self.prd_file, "w", encoding="utf-8") as f:
                f.write(prd.to_json(indent=2))
            return True
        except IOError:
            return False

    def get_next_story(self) -> Optional[UserStory]:
        """Get the next story to work on.

        Returns:
            The highest priority story with passes=False, or None if all done.
        """
        prd = self.read_prd()
        if prd is None:
            return None
        return prd.get_next_story()

    def mark_story_complete(self, story_id: str, notes: str = "") -> Tuple[bool, str]:
        """Mark a story as complete (passes=True).

        Args:
            story_id: The ID of the story to mark complete.
            notes: Optional notes to add to the story.

        Returns:
            Tuple of (success, message).
        """
        prd = self.read_prd()
        if prd is None:
            return False, "No prd.json found"

        for story in prd.user_stories:
            if story.id == story_id:
                story.passes = True
                if notes:
                    story.notes = notes
                if self.write_prd(prd):
                    return True, f"Marked {story_id} as complete"
                else:
                    return False, "Failed to write prd.json"

        return False, f"Story {story_id} not found"

    def all_stories_complete(self) -> bool:
        """Check if all stories are complete."""
        prd = self.read_prd()
        if prd is None:
            return False
        return prd.all_complete()

    def get_status_summary(self) -> str:
        """Get a formatted status summary of the PRD."""
        prd = self.read_prd()
        if prd is None:
            return "No prd.json found in current directory"

        lines = [
            f"📋 **Project:** {prd.project}",
            f"🌿 **Branch:** {prd.branch_name}",
            f"📝 **Description:** {prd.description}",
            f"📊 **Progress:** {prd.get_progress_summary()}",
            "",
            "**Stories:**",
        ]

        for story in sorted(prd.user_stories, key=lambda s: s.priority):
            status = "✅" if story.passes else "⏳"
            lines.append(f"  {status} [{story.id}] {story.title}")

        return "\n".join(lines)

    # =========================================================================
    # PROGRESS.TXT OPERATIONS
    # =========================================================================

    def init_progress_file(self) -> None:
        """Initialize progress.txt with header if it doesn't exist."""
        if self.progress_file.exists():
            return

        header = f"""# Ralph Progress Log
Started: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Codebase Patterns
<!-- Add reusable patterns discovered during implementation here -->

---
"""
        with open(self.progress_file, "w", encoding="utf-8") as f:
            f.write(header)

    def append_progress(self, entry: ProgressEntry) -> bool:
        """Append a progress entry to progress.txt.

        Args:
            entry: The progress entry to append.

        Returns:
            True if successful, False otherwise.
        """
        self.init_progress_file()

        try:
            with open(self.progress_file, "a", encoding="utf-8") as f:
                f.write("\n" + entry.to_markdown() + "\n")
            return True
        except IOError:
            return False

    def read_progress(self) -> str:
        """Read the entire progress.txt file."""
        if not self.progress_file.exists():
            return ""

        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                return f.read()
        except IOError:
            return ""

    def read_codebase_patterns(self) -> str:
        """Extract the Codebase Patterns section from progress.txt."""
        content = self.read_progress()
        if not content:
            return ""

        # Find the Codebase Patterns section
        pattern_start = content.find("## Codebase Patterns")
        if pattern_start == -1:
            return ""

        # Find the end of the patterns section (next ## or ---)
        pattern_end = content.find("\n---", pattern_start)
        if pattern_end == -1:
            pattern_end = content.find("\n## ", pattern_start + 20)
        if pattern_end == -1:
            pattern_end = len(content)

        return content[pattern_start:pattern_end].strip()

    def add_codebase_pattern(self, pattern: str) -> bool:
        """Add a pattern to the Codebase Patterns section.

        Args:
            pattern: The pattern to add (e.g., "Use X for Y").

        Returns:
            True if successful, False otherwise.
        """
        self.init_progress_file()

        try:
            content = self.read_progress()

            # Find insertion point (after "## Codebase Patterns" line)
            marker = "## Codebase Patterns"
            idx = content.find(marker)
            if idx == -1:
                return False

            # Find end of that line
            line_end = content.find("\n", idx)
            if line_end == -1:
                line_end = len(content)

            # Insert the pattern
            new_line = f"\n- {pattern}"
            new_content = content[:line_end] + new_line + content[line_end:]

            with open(self.progress_file, "w", encoding="utf-8") as f:
                f.write(new_content)
            return True
        except IOError:
            return False

    # =========================================================================
    # ARCHIVING
    # =========================================================================

    def should_archive(self, new_branch: str) -> bool:
        """Check if we should archive the current run before starting a new one.

        Args:
            new_branch: The branch name for the new PRD.

        Returns:
            True if current run should be archived.
        """
        if not self.prd_file.exists():
            return False

        if not self.last_branch_file.exists():
            return False

        try:
            last_branch = self.last_branch_file.read_text().strip()
            return last_branch != new_branch and len(self.read_progress()) > 100
        except IOError:
            return False

    def archive_current_run(self) -> Optional[str]:
        """Archive the current prd.json and progress.txt.

        Returns:
            Path to the archive folder, or None if archiving failed.
        """
        prd = self.read_prd()
        if prd is None:
            return None

        # Create archive folder name
        date_str = datetime.now().strftime("%Y-%m-%d")
        folder_name = prd.branch_name.replace("ralph/", "").replace("/", "-")
        archive_folder = self.archive_dir / f"{date_str}-{folder_name}"

        try:
            archive_folder.mkdir(parents=True, exist_ok=True)

            if self.prd_file.exists():
                shutil.copy(self.prd_file, archive_folder / "prd.json")

            if self.progress_file.exists():
                shutil.copy(self.progress_file, archive_folder / "progress.txt")

            return str(archive_folder)
        except IOError:
            return None

    def update_last_branch(self, branch_name: str) -> None:
        """Update the last branch file."""
        try:
            self.last_branch_file.write_text(branch_name)
        except IOError:
            pass

    def reset_for_new_run(self) -> None:
        """Reset progress.txt for a new run."""
        if self.progress_file.exists():
            self.progress_file.unlink()
        self.init_progress_file()


# Global instance for convenience
_default_manager: Optional[RalphStateManager] = None


def get_state_manager(working_dir: Optional[str] = None) -> RalphStateManager:
    """Get the state manager instance.

    Args:
        working_dir: Optional working directory. If None, uses cwd.

    Returns:
        RalphStateManager instance.
    """
    global _default_manager
    if working_dir:
        return RalphStateManager(working_dir)
    if _default_manager is None:
        _default_manager = RalphStateManager()
    return _default_manager
