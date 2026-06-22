"""Build the `available skills` section for system-prompt injection.

Keep the verbosity floor-low. Each skill becomes a single line of the form
``- <name>: <description>``. That is essentially the frontmatter `name` and
`description` fields, flattened. No XML, no ceremony, no escaping circus.
"""

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .metadata import SkillMetadata


def _one_line(text: str) -> str:
    """Collapse whitespace so each skill stays on a single line."""
    return " ".join(text.split())


def build_available_skills_block(skills: List["SkillMetadata"]) -> str:
    """Render a minimal markdown list of available skills.

    Format::

        ## Available Skills
        - skill-one: short description
        - skill-two: short description

    Returns an empty string when there are no skills — callers can simply
    concatenate without worrying about stray headings.
    """
    if not skills:
        return ""

    lines = ["## Available Skills"]
    for skill in skills:
        desc = _one_line(skill.description) if skill.description else ""
        lines.append(f"- {skill.name}: {desc}" if desc else f"- {skill.name}")
    return "\n".join(lines)


def build_skills_guidance() -> str:
    """Tell the model when and how to use a skill."""
    return (
        "When the user's question or task relates to a skill listed above, "
        "activate it with `activate_skill(name)` **before** answering so its "
        "full instructions are loaded into context. Use "
        "`list_or_search_skills(query)` to discover skills by keyword — it "
        "matches any individual word in the query."
    )
