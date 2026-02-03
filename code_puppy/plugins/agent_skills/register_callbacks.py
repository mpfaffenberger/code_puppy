"""Agent Skills plugin - registers callbacks for skill integration.

This plugin:
1. Injects available skills into system prompts
2. Registers skill-related tools
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)


def _get_skills_prompt_section() -> Optional[str]:
    """Build the skills section to inject into system prompts.

    Returns None if skills are disabled or no skills found.
    """
    from .config import get_disabled_skills, get_skill_directories, get_skills_enabled
    from .discovery import discover_skills
    from .metadata import SkillMetadata, parse_skill_metadata
    from .prompt_builder import build_available_skills_xml, build_skills_guidance

    # 1. Check if enabled
    if not get_skills_enabled():
        logger.debug("Skills integration is disabled, skipping prompt injection")
        return None

    # 2. Discover skills
    skill_dirs = [Path(d) for d in get_skill_directories()]
    discovered = discover_skills(skill_dirs)

    if not discovered:
        logger.debug("No skills discovered, skipping prompt injection")
        return None

    # 3. Parse metadata for each and filter out disabled skills
    disabled_skills = get_disabled_skills()
    skills_metadata: List[SkillMetadata] = []

    for skill_info in discovered:
        # Skip disabled skills
        if skill_info.name in disabled_skills:
            logger.debug(f"Skipping disabled skill: {skill_info.name}")
            continue

        # Only include skills with valid SKILL.md
        if not skill_info.has_skill_md:
            logger.debug(f"Skipping skill without SKILL.md: {skill_info.name}")
            continue

        # Parse metadata
        metadata = parse_skill_metadata(skill_info.path)
        if metadata:
            skills_metadata.append(metadata)
        else:
            logger.warning(f"Failed to parse metadata for skill: {skill_info.name}")

    # 4. Build XML + guidance
    if not skills_metadata:
        logger.debug("No valid skills with metadata found, skipping prompt injection")
        return None

    xml_section = build_available_skills_xml(skills_metadata)
    guidance = build_skills_guidance()

    # 5. Return combined string
    combined = f"{xml_section}\n\n{guidance}"
    logger.debug(f"Injecting skills section with {len(skills_metadata)} skills")
    return combined


def _inject_skills_into_prompt(
    model_name: str, default_system_prompt: str, user_prompt: str
) -> Optional[Dict[str, Any]]:
    """Callback to inject skills into system prompt.

    This is registered with the 'get_model_system_prompt' callback phase.
    """
    skills_section = _get_skills_prompt_section()

    if not skills_section:
        return None  # No skills, don't modify prompt

    # Append skills section to system prompt
    enhanced_prompt = f"{default_system_prompt}\n\n{skills_section}"

    return {
        "instructions": enhanced_prompt,
        "user_prompt": user_prompt,
        "handled": False,  # Let other handlers also process
    }


def _register_skills_tools() -> List[Dict[str, Any]]:
    """Callback to register skills tools.

    This is registered with the 'register_tools' callback phase.
    Returns tool definitions for the tool registry.
    """
    from code_puppy.tools.skills_tools import (
        register_activate_skill,
        register_list_or_search_skills,
    )

    return [
        {"name": "activate_skill", "register_func": register_activate_skill},
        {
            "name": "list_or_search_skills",
            "register_func": register_list_or_search_skills,
        },
    ]


# Register callbacks when plugin is loaded
register_callback("get_model_system_prompt", _inject_skills_into_prompt)
register_callback("register_tools", _register_skills_tools)

logger.info("Agent Skills plugin loaded")
