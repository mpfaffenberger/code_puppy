"""Data models for the Ralph plugin."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class UserStory:
    """A single user story in the PRD."""

    id: str
    title: str
    description: str
    acceptance_criteria: List[str]
    priority: int
    passes: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "acceptanceCriteria": self.acceptance_criteria,
            "priority": self.priority,
            "passes": self.passes,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserStory":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            acceptance_criteria=data.get("acceptanceCriteria", []),
            priority=data.get("priority", 0),
            passes=data.get("passes", False),
            notes=data.get("notes", ""),
        )

    def has_ui_verification(self) -> bool:
        """Check if this story requires browser/UI verification."""
        ui_keywords = ["browser", "ui", "verify in browser", "qa-kitten", "visual"]
        criteria_text = " ".join(self.acceptance_criteria).lower()
        return any(kw in criteria_text for kw in ui_keywords)


@dataclass
class PRDConfig:
    """Configuration for a PRD project."""

    project: str
    branch_name: str
    description: str
    user_stories: List[UserStory] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "branchName": self.branch_name,
            "description": self.description,
            "userStories": [s.to_dict() for s in self.user_stories],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PRDConfig":
        return cls(
            project=data.get("project", ""),
            branch_name=data.get("branchName", ""),
            description=data.get("description", ""),
            user_stories=[UserStory.from_dict(s) for s in data.get("userStories", [])],
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "PRDConfig":
        return cls.from_dict(json.loads(json_str))

    def get_next_story(self) -> Optional[UserStory]:
        """Get the highest priority story that hasn't passed yet."""
        pending = [s for s in self.user_stories if not s.passes]
        if not pending:
            return None
        return min(pending, key=lambda s: s.priority)

    def all_complete(self) -> bool:
        """Check if all stories have passed."""
        return all(s.passes for s in self.user_stories)

    def get_progress_summary(self) -> str:
        """Get a summary of progress."""
        total = len(self.user_stories)
        done = sum(1 for s in self.user_stories if s.passes)
        return f"{done}/{total} stories complete"


@dataclass
class ProgressEntry:
    """An entry in the progress log."""

    timestamp: datetime
    story_id: str
    summary: str
    files_changed: List[str] = field(default_factory=list)
    learnings: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert to markdown format for progress.txt."""
        lines = [
            f"## {self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.story_id}",
            f"- {self.summary}",
        ]
        if self.files_changed:
            lines.append(f"- Files changed: {', '.join(self.files_changed)}")
        if self.learnings:
            lines.append("- **Learnings for future iterations:**")
            for learning in self.learnings:
                lines.append(f"  - {learning}")
        lines.append("---")
        return "\n".join(lines)
