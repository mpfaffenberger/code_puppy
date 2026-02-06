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
    """Return guidance text for how to use skills.

    This tells the model about the activate_skill and list_or_search_skills tools,
    and where skills are located.

    Returns:
        Guidance text explaining how to work with skills.
    """
    return """
# Using Agent Skills

Agent Skills are pre-packaged capabilities that provide specialized instructions for specific tasks. Skills are discovered from configured directories and can be activated on demand.

## Skill Locations

Skills are discovered from these directories:
- **~/.code_puppy/skills/** - User skills (primary location)
- **./skills/** - Project-specific skills (relative to current directory)

Each skill is a folder containing a `SKILL.md` file with YAML frontmatter.

## Available Skills Tools

1. **list_or_search_skills(query?)** - List or search available skills
   - `list_or_search_skills()` - List all skills
   - `list_or_search_skills(query="pdf")` - Search for skills matching "pdf"

2. **activate_skill(skill_name)** - Load full skill instructions
   - Call this when a user's task matches a skill's description
   - Returns the complete SKILL.md content with detailed instructions

## How to Use Skills

1. When you see `<available_skills>` in your context, skills are available
2. Match user tasks to skill descriptions
3. Call `activate_skill(skill_name)` to load full instructions
4. Follow the skill's instructions to complete the task

## Installing New Skills

To install a skill, place its folder in `~/.code_puppy/skills/`:
```
~/.code_puppy/skills/
└── my-skill/
    ├── SKILL.md      # Required: Instructions with YAML frontmatter
    └── resources/    # Optional: Templates, scripts, etc.
```
"""
