"""Skills tools - dedicated tools for Agent Skills integration."""

import logging
from typing import List, Optional

from pydantic import BaseModel
from pydantic_ai import RunContext

from code_puppy.messaging import (
    SkillActivateMessage,
    SkillEntry,
    SkillListMessage,
    get_message_bus,
)

logger = logging.getLogger(__name__)


def _skill_haystack(skill: dict) -> str:
    """Lowercased blob of a skill's searchable text (name + desc + tags)."""
    return (
        skill["name"] + " " + skill["description"] + " " + " ".join(skill["tags"])
    ).lower()


# Output models
class SkillListOutput(BaseModel):
    """Output for list_or_search_skills tool."""

    skills: List[dict]  # Each has: name, description, path, tags
    total_count: int
    query: Optional[str] = None  # The search query if provided
    error: Optional[str] = None


class SkillActivateOutput(BaseModel):
    """Output for activate_skill tool."""

    skill_name: str
    content: str  # Full SKILL.md content
    resources: List[str]  # Available resource files
    error: Optional[str] = None


def register_activate_skill(agent):
    """Register the activate_skill tool."""

    @agent.tool
    async def activate_skill(
        context: RunContext, skill_name: str = ""
    ) -> SkillActivateOutput:
        """Activate a skill by loading its full SKILL.md instructions."""
        # Import from plugin
        from code_puppy.plugins.agent_skills.config import get_skills_enabled
        from code_puppy.plugins.agent_skills.enabled_skills import iter_enabled_skills
        from code_puppy.plugins.agent_skills.metadata import (
            get_skill_resources,
            load_full_skill_content,
        )

        # Check if skills enabled
        if not get_skills_enabled():
            return SkillActivateOutput(
                skill_name=skill_name,
                content="",
                resources=[],
                error="Skills integration is disabled. Enable it with /set skills_enabled=true",
            )

        # Find skill by name among *enabled* skills only — disabled skills
        # are intentionally invisible to activate_skill.
        try:
            skill_path = next(
                (
                    info.path
                    for info in iter_enabled_skills()
                    if info.name == skill_name
                ),
                None,
            )
        except Exception as e:
            logger.error(f"Failed to discover skills: {e}")
            return SkillActivateOutput(
                skill_name=skill_name,
                content="",
                resources=[],
                error=f"Failed to discover skills: {e}",
            )

        if not skill_path:
            return SkillActivateOutput(
                skill_name=skill_name,
                content="",
                resources=[],
                error=f"Skill '{skill_name}' not found or disabled. Use list_or_search_skills to see available skills.",
            )

        # Load full content
        content = load_full_skill_content(skill_path)
        if content is None:
            return SkillActivateOutput(
                skill_name=skill_name,
                content="",
                resources=[],
                error=f"Failed to load content for skill '{skill_name}'",
            )

        # Get resource list
        resource_paths = get_skill_resources(skill_path)
        resources = [str(p) for p in resource_paths]

        # Emit message for UI
        content_preview = content[:200] if content else ""
        skill_msg = SkillActivateMessage(
            skill_name=skill_name,
            skill_path=str(skill_path),
            content_preview=content_preview,
            resource_count=len(resources),
            success=True,
        )
        get_message_bus().emit(skill_msg)

        return SkillActivateOutput(
            skill_name=skill_name, content=content, resources=resources, error=None
        )

    return activate_skill


def register_list_or_search_skills(agent):
    """Register the list_or_search_skills tool."""

    @agent.tool
    async def list_or_search_skills(
        context: RunContext, query: Optional[str] = None
    ) -> SkillListOutput:
        """List available skills, optionally filtered by search query.

        Args:
            query: Optional search term to filter skills by name/description/tags.
                   If None, returns all available skills.
        """
        # Import from plugin
        from code_puppy.plugins.agent_skills.config import (
            get_disabled_skills,
            get_skills_enabled,
        )
        from code_puppy.plugins.agent_skills.enabled_skills import (
            list_enabled_skill_metadata,
        )

        # Check if skills enabled
        if not get_skills_enabled():
            return SkillListOutput(
                skills=[],
                total_count=0,
                query=query,
                error="Skills integration is disabled. Enable it with /set skills_enabled=true",
            )

        # We still need disabled_skills for the SkillEntry.enabled flag below,
        # even though the helper has already filtered them out of the list.
        disabled_skills = get_disabled_skills()

        # Get enabled skills with metadata (disabled skills never get their
        # frontmatter loaded — that's enforced inside the helper).
        try:
            metadatas = list_enabled_skill_metadata()
        except Exception as e:
            logger.error(f"Failed to discover skills: {e}")
            return SkillListOutput(
                skills=[],
                total_count=0,
                query=query,
                error=f"Failed to discover skills: {e}",
            )

        skills_list = [
            {
                "name": m.name,
                "description": m.description,
                "path": str(m.path),
                "tags": m.tags,
                "version": m.version,
                "author": m.author,
            }
            for m in metadatas
        ]

        # Filter by query — match if ANY term appears in the skill's name,
        # description, or tags. Avoids the old bug where the entire query was
        # treated as one substring (so "code puppy architecture" matched nothing).
        if query:
            terms = query.lower().replace("-", " ").replace("_", " ").split()
            skills_list = [
                s
                for s in skills_list
                if any(term in _skill_haystack(s) for term in terms)
            ]

        # Emit message for UI
        skill_entries = [
            SkillEntry(
                name=s["name"],
                description=s["description"],
                path=s["path"],
                tags=s["tags"],
                enabled=s["name"] not in disabled_skills,
            )
            for s in skills_list
        ]
        skill_msg = SkillListMessage(
            skills=skill_entries,
            query=query,
            total_count=len(skills_list),
        )
        get_message_bus().emit(skill_msg)

        return SkillListOutput(
            skills=skills_list, total_count=len(skills_list), query=query, error=None
        )

    return list_or_search_skills
