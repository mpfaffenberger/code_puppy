"""Per-plugin contribution extraction for the ``/plugins`` preview.

For a given plugin name, return the concrete things it contributes per
category — tools, slash commands, agents, skills, model types/providers,
MCP catalog servers, browser types, and agent-advertised tool names.

Best-effort and display-only: we invoke only the target plugin's own
collection callbacks (filtered via ``get_callback_owner``), and every read
is wrapped in ``try/except`` so a raising callback or registry yields no
items rather than crashing the preview.

Some plugins register via a direct registry instead of firing the matching
callback, so two categories need extra attribution:

* commands: ``@register_command`` writes straight into the command registry
  without firing ``custom_command_help``.
* tools: ``TOOL_REGISTRY`` is mutable, so a plugin can add a tool without
  firing ``register_tools``.

For both, we read the registry and attribute each entry to the plugin whose
module defines the handler / register_func (see ``_plugin_owner_of_module``).
Core entries never match a real plugin name, so they fall out naturally.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from code_puppy.callbacks import get_callback_owner, get_callbacks

# ---------------------------------------------------------------------------
# Category keys (stable identifiers the preview renderer can key off).
# ---------------------------------------------------------------------------
CATEGORY_TOOLS = "tools"
CATEGORY_COMMANDS = "commands"
CATEGORY_AGENTS = "agents"
CATEGORY_SKILLS = "skills"
CATEGORY_MODEL_TYPES = "model_types"
CATEGORY_MODEL_PROVIDERS = "model_providers"
CATEGORY_MCP_SERVERS = "mcp_servers"
CATEGORY_BROWSER_TYPES = "browser_types"
CATEGORY_AGENT_TOOLS = "agent_tools"


# ---------------------------------------------------------------------------
# Owner-filtered invocation primitives
# ---------------------------------------------------------------------------
def _owned_callbacks(plugin_name: str, phase: str) -> List[Callable[..., Any]]:
    """Return *phase*'s callbacks attributed to *plugin_name*."""
    return [
        cb
        for cb in get_callbacks(phase, include_disabled=True)
        if get_callback_owner(cb) == plugin_name
    ]


def _invoke_owned(plugin_name: str, phase: str, *args: Any) -> List[Any]:
    """Invoke each owned callback for *phase*; a raising callback is skipped."""
    results: List[Any] = []
    for cb in _owned_callbacks(plugin_name, phase):
        try:
            results.append(cb(*args))
        except Exception:
            continue
    return results


def _dedupe(items: List[str]) -> List[str]:
    """Drop falsy/duplicate entries while preserving first-seen order."""
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _as_list(result: Any) -> List[Any]:
    """Normalize a callback result into a list (mirrors core's leniency)."""
    if result is None:
        return []
    return result if isinstance(result, list) else [result]


def _dict_key(entry: Any, key: str) -> str:
    """Return ``entry[key]`` as a non-empty str, else ``""``."""
    if isinstance(entry, dict):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


# ---------------------------------------------------------------------------
# Direct-registry attribution (commands / tools that bypass callback hooks)
# ---------------------------------------------------------------------------
def _plugin_owner_of_module(module_name: Optional[str]) -> Optional[str]:
    """Map a callable's ``__module__`` to the plugin name that defines it.

    Mirrors the three plugin module-name layouts:

    * builtin -> ``code_puppy.plugins.<name>.<...>``
    * project -> ``project_plugins.<name>.<...>``
    * user    -> ``<name>.<...>``

    Returns ``None`` when the module is empty/unparseable.
    """
    if not module_name:
        return None
    parts = module_name.split(".")
    if module_name.startswith("code_puppy.plugins."):
        return parts[2] if len(parts) >= 3 else None
    if module_name.startswith("project_plugins."):
        return parts[1] if len(parts) >= 2 else None
    return parts[0] if parts and parts[0] else None


def _owns_callable(plugin_name: str, func: Any) -> bool:
    """Whether *func* is defined inside *plugin_name*'s module tree."""
    module_name = getattr(func, "__module__", None)
    return _plugin_owner_of_module(module_name) == plugin_name


