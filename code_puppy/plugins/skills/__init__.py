"""Skills Plugin for Code Puppy - Claude Code compatible skill support."""

from code_puppy.plugins.skills.skill_loader import SkillLoader, SkillLoaderError
from code_puppy.plugins.skills.skill_manager import SkillManager
from code_puppy.plugins.skills.skill_types import SkillMetadata

__all__ = ["SkillMetadata", "SkillLoader", "SkillLoaderError", "SkillManager"]
