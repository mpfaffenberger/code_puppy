"""Skills tools - dedicated tools for Agent Skills integration.

Supports both local skills and remote skill registries:
- Local: ~/.code_puppy/skills/, ./skills/
- Remote: E2E Open Skills, MetaRegistry BFF

When activating a skill not found locally, it will attempt to
auto-install from the remote registries.
"""

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

# Source identifiers for skills
SOURCE_LOCAL = "local"
SOURCE_E2E = "e2e"
SOURCE_METAREGISTRY = "metaregistry"


# Output models
class SkillListOutput(BaseModel):
    """Output for list_or_search_skills tool."""

    skills: List[dict]  # Each has: name, description, path/source, tags
    total_count: int
    query: Optional[str] = None  # The search query if provided
    include_remote: bool = False  # Whether remote registries were queried
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
        """Activate a skill by loading its full SKILL.md instructions.

        Call this when a user's task matches a skill's description.
        Returns complete instructions for accomplishing the task.

        Args:
            skill_name: Name of the skill to activate (from available skills list)

        Returns:
            SkillActivateOutput: Contains the skill's full content and available resources.
        """
        # Import from plugin
        from pathlib import Path

        from code_puppy.plugins.agent_skills.config import (
            get_skill_directories,
            get_skills_enabled,
        )
        from code_puppy.plugins.agent_skills.discovery import discover_skills
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

        # Discover skills
        try:
            skill_dirs = [Path(d) for d in get_skill_directories()]
            discovered = discover_skills(skill_dirs)
        except Exception as e:
            logger.error(f"Failed to discover skills: {e}")
            return SkillActivateOutput(
                skill_name=skill_name,
                content="",
                resources=[],
                error=f"Failed to discover skills: {e}",
            )

        # Find skill by name
        skill_path = None
        for skill_info in discovered:
            if skill_info.name == skill_name and skill_info.has_skill_md:
                skill_path = skill_info.path
                break

        if not skill_path:
            # Try to auto-install from remote registries
            logger.info(f"Skill '{skill_name}' not found locally, checking remote registries...")
            try:
                from code_puppy.plugins.skill_marketplace import api_client

                # Fetch all skills from remote retries
                resp = await api_client.fetch_all_skills()
                if resp.get("success"):
                    remote_skills = resp.get("data", [])
                    # Find matching skill
                    matching = None
                    for rs in remote_skills:
                        if rs.get("name") == skill_name:
                            matching = rs
                            break

                    if matching:
                        # Fetch and install the SKILL.md
                        source = matching.get("_source", api_client.SOURCE_E2E)
                        skill_id = matching.get("id", skill_name)
                        md_resp = await api_client.fetch_skill_md(
                            skill_name,
                            source=source,
                            skill_id=skill_id,
                        )
                        if md_resp.get("success"):
                            content = md_resp.get("data", "")
                            # Install locally
                            installed_path = api_client.install_skill(
                                skill_name, content, metadata=matching
                            )
                            logger.info(f"Auto-installed skill '{skill_name}' from {source}")

                            # Return the content directly
                            skill_msg = SkillActivateMessage(
                                skill_name=skill_name,
                                skill_path=str(installed_path.parent),
                                content_preview=content[:200] if content else "",
                                resource_count=0,
                                success=True,
                            )
                            get_message_bus().emit(skill_msg)

                            return SkillActivateOutput(
                                skill_name=skill_name,
                                content=content,
                                resources=[],
                                error=None,
                            )
            except Exception as e:
                logger.warning(f"Failed to auto-install from registry: {e}")

            return SkillActivateOutput(
                skill_name=skill_name,
                content="",
                resources=[],
                error=f"Skill '{skill_name}' not found locally or in remote registries. Use list_or_search_skills to see available skills.",
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
        context: RunContext,
        query: Optional[str] = None,
        include_remote: bool = False,
    ) -> SkillListOutput:
        """List available skills, optionally filtered by search query.

        Args:
            query: Optional search term to filter skills by name/description/tags.
                   If None, returns all available skills.
            include_remote: If True, also query remote skill registries
                   (E2E Open Skills, MetaRegistry). Default False for speed.

        Returns:
            SkillListOutput: List of skills with name, description, path/source, and tags.
        """
        # Import from plugin
        from pathlib import Path

        from code_puppy.plugins.agent_skills.config import (
            get_disabled_skills,
            get_skill_directories,
            get_skills_enabled,
        )
        from code_puppy.plugins.agent_skills.discovery import discover_skills
        from code_puppy.plugins.agent_skills.metadata import parse_skill_metadata

        # Check if skills enabled
        if not get_skills_enabled():
            return SkillListOutput(
                skills=[],
                total_count=0,
                query=query,
                error="Skills integration is disabled. Enable it with /set skills_enabled=true",
            )

        # Get disabled skills
        disabled_skills = get_disabled_skills()

        # Discover all skills
        try:
            skill_dirs = [Path(d) for d in get_skill_directories()]
            discovered = discover_skills(skill_dirs)
        except Exception as e:
            logger.error(f"Failed to discover skills: {e}")
            return SkillListOutput(
                skills=[],
                total_count=0,
                query=query,
                error=f"Failed to discover skills: {e}",
            )

        # Parse metadata for each local skill
        skills_list = []
        local_skill_names = set()
        for skill_info in discovered:
            # Skip disabled skills
            if skill_info.name in disabled_skills:
                continue

            # Only include skills with valid SKILL.md
            if not skill_info.has_skill_md:
                continue

            metadata = parse_skill_metadata(skill_info.path)
            if metadata:
                skill_dict = {
                    "name": metadata.name,
                    "description": metadata.description,
                    "path": str(metadata.path),
                    "tags": metadata.tags,
                    "version": metadata.version,
                    "author": metadata.author,
                    "source": SOURCE_LOCAL,
                    "installed": True,
                }
                skills_list.append(skill_dict)
                local_skill_names.add(metadata.name)

        # Optionally fetch from remote registries
        if include_remote:
            try:
                from code_puppy.plugins.skill_marketplace import api_client

                resp = await api_client.fetch_all_skills()
                if resp.get("success"):
                    remote_skills = resp.get("data", [])
                    for rs in remote_skills:
                        name = rs.get("name", "")
                        # Skip if already have locally
                        if name in local_skill_names:
                            continue
                        # Skip disabled
                        if name in disabled_skills:
                            continue

                        # Normalize tags
                        raw_tags = rs.get("tags", [])
                        if isinstance(raw_tags, str):
                            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
                        elif isinstance(raw_tags, list):
                            tags = raw_tags
                        else:
                            tags = []

                        skill_dict = {
                            "name": name,
                            "description": rs.get("description", ""),
                            "path": None,  # Not installed locally
                            "tags": tags,
                            "version": rs.get("metadata", {}).get("version"),
                            "author": rs.get("metadata", {}).get("author"),
                            "source": rs.get("_source", SOURCE_E2E),
                            "installed": False,
                        }
                        skills_list.append(skill_dict)
            except Exception as e:
                logger.warning(f"Failed to fetch remote skills: {e}")

        # Filter by query if provided
        if query:
            query_lower = query.lower()
            filtered = []
            for skill in skills_list:
                # Check name (case-insensitive)
                if query_lower in skill["name"].lower():
                    filtered.append(skill)
                    continue

                # Check description (case-insensitive)
                if query_lower in skill["description"].lower():
                    filtered.append(skill)
                    continue

                # Check tags (case-insensitive)
                for tag in skill["tags"]:
                    if query_lower in tag.lower():
                        filtered.append(skill)
                        break
            skills_list = filtered

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
            skills=skills_list,
            total_count=len(skills_list),
            query=query,
            include_remote=include_remote,
            error=None,
        )

    return list_or_search_skills
