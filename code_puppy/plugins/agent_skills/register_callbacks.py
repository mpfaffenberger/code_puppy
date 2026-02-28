"""Agent Skills plugin - registers callbacks for skill integration.

This plugin:
1. Injects available skills into system prompts
2. Registers skill-related tools
3. Provides /skills slash command (and alias /skill)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


# ---------------------------------------------------------------------------
# Slash command: /skills (and alias /skill)
# ---------------------------------------------------------------------------

_COMMAND_NAME = "skills"
_ALIASES = ("skill",)


def _skills_command_help() -> List[Tuple[str, str]]:
    """Advertise /skills in the /help menu."""
    return [
        ("skills", "Manage agent skills – browse, enable, disable, install"),
        ("skill", "Alias for /skills"),
    ]


def _handle_skills_command(command: str, name: str) -> Optional[Any]:
    """Handle /skills and /skill slash commands.

    Sub-commands:
        /skills          – Launch interactive TUI menu
        /skills list     – Quick text list of all skills
        /skills install  – Browse & install from remote catalog
        /skills enable   – Enable skills integration globally
        /skills disable  – Disable skills integration globally
    """
    if name not in (_COMMAND_NAME, *_ALIASES):
        return None

    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
    from code_puppy.plugins.agent_skills.config import (
        get_disabled_skills,
        get_skills_enabled,
        set_skills_enabled,
    )
    from code_puppy.plugins.agent_skills.discovery import discover_skills
    from code_puppy.plugins.agent_skills.metadata import parse_skill_metadata
    from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

    tokens = command.split()

    if len(tokens) > 1:
        subcommand = tokens[1].lower()

        if subcommand == "list":
            disabled_skills = get_disabled_skills()
            skills = discover_skills()
            enabled = get_skills_enabled()

            if not skills:
                emit_info("No skills found.")
                emit_info("Create skills in:")
                emit_info("  - ~/.code_puppy/skills/")
                emit_info("  - ./skills/")
                return True

            emit_info(
                f"\U0001f6e0\ufe0f Skills (integration: {'enabled' if enabled else 'disabled'})"
            )
            emit_info(f"Found {len(skills)} skill(s):\n")

            for skill in skills:
                metadata = parse_skill_metadata(skill.path)
                if metadata:
                    status = (
                        "\U0001f534 disabled"
                        if metadata.name in disabled_skills
                        else "\U0001f7e2 enabled"
                    )
                    version_str = f" v{metadata.version}" if metadata.version else ""
                    author_str = f" by {metadata.author}" if metadata.author else ""
                    emit_info(f"  {status} {metadata.name}{version_str}{author_str}")
                    emit_info(f"      {metadata.description}")
                    if metadata.tags:
                        emit_info(f"      tags: {', '.join(metadata.tags)}")
                else:
                    status = (
                        "\U0001f534 disabled"
                        if skill.name in disabled_skills
                        else "\U0001f7e2 enabled"
                    )
                    emit_info(f"  {status} {skill.name}")
                    emit_info("      (no SKILL.md metadata found)")
                emit_info("")
            return True

        elif subcommand == "install":
            from code_puppy.plugins.agent_skills.skills_install_menu import (
                run_skills_install_menu,
            )

            run_skills_install_menu()
            return True

        elif subcommand == "enable":
            set_skills_enabled(True)
            emit_success("\u2705 Skills integration enabled globally")
            return True

        elif subcommand == "disable":
            set_skills_enabled(False)
            emit_warning("\U0001f534 Skills integration disabled globally")
            return True

        else:
            emit_error(f"Unknown subcommand: {subcommand}")
            emit_info("Usage: /skills [list|install|enable|disable]")
            return True

    # No subcommand – launch TUI menu
    show_skills_menu()
    return True


# ---------------------------------------------------------------------------
# Register all callbacks
# ---------------------------------------------------------------------------
register_callback("get_model_system_prompt", _inject_skills_into_prompt)
register_callback("register_tools", _register_skills_tools)
register_callback("custom_command_help", _skills_command_help)
register_callback("custom_command", _handle_skills_command)

logger.info("Agent Skills plugin loaded")
