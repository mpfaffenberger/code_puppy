"""browse_skill_namespace — the on-demand discovery tool.

This is the model-agnostic analog of OpenAI's `tool_search` (and
Anthropic's Tool Search Tool): the model calls it when it needs a
capability instead of scanning a flat list baked into the system prompt.
Three modes, one tool, matching the three things a model actually needs
to do at this scale:

    browse_skill_namespace()                    -> list namespaces (directory)
    browse_skill_namespace(namespace="Finance")  -> list skills in one namespace
    browse_skill_namespace(query="variance")     -> keyword search, all namespaces

No model-provider-specific `defer_loading` flag required — the reduction
in upfront context comes from the `load_prompt` summary block (see
namespaces.py) being a few lines per namespace instead of one line per
skill. This tool is just the drill-down mechanism underneath it.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from pydantic import BaseModel
from pydantic_ai import RunContext

from .namespaces import build_namespaces


class NamespaceBrowseOutput(BaseModel):
    """Uniform output for all three browse_skill_namespace modes."""

    mode: str  # "directory" | "namespace" | "search"
    namespaces: List[str] = []  # populated in "directory" mode
    skills: List[dict] = []  # populated in "namespace"/"search" modes
    total_skills: int = 0
    error: Optional[str] = None


def _skill_matches(skill_haystack: str, terms: List[str]) -> bool:
    return any(term in skill_haystack for term in terms)


def _query_terms(query: Optional[str]) -> List[str]:
    """Split a query into lowercase terms.

    A blank or whitespace-only query means "no filter", not "filter to
    nothing" -- ``any(term in haystack for term in [])`` is ``False`` for
    every skill, which would otherwise make ``query=""`` or
    ``query="   "`` silently return zero results instead of the
    unfiltered set the caller almost certainly intended.
    """
    if not query or not query.strip():
        return []
    return query.lower().split()


def register_browse_skill_namespace(agent):
    """Register the browse_skill_namespace tool on an agent."""

    @agent.tool
    async def browse_skill_namespace(
        context: RunContext,
        namespace: Optional[str] = None,
        query: Optional[str] = None,
    ) -> NamespaceBrowseOutput:
        """Discover skills without loading all of them into context at once.

        Call with no arguments first to see the namespace directory (a
        short list of domains + counts). Then either drill into one
        namespace by name, or keyword-search across every namespace at
        once. Call activate_skill(name) on whatever you find.

        Args:
            namespace: Exact namespace name to list skills within.
            query: Keyword(s) to search across name/description/tags.
        """
        # build_namespaces() does a full filesystem walk + frontmatter
        # re-parse per call. Left inline, that blocking I/O runs directly
        # on the event loop -- pydantic-ai only auto-offloads to a worker
        # thread for *sync* tool functions (anyio.to_thread), not async
        # ones. Since this tool must stay async (RunContext-taking tools
        # in this codebase are conventionally async -- see
        # activate_skill/list_or_search_skills in
        # code_puppy/tools/skills_tools.py), we offload explicitly instead.
        try:
            namespaces = await asyncio.to_thread(build_namespaces)
        except Exception as exc:  # noqa: BLE001 - surface to the model, don't crash the turn
            return NamespaceBrowseOutput(
                mode="directory",
                error=f"Failed to read skill catalog: {exc}",
            )
        total = sum(len(v) for v in namespaces.values())

        if not namespaces:
            return NamespaceBrowseOutput(
                mode="directory",
                error="No skills available (skills disabled or none installed).",
            )

        # Mode 1: directory listing (no args)
        if namespace is None and query is None:
            return NamespaceBrowseOutput(
                mode="directory",
                namespaces=sorted(namespaces.keys(), key=lambda n: -len(namespaces[n])),
                total_skills=total,
            )

        # Mode 2: drill into a specific namespace
        if namespace is not None:
            matched_ns = next(
                (n for n in namespaces if n.lower() == namespace.lower()), None
            )
            if matched_ns is None:
                return NamespaceBrowseOutput(
                    mode="namespace",
                    error=(
                        f"Namespace '{namespace}' not found. Call "
                        "browse_skill_namespace() with no arguments to see "
                        "valid namespace names."
                    ),
                )
            skills = namespaces[matched_ns]
            terms = _query_terms(query)
            if terms:
                skills = [
                    s
                    for s in skills
                    if _skill_matches(
                        f"{s.name} {s.description} {' '.join(s.tags)}".lower(),
                        terms,
                    )
                ]
            return NamespaceBrowseOutput(
                mode="namespace",
                skills=[
                    {"name": s.name, "description": s.description, "tags": s.tags}
                    for s in skills
                ],
                total_skills=len(skills),
            )

        # Mode 3: keyword search across every namespace. An empty/blank
        # query (explicit query="" rather than omitted entirely -- mode 1
        # only triggers when both args are None) means "no filter",
        # matching mode 2's semantics above.
        terms = _query_terms(query)
        results = [
            {
                "name": s.name,
                "description": s.description,
                "tags": s.tags,
                "namespace": ns,
            }
            for ns, skills in namespaces.items()
            for s in skills
            if not terms
            or _skill_matches(
                f"{s.name} {s.description} {' '.join(s.tags)}".lower(), terms
            )
        ]
        return NamespaceBrowseOutput(
            mode="search", skills=results, total_skills=len(results)
        )

    return browse_skill_namespace
