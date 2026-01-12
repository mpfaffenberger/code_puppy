"""Data types for the Skills Plugin."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkillMetadata:
    """Metadata extracted from a SKILL.md file's YAML frontmatter.

    Attributes:
        name: Skill identifier (kebab-case, e.g., 'pdf-processor')
        description: What the skill does and when to trigger it
        path: Path to the skill directory containing SKILL.md
        license: Optional license information
    """

    name: str
    description: str
    path: Path
    license: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize fields after initialization."""
        if not self.name or not self.name.strip():
            raise ValueError("Skill name cannot be empty")
        if not self.description or not self.description.strip():
            raise ValueError("Skill description cannot be empty")
        # Convert string path to Path object if needed
        if isinstance(self.path, str):
            self.path = Path(self.path)
