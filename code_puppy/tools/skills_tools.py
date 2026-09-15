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
from code_puppy.skill_provider import get_skill_provider

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
        provider = get_skill_provider()
        if provider is None:
            return SkillActivateOutput(
                skill_name=skill_name,
                content="",
                resources=[],
                error="Skills integration is unavailable.",
            )

        # Check if skills enabled
        if not provider.is_enabled():
            return SkillActivateOutput(
                skill_name=skill_name,
                content="",
                resources=[],
                error="Skills integration is disabled. Enable it with /set skills_enabled=true",
            )

        # Find skill by name among *enabled* skills only — disabled skills
        # are intentionally invisible to activate_skill.
        try:
            skill_path = provider.find_enabled_skill_path(skill_name)
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
        content = provider.load_skill_content(skill_path)
        if content is None:
            return SkillActivateOutput(
                skill_name=skill_name,
                content="",
                resources=[],
                error=f"Failed to load content for skill '{skill_name}'",
            )

        # Get resource list
        resource_paths = provider.get_skill_resources(skill_path)
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
        provider = get_skill_provider()
        if provider is None:
            return SkillListOutput(
                skills=[],
                total_count=0,
                query=query,
                error="Skills integration is unavailable.",
            )

        # Check if skills enabled
        if not provider.is_enabled():
            return SkillListOutput(
                skills=[],
                total_count=0,
                query=query,
                error="Skills integration is disabled. Enable it with /set skills_enabled=true",
            )

        # We still need disabled_skills for the SkillEntry.enabled flag below,
        # even though the helper has already filtered them out of the list.
        disabled_skills = provider.get_disabled_skill_names()

        # Get enabled skills with metadata (disabled skills never get their
        # frontmatter loaded — that's enforced inside the provider).
        try:
            skills_list = provider.list_enabled_skills()
        except Exception as e:
            logger.error(f"Failed to discover skills: {e}")
            return SkillListOutput(
                skills=[],
                total_count=0,
                query=query,
                error=f"Failed to discover skills: {e}",
            )

        # Filter: match if ANY term appears in name/description/tags — avoids the
        # old bug of treating the whole query as one substring.
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
