"""``skill_manage`` tool — create / patch / view / list / archive skills.

Writes ``SKILL.md`` files into the user skills store
(``~/.code_puppy/skills/<name>/SKILL.md``) using the same frontmatter format
the ``agent_skills`` plugin already discovers, so created skills show up in the
prompt index immediately.

Calling this tool is also what *unlocks* the governance budget (handled by the
post_tool_call hook in :mod:`enforcer`), recreating the Hermes onboarding loop.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel
from pydantic_ai import RunContext

logger = logging.getLogger(__name__)

_VALID_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class SkillManageOutput(BaseModel):
    """Result of a skill_manage action."""

    action: str
    skill_name: str = ""
    path: str = ""
    message: str = ""
    content: str = ""
    skills: List[dict] = []
    error: Optional[str] = None


def _user_skills_root() -> Path:
    return Path.home() / ".code_puppy" / "skills"


def _skill_dir(name: str) -> Path:
    return _user_skills_root() / name


def _render_skill_md(name: str, description: str, instructions: str) -> str:
    desc = description.replace('"', "'").strip()
    return (
        "---\n"
        f"name: {name}\n"
        f'description: "{desc}"\n'
        "version: 1.0.0\n"
        "author: code-puppy\n"
        "---\n\n"
        f"{instructions.strip()}\n"
    )


def _do_create(name: str, description: str, instructions: str) -> SkillManageOutput:
    if not _VALID_NAME.match(name):
        return SkillManageOutput(
            action="create",
            skill_name=name,
            error="Invalid name. Use lowercase letters, digits, and hyphens.",
        )
    if len((instructions or "").strip()) < 40:
        return SkillManageOutput(
            action="create",
            skill_name=name,
            error="Instructions too short — provide a real, reusable procedure.",
        )
    skill_dir = _skill_dir(name)
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        return SkillManageOutput(
            action="create",
            skill_name=name,
            error=f"Skill '{name}' already exists. Use action='patch' to update it.",
        )
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(
        _render_skill_md(name, description, instructions), encoding="utf-8"
    )
    return SkillManageOutput(
        action="create",
        skill_name=name,
        path=str(skill_md),
        message=f"Created skill '{name}'.",
    )


def _do_patch(name: str, description: str, instructions: str) -> SkillManageOutput:
    skill_md = _skill_dir(name) / "SKILL.md"
    if not skill_md.exists():
        return SkillManageOutput(
            action="patch",
            skill_name=name,
            error=f"Skill '{name}' not found. Use action='create' first.",
        )
    # Re-render with provided fields; bump patch version if we can parse it.
    existing = skill_md.read_text(encoding="utf-8")
    version = "1.0.1"
    m = re.search(r"^version:\s*(\d+)\.(\d+)\.(\d+)", existing, re.MULTILINE)
    if m:
        version = f"{m.group(1)}.{m.group(2)}.{int(m.group(3)) + 1}"
    desc = (description or "").replace('"', "'").strip()
    body = (instructions or "").strip()
    content = (
        "---\n"
        f"name: {name}\n"
        f'description: "{desc}"\n'
        f"version: {version}\n"
        "author: code-puppy\n"
        "---\n\n"
        f"{body}\n"
    )
    skill_md.write_text(content, encoding="utf-8")
    return SkillManageOutput(
        action="patch",
        skill_name=name,
        path=str(skill_md),
        message=f"Patched skill '{name}' (version {version}).",
    )


def _do_view(name: str) -> SkillManageOutput:
    skill_md = _skill_dir(name) / "SKILL.md"
    if not skill_md.exists():
        return SkillManageOutput(
            action="view", skill_name=name, error=f"Skill '{name}' not found."
        )
    return SkillManageOutput(
        action="view",
        skill_name=name,
        path=str(skill_md),
        content=skill_md.read_text(encoding="utf-8"),
    )


def _do_list() -> SkillManageOutput:
    from code_puppy.plugins.agent_skills.config import get_skill_directories
    from code_puppy.plugins.agent_skills.discovery import discover_skills
    from code_puppy.plugins.agent_skills.metadata import parse_skill_metadata

    dirs = [Path(d) for d in get_skill_directories()]
    discovered = discover_skills(dirs)
    skills: List[dict] = []
    for info in discovered:
        if not info.has_skill_md:
            continue
        meta = parse_skill_metadata(info.path)
        skills.append(
            {
                "name": info.name,
                "description": getattr(meta, "description", "") if meta else "",
                "path": str(info.path),
            }
        )
    return SkillManageOutput(
        action="list", skills=skills, message=f"{len(skills)} skill(s) found."
    )


def _do_archive(name: str) -> SkillManageOutput:
    skill_dir = _skill_dir(name)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return SkillManageOutput(
            action="archive", skill_name=name, error=f"Skill '{name}' not found."
        )
    archive_root = _user_skills_root() / ".archived"
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / name
    if target.exists():
        import shutil

        shutil.rmtree(target, ignore_errors=True)
    skill_dir.rename(target)
    return SkillManageOutput(
        action="archive",
        skill_name=name,
        path=str(target),
        message=f"Archived skill '{name}'.",
    )


def register_skill_manage(agent):
    """Register the skill_manage tool on the agent."""

    @agent.tool
    async def skill_manage(
        context: RunContext,
        action: str = "list",
        name: str = "",
        description: str = "",
        instructions: str = "",
    ) -> SkillManageOutput:
        """Create, patch, view, list, or archive a reusable skill.

        action="create"  : write a new SKILL.md (needs name + instructions)
        action="patch"   : update an existing skill (needs name + instructions)
        action="view"    : return a skill's full SKILL.md (needs name)
        action="list"    : list all discoverable skills
        action="archive" : move a skill to ~/.code_puppy/skills/.archived/
        """
        act = (action or "list").strip().lower()
        try:
            if act == "create":
                return _do_create(name.strip(), description, instructions)
            if act == "patch":
                return _do_patch(name.strip(), description, instructions)
            if act == "view":
                return _do_view(name.strip())
            if act == "list":
                return _do_list()
            if act == "archive":
                return _do_archive(name.strip())
            return SkillManageOutput(
                action=act,
                error="Unknown action. Use create|patch|view|list|archive.",
            )
        except Exception as e:  # never crash the agent loop
            logger.error("skill_manage failed: %s", e, exc_info=True)
            return SkillManageOutput(action=act, skill_name=name, error=str(e))
