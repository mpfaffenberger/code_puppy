"""Agent Skills plugin - registers callbacks for skill integration.

This plugin:
1. Injects available skills into system prompts
2. Registers skill-related tools
3. Provides /skills slash command (and alias /skill)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)


def _get_skills_prompt_section() -> Optional[str]:
    """Build the skills section to inject into system prompts.

    Returns None if skills are disabled or no enabled skills exist.
    Disabled skills never have their frontmatter loaded — see
    :mod:`code_puppy.plugins.agent_skills.enabled_skills`.

    When ``frontmatter_in_system_prompt`` is ``False``, the per-skill list is
    omitted but the short guidance line is still emitted so the model knows
    the ``activate_skill`` / ``list_or_search_skills`` mechanism exists.
    """
    from .config import get_frontmatter_in_system_prompt
    from .enabled_skills import list_enabled_skill_metadata
    from .prompt_builder import build_available_skills_block, build_skills_guidance

    skills_metadata = list_enabled_skill_metadata()
    if not skills_metadata:
        logger.debug("No enabled skills with metadata found, skipping prompt injection")
        return None

    guidance = build_skills_guidance()

    if not get_frontmatter_in_system_prompt():
        logger.debug(
            "Frontmatter injection disabled; emitting guidance line only "
            f"({len(skills_metadata)} skills hidden from system prompt)"
        )
        return guidance

    skills_block = build_available_skills_block(skills_metadata)
    logger.debug(f"Injecting skills section with {len(skills_metadata)} skills")
    return f"{skills_block}\n\n{guidance}"


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
    """Advertise /skills (+ every individual skill) in the /help menu."""
    from .skill_commands import skill_command_help

    entries: List[Tuple[str, str]] = [
        ("skills", "Manage agent skills – browse, enable, disable, install"),
        ("skill", "Alias for /skills"),
    ]
    # Append per-skill commands so they show up in /help & tab-completion.
    entries.extend(skill_command_help())
    return entries


def _handle_skills_command(command: str, name: str) -> Optional[Any]:
    """Handle /skills and /skill slash commands.

    Sub-commands:
        /skills          – Launch interactive TUI menu
        /skills list     – Quick text list of all skills
        /skills install  – Browse & install from remote catalog
        /skills enable   – Enable skills integration globally
        /skills disable  – Disable skills integration globally
        /skills toggle   – Toggle skills integration globally
        /skills refresh  – Force skill re-discovery and refresh local cache
        /skills help     – Show skills command help
    """
    if name not in (_COMMAND_NAME, *_ALIASES):
        # Not the /skills meta-command — maybe it's an individual skill?
        from .skill_commands import handle_skill_command

        return handle_skill_command(command, name)

    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
    from code_puppy.plugins.agent_skills.config import (
        get_disabled_skills,
        get_frontmatter_in_system_prompt,
        get_skills_enabled,
        set_frontmatter_in_system_prompt,
        set_skills_enabled,
    )
    from code_puppy.plugins.agent_skills.discovery import (
        discover_skills,
        refresh_skill_cache,
    )
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
                emit_info("  - ~/.mist/skills/")
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

        elif subcommand == "toggle":
            new_state = not get_skills_enabled()
            set_skills_enabled(new_state)
            if new_state:
                emit_success("✅ Skills integration enabled globally")
            else:
                emit_warning("🔴 Skills integration disabled globally")
            return True

        elif subcommand == "frontmatter":
            # /skills frontmatter [on|off|toggle]   (no arg = show state)
            arg = tokens[2].lower() if len(tokens) > 2 else None
            current = get_frontmatter_in_system_prompt()

            if arg in ("on", "enable", "true"):
                new_state = True
            elif arg in ("off", "disable", "false"):
                new_state = False
            elif arg == "toggle":
                new_state = not current
            elif arg is None:
                emit_info(
                    f"Skill frontmatter in system prompt: "
                    f"{'🟢 on' if current else '🔴 off'}"
                )
                emit_info("Usage: /skills frontmatter [on|off|toggle]")
                return True
            else:
                emit_error(f"Unknown frontmatter arg: {arg}")
                emit_info("Usage: /skills frontmatter [on|off|toggle]")
                return True

            set_frontmatter_in_system_prompt(new_state)
            if new_state:
                emit_success(
                    "✅ Skill frontmatter will be injected into system prompts"
                )
            else:
                emit_warning(
                    "🔴 Skill frontmatter hidden from system prompts "
                    "(model can still call activate_skill / list_or_search_skills)"
                )
            return True

        elif subcommand == "refresh":
            refreshed = refresh_skill_cache()
            valid_skills = [skill for skill in refreshed if skill.has_skill_md]
            emit_success(
                f"🔄 Refreshed skills cache: {len(refreshed)} discovered "
                f"({len(valid_skills)} with SKILL.md)"
            )
            return True

        elif subcommand == "help":
            emit_info("Available /skills subcommands:")
            emit_info("  /skills list     - List all installed skills")
            emit_info("  /skills install  - Browse & install from catalog")
            emit_info("  /skills enable   - Enable skills integration globally")
            emit_info("  /skills disable  - Disable skills integration globally")
            emit_info("  /skills toggle   - Toggle skills integration globally")
            emit_info(
                "  /skills frontmatter [on|off|toggle] - Toggle skill list injection into system prompt"
            )
            emit_info("  /skills refresh  - Refresh skill cache")
            emit_info("  /skills          - Open interactive skills menu")
            return True

        else:
            emit_error(f"Unknown subcommand: {subcommand}")
            emit_info(
                "Usage: /skills [list|install|enable|disable|toggle|frontmatter|refresh|help]"
            )
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
