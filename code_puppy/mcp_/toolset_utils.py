"""Helpers for introspecting pydantic-ai toolsets (``MCPToolset`` + wrappers).

``ManagedMCPServer.get_pydantic_server()`` hands agents a *wrapped* toolset
(``PrefixedToolset`` around an ``MCPToolset``, possibly further wrapped by
``FilteredToolset``). Consumers that need leaf-level facts (running state,
cached tool definitions) should use these helpers instead of poking at
private attributes on whatever object they happen to hold.

Only ``.wrapped`` (public ``WrapperToolset`` API) and ``.prefix`` (public
``PrefixedToolset`` API) are used for traversal. The one private read left
in the codebase — ``MCPToolset._cached_tools`` — is quarantined here behind
``iter_cached_tool_defs`` with a defensive ``getattr``, because pydantic-ai
exposes no *synchronous* tool-listing API (``list_tools()`` is async and
performs I/O; token estimation must stay sync + side-effect-free).
"""

from typing import Any, Iterator, List, Optional, Tuple


def unwrap_toolset(toolset: Any) -> Any:
    """Follow public ``.wrapped`` links down to the leaf toolset."""
    seen: set = set()
    while True:
        wrapped = getattr(toolset, "wrapped", None)
        if wrapped is None or id(toolset) in seen:
            return toolset
        seen.add(id(toolset))
        toolset = wrapped


def toolset_prefix(toolset: Any) -> Optional[str]:
    """Combined tool-name prefix applied by ``PrefixedToolset`` wrappers.

    Prefixes compose outermost-first (the outer wrapper prefixes the already
    prefixed inner names), matching how ``PrefixedToolset.get_tools``
    renders final tool names. Falls back to a legacy ``tool_prefix``
    attribute on the leaf for duck-typed test doubles.
    """
    parts: List[str] = []
    seen: set = set()
    current = toolset
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        prefix = getattr(current, "prefix", None)
        if isinstance(prefix, str) and prefix:
            parts.append(prefix)
        current = getattr(current, "wrapped", None)
    if parts:
        return "_".join(parts)
    legacy = getattr(unwrap_toolset(toolset), "tool_prefix", None)
    return legacy or None


def toolset_is_running(toolset: Any) -> bool:
    """Whether the leaf toolset currently holds an open server session."""
    return bool(getattr(unwrap_toolset(toolset), "is_running", False))


def iter_cached_tool_defs(toolset: Any) -> Iterator[Tuple[str, str, Any]]:
    """Yield ``(full_name, description, input_schema)`` for cached MCP tools.

    Reads the leaf ``MCPToolset``'s tool cache (populated by pydantic-ai
    after the first ``list_tools()`` call) without triggering I/O. Yields
    nothing for servers that haven't been queried yet — callers should
    treat that as "unknown, assume zero".
    """
    leaf = unwrap_toolset(toolset)
    cached = getattr(leaf, "_cached_tools", None)
    if not cached:
        return
    prefix = toolset_prefix(toolset) or ""
    for mcp_tool in cached:
        name = getattr(mcp_tool, "name", "") or ""
        full_name = f"{prefix}_{name}" if prefix and name else name
        description = getattr(mcp_tool, "description", "") or ""
        schema = getattr(mcp_tool, "inputSchema", None)
        yield full_name, description, schema
