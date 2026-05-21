"""Per-skill slash commands.

Each discovered (and enabled) skill is exposed as a ``/<skill-name>`` slash
command.  Invoking it loads the full ``SKILL.md`` content and submits it
as the prompt — effectively the same thing the ``activate_skill`` tool
does, only initiated by the user.

This lives in its own module so that ``register_callbacks.py`` stays
focused on wiring callbacks (SRP, and the file-size cap).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional, Tuple

from code_puppy.messaging import emit_info

logger = logging.getLogger(__name__)

# Slash command names already owned by the skills plugin itself.
# We must never shadow them with a per-skill command.
_RESERVED_NAMES = {"skills", "skill"}


def _iter_enabled_skills():
    """Yield ``SkillMetadata`` for every enabled, valid skill."""
    from .config import (
        get_disabled_skills,
        get_skill_directories,
        get_skills_enabled,
    )
    from .discovery import discover_skills
    from .metadata import parse_skill_metadata

    if not get_skills_enabled():
        return

    disabled = get_disabled_skills()
    skill_dirs = [Path(d) for d in get_skill_directories()]
    for info in discover_skills(skill_dirs):
        if not info.has_skill_md:
            continue
        if info.name in disabled:
            continue
        if info.name in _RESERVED_NAMES:
            logger.debug(
                "Skipping skill %r: name collides with reserved slash command",
                info.name,
            )
            continue
        meta = parse_skill_metadata(info.path)
        if meta is not None:
            yield meta


def skill_command_help() -> List[Tuple[str, str]]:
    """Advertise every enabled skill in the ``/help`` menu."""
    entries: List[Tuple[str, str]] = []
    for meta in _iter_enabled_skills():
        desc = meta.description or "(no description)"
        # Trim ridiculously long descriptions for the help table.
        if len(desc) > 80:
            desc = desc[:77] + "..."
        entries.append((meta.name, f"🛠️  Skill: {desc}"))
    return entries


def handle_skill_command(command: str, name: str) -> Optional[Any]:
    """Return the SKILL.md content as a MarkdownCommandResult if ``name``
    matches an enabled skill, otherwise ``None``.

    Extra args after the command are appended as ``Additional context:``,
    mirroring the customizable_commands plugin's contract.
    """
    if not name or name in _RESERVED_NAMES:
        return None

    # Lazy import to avoid a hard dependency on customizable_commands at
    # plugin load time (and to keep things tidy if it ever moves).
    try:
        from code_puppy.plugins.customizable_commands.register_callbacks import (
            MarkdownCommandResult,
        )
    except ImportError:
        logger.debug("MarkdownCommandResult unavailable; cannot run skill via slash")
        return None

    # Find a matching enabled skill.
    match = next((m for m in _iter_enabled_skills() if m.name == name), None)
    if match is None:
        return None

    from .metadata import load_full_skill_content

    content = load_full_skill_content(match.path)
    if not content:
        logger.warning("Failed to load SKILL.md for %s", match.name)
        return None

    # Allow user to pass freeform args after the slash command.
    parts = command.split(maxsplit=1)
    args = parts[1].strip() if len(parts) > 1 else ""

    header = (
        f"You are activating the '{match.name}' skill. Follow its "
        f"SKILL.md instructions below verbatim.\n\n"
    )
    prompt = header + content
    if args:
        prompt = f"{prompt}\n\nAdditional context: {args}"

    emit_info(f"🛠️  Activating skill via slash command: {match.name}")
    return MarkdownCommandResult(prompt)
