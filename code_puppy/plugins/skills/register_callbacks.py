"""Skills Plugin for Code Puppy.

Provides Claude Code-compatible skill support through the plugin system.
Registers callbacks for startup, commands, and prompt injection.
"""

import logging
from pathlib import Path

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info, emit_warning
from code_puppy.plugins.skills.skill_manager import SkillManager

logger = logging.getLogger(__name__)

# Global skill manager instance (lazy initialization)
_skill_manager: SkillManager | None = None


def _get_manager() -> SkillManager:
    """Get or create the global SkillManager instance.

    Note: This uses simple lazy initialization. Thread-safety is not a concern
    because Code Puppy's CLI is single-threaded and callbacks are invoked
    sequentially from the main event loop.
    """
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager


# ================================================================
# CALLBACK: startup
# ================================================================
async def _on_startup() -> None:
    """Initialize skill manager and show loaded count."""
    try:
        manager = _get_manager()
        count = manager.get_skill_count()
        if count > 0:
            emit_info(f"📚 Skills plugin: Loaded {count} skill(s)")
    except Exception as e:
        logger.warning("Skills plugin failed to initialize: %s", e)


# ================================================================
# CALLBACK: custom_command_help
# ================================================================
def _skill_help() -> list[tuple[str, str]]:
    """Return help entries for /skill commands."""
    return [
        ("skill", "Manage skills: /skill list|info|add|remove|refresh|show"),
        ("skill list", "List all installed skills"),
        ("skill info <name>", "Show skill details and metadata"),
        ("skill add <path>", "Install a skill from directory"),
        ("skill remove <name>", "Remove an installed skill"),
        ("skill refresh", "Rescan the skills directory"),
        ("skill show <name>", "Display the full SKILL.md content"),
    ]


# ================================================================
# CALLBACK: custom_command
# ================================================================
def _handle_skill_command(command: str, name: str) -> str | None:
    """Handle /skill commands.

    Args:
        command: Full command string (e.g., "skill list")
        name: Command name (e.g., "skill")

    Returns:
        Command result if handled, None if not our command
    """
    if name != "skill":
        return None  # Not our command

    parts = command.split()
    subcommand = parts[1] if len(parts) > 1 else "help"
    args = parts[2:] if len(parts) > 2 else []

    manager = _get_manager()

    if subcommand == "list":
        return _cmd_list(manager)
    elif subcommand == "info" and args:
        return _cmd_info(manager, args[0])
    elif subcommand == "add" and args:
        return _cmd_add(manager, " ".join(args))  # Handle paths with spaces
    elif subcommand == "remove" and args:
        return _cmd_remove(manager, args[0])
    elif subcommand == "refresh":
        return _cmd_refresh(manager)
    elif subcommand == "show" and args:
        return _cmd_show(manager, args[0])
    else:
        return _cmd_help()


def _cmd_help() -> str:
    """Show skill command help."""
    return """📚 **Skills Plugin**

Manage Claude Code-compatible skills for enhanced AI capabilities.

**Commands:**
  /skill list              List all installed skills
  /skill info <name>       Show skill details and metadata
  /skill add <path>        Install a skill from directory
  /skill remove <name>     Remove an installed skill
  /skill refresh           Rescan the skills directory
  /skill show <name>       Display the full SKILL.md content

**Skills Location:** ~/.code_puppy/skills/
"""


def _cmd_list(manager: SkillManager) -> str:
    """List installed skills."""
    skills = manager.list_skills()

    if not skills:
        return (
            "📚 **No skills installed**\n\nUse `/skill add <path>` to install a skill."
        )

    lines = [f"📚 **Installed Skills ({len(skills)})**\n"]
    for skill in skills:
        desc = skill.description
        if len(desc) > 60:
            desc = desc[:57] + "..."
        lines.append(f"  **{skill.name}** - {desc}")

    lines.append("\nUse `/skill info <name>` for details.")
    return "\n".join(lines)


def _cmd_info(manager: SkillManager, name: str) -> str:
    """Show skill details."""
    info = manager.get_skill_info(name)

    if info is None:
        emit_warning(f"Skill '{name}' not found")
        return f"❌ Skill '{name}' not found"

    lines = [
        f"📚 **Skill: {info['name']}**\n",
        f"**Description:** {info['description']}",
        f"**Path:** `{info['path']}`",
    ]
    if info.get("license"):
        lines.append(f"**License:** {info['license']}")

    lines.append(f"\nUse `/skill show {name}` to see full documentation.")
    return "\n".join(lines)


def _cmd_add(manager: SkillManager, path_str: str) -> str:
    """Install a skill."""
    path = Path(path_str).expanduser()
    success, message = manager.add_skill(path)

    if success:
        emit_info(message)
        return f"✅ {message}"
    else:
        emit_warning(message)
        return f"❌ {message}"


def _cmd_remove(manager: SkillManager, name: str) -> str:
    """Remove a skill."""
    success, message = manager.remove_skill(name)

    if success:
        emit_info(message)
        return f"✅ {message}"
    else:
        emit_warning(message)
        return f"❌ {message}"


def _cmd_refresh(manager: SkillManager) -> str:
    """Refresh skill catalog."""
    count = manager.refresh()
    msg = f"📚 Rescanned skills directory. Found {count} skill(s)."
    emit_info(msg)
    return msg


def _cmd_show(manager: SkillManager, name: str) -> str:
    """Show full skill content."""
    body = manager.load_skill_body(name)

    if body is None:
        emit_warning(f"Skill '{name}' not found")
        return f"❌ Skill '{name}' not found"

    return f"📚 **SKILL.md for {name}**\n\n{body}"


# ================================================================
# CALLBACK: load_prompt
# ================================================================
def _inject_skill_catalog() -> str | None:
    """Inject skill catalog into system prompt."""
    manager = _get_manager()
    catalog = manager.get_skill_catalog()

    if not catalog:
        return None

    return f"""

## Available Skills

You have access to specialized skills. When a task matches a skill's
expertise, you can ask to see its detailed instructions.

**Installed Skills:**
{catalog}

To use a skill, mention "I'll use the [skill-name] skill for this task"
and request the full documentation if needed.
"""


# ================================================================
# REGISTER ALL CALLBACKS
# ================================================================
register_callback("startup", _on_startup)
register_callback("custom_command_help", _skill_help)
register_callback("custom_command", _handle_skill_command)
register_callback("load_prompt", _inject_skill_catalog)
