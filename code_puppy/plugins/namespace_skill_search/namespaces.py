"""Namespace derivation and summary-block rendering.

A "namespace" is a skill's first tag (falling back to "General" for
untagged skills). No new frontmatter field, no schema migration — every
skill that already has a `tags:` entry in its SKILL.md slots in for free.

This mirrors OpenAI's namespace grouping (`{"type": "namespace", "name":
"crm", "tools": [...]}`) as a plain-data structure instead of a
model-provider-specific request field.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from code_puppy.plugins.agent_skills.enabled_skills import list_enabled_skill_metadata
from code_puppy.plugins.agent_skills.metadata import SkillMetadata

_DEFAULT_NAMESPACE = "General"

# OpenAI's own sizing guidance: "keep each namespace to fewer than 10
# functions for better token efficiency and model performance." We don't
# enforce this (skills aren't ours to re-tag), but we surface it in the
# namespace summary so an oversized namespace is visible, not silent.
_RECOMMENDED_MAX_PER_NAMESPACE = 10


def _namespace_for(skill: SkillMetadata) -> str:
    """First tag wins; untagged skills land in the General bucket."""
    if skill.tags:
        return skill.tags[0].strip() or _DEFAULT_NAMESPACE
    return _DEFAULT_NAMESPACE


def build_namespaces() -> Dict[str, List[SkillMetadata]]:
    """Group every enabled skill by namespace.

    Returns an empty dict if skills are globally disabled or none exist —
    callers should treat that as "nothing to show", not an error.
    """
    namespaces: Dict[str, List[SkillMetadata]] = {}
    for skill in list_enabled_skill_metadata():
        ns = _namespace_for(skill)
        namespaces.setdefault(ns, []).append(skill)
    return namespaces


def build_namespace_summary() -> Optional[str]:
    """Render the compact `load_prompt` block replacing the flat skill list.

    Format is intentionally terse — this is the ONE thing that always
    lands in the system prompt, so every line here is context budget spent
    on every single turn.
    """
    namespaces = build_namespaces()
    if not namespaces:
        return None

    total = sum(len(v) for v in namespaces.values())
    lines = [
        "## Skill Namespaces",
        f"{total} skills available across {len(namespaces)} namespaces. "
        "Individual skills are NOT listed here — browse or search instead.",
        "",
    ]

    for ns, skills in sorted(namespaces.items(), key=lambda kv: -len(kv[1])):
        preview = ", ".join(s.name for s in skills[:3])
        remainder = len(skills) - 3
        if remainder > 0:
            preview += f", +{remainder} more"
        flag = (
            "  oversized namespace"
            if len(skills) > _RECOMMENDED_MAX_PER_NAMESPACE
            else ""
        )
        lines.append(f"- **{ns}** ({len(skills)}){flag}: {preview}")

    lines.append("")
    lines.append(
        "Call `browse_skill_namespace()` with no arguments to see this same "
        "directory again, `browse_skill_namespace(namespace=...)` to list "
        "every skill in one namespace, or `browse_skill_namespace(query=...)` "
        "to keyword-search across all namespaces. Then `activate_skill(name)` "
        "to load full instructions."
    )
    return "\n".join(lines)
