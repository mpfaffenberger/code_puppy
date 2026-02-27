"""
Tool name alias registry — maps each AI provider's tool names to code_puppy's
internal tool names, enabling hooks written for any provider to fire correctly.

Structure
---------
Each provider block defines a dict[str, str] mapping:
    "<Provider tool name>" -> "<code_puppy internal tool name>"

The mapping is bidirectional at lookup time: a hook matcher that names *either*
the provider tool OR the internal tool will match the same event.

Adding a new provider
---------------------
1. Add a new section following the pattern below.
2. Register it in PROVIDER_ALIASES at the bottom of this file.
3. That's it — the matcher picks it up automatically.
"""

from typing import Dict, FrozenSet, Optional

# ---------------------------------------------------------------------------
# Claude Code  (Anthropic)
# Source: `claude mcp serve` → tools/list  (verified against v2.1.52)
# ---------------------------------------------------------------------------
CLAUDE_CODE_ALIASES: Dict[str, str] = {
    # Shell execution
    "Bash": "agent_run_shell_command",
    # File system — read
    "Glob": "list_files",
    "Read": "read_file",
    "Grep": "grep",
    # File system — write
    "Edit": "edit_file",
    "Write": "edit_file",  # Write = full overwrite; same tool in puppy
    # File system — delete
    "Delete": "delete_file",
    # User interaction
    "AskUserQuestion": "ask_user_question",
    # Agent / task orchestration
    "Task": "invoke_agent",
    # Skills
    "Skill": "activate_skill",
    "ToolSearch": "list_or_search_skills",
    # NOTE: the tools below have no direct code_puppy equivalent yet.
    # They are listed here for documentation and future mapping:
    #   "TaskOutput"     -> (no equivalent)
    #   "TaskStop"       -> (no equivalent)
    #   "WebFetch"       -> (no equivalent — see browser_navigate)
    #   "WebSearch"      -> (no equivalent)
    #   "NotebookEdit"   -> (no equivalent)
    #   "TodoWrite"      -> (no equivalent)
    #   "EnterPlanMode"  -> (no equivalent)
    #   "ExitPlanMode"   -> (no equivalent)
    #   "EnterWorktree"  -> (no equivalent)
}


# ---------------------------------------------------------------------------
# Gemini  (Google)
# TODO: populate once Gemini MCP tool names are verified.
# Run `gemini mcp serve` (or equivalent) and inspect the tools/list response,
# then add entries following the same pattern as CLAUDE_CODE_ALIASES above.
# ---------------------------------------------------------------------------
GEMINI_ALIASES: Dict[str, str] = {
    # Add Gemini → code_puppy tool mappings here
}


# ---------------------------------------------------------------------------
# Codex  (OpenAI)
# TODO: populate once Codex MCP tool names are verified.
# Run the Codex MCP server, inspect tools/list, and add entries here.
# ---------------------------------------------------------------------------
CODEX_ALIASES: Dict[str, str] = {
    # Add Codex → code_puppy tool mappings here
}


# ---------------------------------------------------------------------------
# Swarm  (internal / multi-agent)
# TODO: populate if Swarm exposes its own canonical tool name vocabulary.
# ---------------------------------------------------------------------------
SWARM_ALIASES: Dict[str, str] = {
    # Add Swarm → code_puppy tool mappings here
}


# ---------------------------------------------------------------------------
# Master registry — all active alias tables, merged at module load time.
# To disable a provider's aliases, remove its entry from this dict.
# ---------------------------------------------------------------------------
PROVIDER_ALIASES: Dict[str, Dict[str, str]] = {
    "claude": CLAUDE_CODE_ALIASES,
    "gemini": GEMINI_ALIASES,  # placeholder — empty until populated
    "codex": CODEX_ALIASES,  # placeholder — empty until populated
    "swarm": SWARM_ALIASES,  # placeholder — empty until populated
}


# ---------------------------------------------------------------------------
# Flattened lookup structures — built once at import time for O(1) access.
# ---------------------------------------------------------------------------


def _build_lookup() -> Dict[str, FrozenSet[str]]:
    """
    Return a dict mapping every known name (provider *and* internal) to the
    full set of equivalent names, including itself.

    Example result entry:
        "Bash" -> frozenset({"Bash", "agent_run_shell_command"})
        "agent_run_shell_command" -> frozenset({"Bash", "agent_run_shell_command"})
    """
    groups: Dict[str, set] = {}

    for provider_aliases in PROVIDER_ALIASES.values():
        for provider_name, internal_name in provider_aliases.items():
            # Collect all names that map to the same internal tool
            key = internal_name.lower()
            if key not in groups:
                groups[key] = {internal_name}
            groups[key].add(provider_name)

    # Build the final lookup: every alias points to the frozen group
    lookup: Dict[str, FrozenSet[str]] = {}
    for group in groups.values():
        frozen = frozenset(group)
        for name in group:
            lookup[name.lower()] = frozen
    return lookup


# Module-level singleton — import this in matcher.py
ALIAS_LOOKUP: Dict[str, FrozenSet[str]] = _build_lookup()


def get_aliases(tool_name: str) -> FrozenSet[str]:
    """
    Return all known equivalent names for *tool_name* (including itself).
    Returns a frozenset containing only *tool_name* when no aliases exist.
    """
    return ALIAS_LOOKUP.get(tool_name.lower(), frozenset({tool_name}))


def resolve_internal_name(provider_tool_name: str) -> Optional[str]:
    """
    Return the code_puppy internal tool name for a given provider tool name,
    or None if the name is not a known provider alias.
    """
    for provider_aliases in PROVIDER_ALIASES.values():
        for pname, internal in provider_aliases.items():
            if pname.lower() == provider_tool_name.lower():
                return internal
    return None