# ---------------------------------------------------------------------------
# Per-category extraction helpers
# ---------------------------------------------------------------------------
def _collect_dict_field(
    plugin_name: str, phase: str, field: str, *args: Any
) -> List[str]:
    """Invoke *phase* (owned by *plugin_name*) and collect ``entry[field]``.

    Each callback returns a dict or list of dicts; ``entry[field]`` from
    each is appended. ``*args`` is forwarded (e.g. ``register_agent_tools(None)``).
    """
    names: List[str] = []
    for result in _invoke_owned(plugin_name, phase, *args):
        for entry in _as_list(result):
            names.append(_dict_key(entry, field))
    return names


def _collect_dict_keys(plugin_name: str, phase: str) -> List[str]:
    """Invoke *phase* and collect the string keys of each dict result.

    Used for hooks whose contract is ``() -> {name: handler}`` rather than
    ``() -> [{"name": ...}]``.
    """
    keys: List[str] = []
    for result in _invoke_owned(plugin_name, phase):
        keys.extend(_dict_keys(result))
    return keys


def get_tools(plugin_name: str) -> List[str]:
    """Tool names contributed by *plugin_name*, deduped (first-seen order).

    Combines the ``register_tools`` callback with direct ``TOOL_REGISTRY``
    entries owned by this plugin's module.
    """
    names = _collect_dict_field(plugin_name, "register_tools", "name")
    names.extend(_registry_tools(plugin_name))
    return _dedupe(names)


def _registry_tools(plugin_name: str) -> List[str]:
    """Tool names from ``TOOL_REGISTRY`` owned by *plugin_name* (read-only)."""
    names: List[str] = []
    try:
        from code_puppy.tools import TOOL_REGISTRY

        items = list(TOOL_REGISTRY.items())
    except Exception:
        return names
    for tool_name, register_func in items:
        try:
            if isinstance(tool_name, str) and _owns_callable(
                plugin_name, register_func
            ):
                names.append(tool_name)
        except Exception:
            continue
    return names


def get_commands(plugin_name: str) -> List[str]:
    """Slash commands contributed by *plugin_name*, deduped (first-seen order).

    Combines the ``custom_command_help`` callback (which may return a single
    ``(name, description)`` tuple, a list of such tuples, or a legacy list of
    ``"/name - description"`` strings) with direct ``command_registry`` entries
    whose handler is owned by this plugin. Each command renders as
    ``"/name — description"`` (description omitted when absent).
    """
    commands: List[str] = []
    for result in _invoke_owned(plugin_name, "custom_command_help"):
        if not result:
            continue
        # Shape 1: a bare (name, description) tuple.
        if isinstance(result, tuple) and len(result) == 2:
            commands.append(_format_command(result[0], result[1]))
            continue
        if not isinstance(result, list):
            continue
        # Shape 2: list of (name, description) tuples.
        if result and isinstance(result[0], tuple):
            for item in result:
                if isinstance(item, tuple) and len(item) == 2:
                    commands.append(_format_command(item[0], item[1]))
        # Shape 3: legacy list of "/name - description" strings.
        elif result and isinstance(result[0], str):
            for item in result:
                parsed = _parse_legacy_command(item)
                if parsed:
                    commands.append(parsed)
    commands.extend(_registry_commands(plugin_name))
    return _dedupe(commands)


def _registry_commands(plugin_name: str) -> List[str]:
    """Slash commands from ``command_registry`` owned by *plugin_name*.

    Uses ``get_unique_commands`` (one entry per primary command, no aliases),
    attributing each to the plugin that defines its handler.
    """
    commands: List[str] = []
    try:
        from code_puppy.command_line.command_registry import get_unique_commands

        infos = get_unique_commands()
    except Exception:
        return commands
    for info in infos:
        try:
            if not _owns_callable(plugin_name, getattr(info, "handler", None)):
                continue
            name = getattr(info, "name", "")
            description = getattr(info, "description", "")
            formatted = _format_command(name, description)
            if formatted:
                commands.append(formatted)
        except Exception:
            continue
    return commands


