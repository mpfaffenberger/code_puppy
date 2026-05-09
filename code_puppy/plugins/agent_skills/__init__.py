"""Agent Skills plugin - dynamic skill loading and discovery.

This plugin enables code_puppy to discover, load, and use custom skills
defined in SKILL.md files. Skills can be placed in user-specific or
project-specific directories for easy sharing and organization.
"""

from .discovery import (
    MAX_SKILL_MD_BYTES,
    SKILL_CONTEXT_CAP,
    SkillInfo,
    cap_skill_content,
)
from .metadata import (
    SkillMetadata,
    get_skill_resources,
    load_full_skill_content,
    parse_skill_metadata,
    parse_yaml_frontmatter,
)

__all__ = [
    "SkillInfo",
    "SkillMetadata",
    "MAX_SKILL_MD_BYTES",
    "SKILL_CONTEXT_CAP",
    "cap_skill_content",
    "parse_yaml_frontmatter",
    "parse_skill_metadata",
    "load_full_skill_content",
    "get_skill_resources",
]
