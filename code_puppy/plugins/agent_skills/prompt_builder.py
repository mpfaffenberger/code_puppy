"""Build available_skills XML for system prompt injection."""

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .metadata import SkillMetadata


def build_available_skills_xml(skills: List["SkillMetadata"]) -> str:
    """Build Claude-optimized XML listing available skills.

    Args:
        skills: List of SkillMetadata objects to include in the XML.

    Returns:
        XML string listing available skills in the format:
        <available_skills>
          <skill>
            <name>skill-name</name>
            <description>What the skill does...</description>
          </skill>
          ...
        </available_skills>

    To use a skill, call activate_skill(skill_name) to load full instructions.
    """
    if not skills:
        return "<available_skills></available_skills>"

    xml_parts = ["<available_skills>"]

    for skill in skills:
        xml_parts.append("  <skill>")
        xml_parts.append(f"    <name>{skill.name}</name>")
        if skill.description:
            # Escape any XML special characters in the description
            escaped_desc = (
                skill.description.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;")
            )
            xml_parts.append(f"    <description>{escaped_desc}</description>")
        xml_parts.append("  </skill>")

    xml_parts.append("</available_skills>")

    return "\n".join(xml_parts)


def build_skills_guidance() -> str:
    """Return guidance text for how to use skills."""
    return """
# Agent Skills

When `<available_skills>` appears in context, match user tasks to skill descriptions.
Call `activate_skill(skill_name)` to load full instructions before starting the task.
Use `list_or_search_skills(query)` to search for relevant skills.
"""
