"""Anthropic-native-editor capability resolution (Phase 3 of the Anthropic
editor adapter plan, see ``.context/plan/anthropic-editor-adapter.md``).

Decides, from known configuration data (never from a failed provider call),
whether a given model is eligible for Anthropic's client-executed text-editor
tool (``str_replace_based_edit_tool``). The decision is made once, up front,
at tool-registration and model-construction time -- never discovered by
retrying after a provider rejection.

Two independent gates must both pass:

1. **Feature flag** -- ``enable_anthropic_native_editor`` (default off). This
   keeps the native path opt-in at merge time; Phase 4 decides the default.
2. **Route** -- the resolved model's ``type`` in ``models.json`` must be the
   direct Anthropic API (``"anthropic"``). Deliberately conservative:
   ``custom_anthropic`` (an arbitrary Anthropic-compatible base URL) and
   ``claude_code`` (OAuth via a separate plugin-owned transport) are not
   assumed compatible without dedicated verification, and Claude reached
   through an OpenAI-compatible gateway (``type: "openai"``, e.g. OpenRouter)
   is excluded by construction -- this checks the declared route, never a
   model-name substring.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from code_puppy.command_line.completion_cache import TTLCache
from code_puppy.config import get_truthy_bool_value

# Anthropic's client-executed text-editor tool. Both the 2025-04-29 and
# 2025-07-28 tool *versions* (the ``type`` value) advertise this same tool
# ``name``; we target the newer, currently-documented version for Claude 4.x
# models. Verified in the installed ``anthropic`` SDK: no ``undo_edit`` command
# exists for this tool family (only the retired ``text_editor_20241022``
# had one), so it is intentionally not offered -- see the dispatcher in
# ``code_puppy/tools/anthropic_editor_tool.py``.
NATIVE_EDITOR_TOOL_NAME = "str_replace_based_edit_tool"
NATIVE_EDITOR_TOOL_TYPE = "text_editor_20250728"

# model_config["type"] values confirmed (in model_factory.py) to route
# directly to Anthropic's own API via the real ``anthropic`` SDK client.
_DIRECT_ANTHROPIC_MODEL_TYPES = frozenset({"anthropic"})

# Generic tools with a direct native-editor equivalent. Hidden from the tool
# list only when the native editor is actually offered in their place.
# delete_snippet/delete_file are deliberately NOT here: the native editor has
# no delete command, so hiding them would remove a capability, not
# deduplicate one.
OVERLAPPING_PORTABLE_TOOLS = frozenset({"read_file", "replace_in_file", "create_file"})

# The subset of OVERLAPPING_PORTABLE_TOOLS that actually grants write access.
# The native editor is a single monolithic tool offering create+str_replace+
# insert together -- it cannot be partially granted. So the swap must only
# fire for an agent that already carries *all* of these (the full portable
# write surface), never just one:
#   - An agent with only `create_file` (e.g. agent_model_judge: `create_file`
#     but no `replace_in_file`) must not gain `str_replace`/`insert` access
#     to arbitrary *existing* files it could never touch before.
#   - An agent with only `replace_in_file` must not gain the native `create`
#     command's always-overwrite whole-file write it could never do before.
# Least-privilege triggers on "did this agent ask for the full mutation
# surface", not "does the agent's toolset overlap the native editor at all"
# or "did it ask for any one mutation tool".
NATIVE_EDITOR_MUTATION_TOOLS = frozenset({"replace_in_file", "create_file"})


def has_full_native_editor_mutation_surface(tool_names) -> bool:
    """True only when ``tool_names`` already contains every tool the native
    editor's write commands collectively replace -- see
    ``NATIVE_EDITOR_MUTATION_TOOLS`` for why partial overlap must not
    trigger the swap.
    """
    names = set(tool_names)
    return NATIVE_EDITOR_MUTATION_TOOLS.issubset(names)


_model_config_cache: TTLCache[Dict[str, Any]] = TTLCache()


def _load_models_config() -> Dict[str, Any]:
    from code_puppy.model_factory import ModelFactory

    return ModelFactory.load_config()


def get_anthropic_native_editor_enabled() -> bool:
    """Feature flag: opt-in rollout switch for the Anthropic native editor.

    Off by default -- per the Phase 3 plan and acceptance criteria, the
    native path must not become the default at merge. Set
    ``enable_anthropic_native_editor = true`` in config to turn it on.
    ``get_value``/``get_truthy_bool_value`` read only the config file today
    (no environment-variable fallback exists for this or any other flag),
    so there is no separate env-var knob to document here.
    """
    return get_truthy_bool_value("enable_anthropic_native_editor", False)


def get_model_config(
    model_name: Optional[str], models_config: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Look up one model's config dict, loading/caching the full config if needed.

    Cached briefly (see ``TTLCache``) because ``register_tools_for_agent`` is
    called twice per agent build (probe + final pass) and this resolution
    must not add a full config reload+merge to each call.
    """
    if not model_name:
        return None
    config = (
        models_config
        if models_config is not None
        else _model_config_cache.get(_load_models_config)
    )
    model_config = config.get(model_name)
    return model_config if isinstance(model_config, dict) else None


def is_direct_anthropic_route(model_config: Optional[Dict[str, Any]]) -> bool:
    """Return True when ``model_config`` routes directly to Anthropic's API.

    Based solely on the declared ``type``, never a model-name guess.
    """
    if not model_config:
        return False
    return model_config.get("type") in _DIRECT_ANTHROPIC_MODEL_TYPES


def supports_anthropic_native_editor(
    model_name: Optional[str], models_config: Optional[Dict[str, Any]] = None
) -> bool:
    """Return True when ``model_name`` should receive the native editor tool.

    Both the feature flag and a confirmed direct-Anthropic route are
    required; an unsupported or ambiguous route falls back to the portable
    tool profile chosen up front, not discovered by retrying.
    """
    if not get_anthropic_native_editor_enabled():
        return False
    model_config = get_model_config(model_name, models_config)
    return is_direct_anthropic_route(model_config)