def _format_command(name: Any, description: Any) -> str:
    """Render a ``(name, description)`` pair as ``/name — description``."""
    cmd = str(name).strip().lstrip("/").strip()
    if not cmd:
        return ""
    desc = str(description).strip()
    return f"/{cmd} — {desc}" if desc else f"/{cmd}"


def _parse_legacy_command(line: Any) -> str:
    """Parse a legacy ``"/name - description"`` string."""
    if not isinstance(line, str) or not line.startswith("/"):
        return ""
    if " - " in line:
        name, desc = line.split(" - ", 1)
        return _format_command(name, desc)
    return _format_command(line, "")


def get_agents(plugin_name: str) -> List[str]:
    """Agent names from ``register_agents`` -> ``[{"name", ...}]``."""
    return _dedupe(_collect_dict_field(plugin_name, "register_agents", "name"))


def get_skills(plugin_name: str) -> List[str]:
    """Skill names from ``register_skills`` -> ``[{"name", ...}]``."""
    return _dedupe(_collect_dict_field(plugin_name, "register_skills", "name"))


def get_model_types(plugin_name: str) -> List[str]:
    """Model type names from ``register_model_type`` -> ``[{"type", ...}]``."""
    return _dedupe(_collect_dict_field(plugin_name, "register_model_type", "type"))


def get_model_providers(plugin_name: str) -> List[str]:
    """Provider keys from ``register_model_providers`` -> ``{name: ModelClass}``."""
    return _dedupe(_collect_dict_keys(plugin_name, "register_model_providers"))


def get_mcp_servers(plugin_name: str) -> List[str]:
    """Server names from ``register_mcp_catalog_servers`` -> ``[MCPServerTemplate]``.

    Accepts ``MCPServerTemplate``-like objects (``.name`` attribute) as well
    as plain dicts with a ``"name"`` key, for maximum leniency.
    """
    names: List[str] = []
    for result in _invoke_owned(plugin_name, "register_mcp_catalog_servers"):
        for entry in _as_list(result):
            names.append(_server_name(entry))
    return _dedupe(names)


def _server_name(entry: Any) -> str:
    """Extract a display name from an MCP server template or dict."""
    name = getattr(entry, "name", None)
    if isinstance(name, str) and name:
        return name
    return _dict_key(entry, "name")


def get_browser_types(plugin_name: str) -> List[str]:
    """Browser type keys from ``register_browser_types`` -> ``{type_name: init}``."""
    return _dedupe(_collect_dict_keys(plugin_name, "register_browser_types"))


def get_agent_tools(plugin_name: str) -> List[str]:
    """Advertised tool names from ``register_agent_tools(None)`` -> ``[str]``.

    ``None`` means "any agent" per the hook contract.
    """
    names: List[str] = []
    for result in _invoke_owned(plugin_name, "register_agent_tools", None):
        for item in _as_list(result):
            if isinstance(item, str):
                names.append(item)
    return _dedupe(names)


def _dict_keys(result: Any) -> List[str]:
    """Return the string keys of a dict result (provider/browser shape)."""
    if not isinstance(result, dict):
        return []
    return [k for k in result.keys() if isinstance(k, str) and k]


# ---------------------------------------------------------------------------
# Public aggregate API
# ---------------------------------------------------------------------------
_EXTRACTORS: Dict[str, Callable[[str], List[str]]] = {
    CATEGORY_TOOLS: get_tools,
    CATEGORY_COMMANDS: get_commands,
    CATEGORY_AGENTS: get_agents,
    CATEGORY_SKILLS: get_skills,
    CATEGORY_MODEL_TYPES: get_model_types,
    CATEGORY_MODEL_PROVIDERS: get_model_providers,
    CATEGORY_MCP_SERVERS: get_mcp_servers,
    CATEGORY_BROWSER_TYPES: get_browser_types,
    CATEGORY_AGENT_TOOLS: get_agent_tools,
}


def get_contributions(plugin_name: str) -> Dict[str, List[str]]:
    """Return every contribution category for *plugin_name*.

    Keyed by the ``CATEGORY_*`` constants; each value is a (possibly empty)
    list of display strings, so the renderer always gets a complete dict.
    """
    return {category: extract(plugin_name) for category, extract in _EXTRACTORS.items()}
