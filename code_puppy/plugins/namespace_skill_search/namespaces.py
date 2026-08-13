"""Namespace derivation and summary-block rendering.

A "namespace" is a skill's first tag (falling back to "General" for
untagged skills). No new frontmatter field, no schema migration — every
skill that already has a `tags:` entry in its SKILL.md slots in for free.

This mirrors OpenAI's namespace grouping (`{"type": "namespace", "name":
"crm", "tools": [...]}`) as a plain-data structure instead of a
model-provider-specific request field.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional

from code_puppy.plugins.agent_skills.enabled_skills import list_enabled_skill_metadata
from code_puppy.plugins.agent_skills.metadata import SkillMetadata

_DEFAULT_NAMESPACE = "General"

# OpenAI recommends fewer than 10 functions per namespace; flag oversized
# namespaces without re-tagging skills we don't own.
_RECOMMENDED_MAX_PER_NAMESPACE = 10


def _namespace_for(skill: SkillMetadata) -> str:
    """First tag wins; untagged skills land in the General bucket."""
    if skill.tags:
        return skill.tags[0].strip() or _DEFAULT_NAMESPACE
    return _DEFAULT_NAMESPACE


def build_namespaces() -> Dict[str, List[SkillMetadata]]:
    """Group every enabled skill by namespace.

    Grouping is case-insensitive: skills tagged "finance" and "Finance"
    land in the same bucket. Without this, the directory would silently
    fragment into two separate namespace entries that look distinct to
    the model but are semantically the same category, and a
    case-sensitive drill-down would only ever surface one of them (see
    `search_tool.py`'s case-insensitive `namespace=` lookup, which
    depends on this function never producing two keys that only differ
    by case). The *first* casing encountered wins for display purposes,
    which keeps behavior deterministic for a given skill-discovery order.

    Returns an empty dict if skills are globally disabled or none exist —
    callers should treat that as "nothing to show", not an error.
    """
    namespaces: Dict[str, List[SkillMetadata]] = {}
    display_names: Dict[str, str] = {}
    for skill in list_enabled_skill_metadata():
        raw_ns = _namespace_for(skill)
        key = raw_ns.lower()
        display = display_names.setdefault(key, raw_ns)
        namespaces.setdefault(display, []).append(skill)
    return namespaces


def _duplicate_skill_names(namespaces: Dict[str, List[SkillMetadata]]) -> List[str]:
    """Names shared by 2+ skills, regardless of namespace.

    Nothing in `agent_skills` enforces globally-unique skill names, and
    grouping by namespace makes a collision more visible (two entries
    with the same name can now show up side-by-side across namespace
    listings), not less. We can't resolve the ambiguity here -- that's an
    `agent_skills`-level concern -- but we can at least flag it instead
    of silently presenting the model with two indistinguishable
    `activate_skill(name)` targets.
    """
    counts = Counter(s.name for skills in namespaces.values() for s in skills)
    return sorted(name for name, count in counts.items() if count > 1)


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

    duplicates = _duplicate_skill_names(namespaces)
    if duplicates:
        lines.append(
            "Note: these skill names appear more than once across "
            f"namespaces, so `activate_skill(name)` may be ambiguous: "
            f"{', '.join(duplicates)}."
        )

    return "\n".join(lines)
