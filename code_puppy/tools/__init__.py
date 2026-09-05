import os
import sys

from code_puppy.callbacks import (
    on_filter_agent_tools,
    on_register_agent_tools,
    on_register_tools,
)
from code_puppy.messaging import emit_warning
from code_puppy.tools.agent_tools import register_list_agents
from code_puppy.tools.ask_user_question import register_ask_user_question
from code_puppy.tools.command_runner import (
    register_agent_run_shell_command,
    register_agent_share_your_reasoning,
)
from code_puppy.tools.display import (
    display_non_streamed_result as display_non_streamed_result,
)
from code_puppy.tools.file_modifications import (
    register_create_file,
    register_delete_file,
    register_delete_snippet,
    register_edit_file,
    register_claude_edit,
    register_replace_in_file,
)
from code_puppy.tools.apply_patch import register_apply_patch
from code_puppy.tools.file_operations import (
    register_grep,
    register_list_files,
    register_read_file,
)
from code_puppy.tools.image_tools import register_load_image
from code_puppy.tools.model_tools import register_list_available_models
from code_puppy.tools.subagent_invocation import (
    register_invoke_agent,
    register_invoke_agent_with_model,
)

# Map of tool names to their individual registration functions
TOOL_REGISTRY = {
    # Agent Tools
    "list_agents": register_list_agents,
    "invoke_agent": register_invoke_agent,
    "invoke_agent_with_model": register_invoke_agent_with_model,
    "list_available_models": register_list_available_models,
    # File Operations
    "list_files": register_list_files,
    "read_file": register_read_file,
    "grep": register_grep,
    # File Modifications
    "edit_file": register_edit_file,  # DEPRECATED: auto-expanded to create_file, replace_in_file, delete_snippet
    "edit": register_claude_edit,
    "create_file": register_create_file,
    "replace_in_file": register_replace_in_file,
    "delete_snippet": register_delete_snippet,
    "delete_file": register_delete_file,
    "apply_patch": register_apply_patch,
    # Command Runner
    "agent_run_shell_command": register_agent_run_shell_command,
    "agent_share_your_reasoning": register_agent_share_your_reasoning,
    # User Interaction
    "ask_user_question": register_ask_user_question,
    # Image loading (used by browser/QA agents and friends)
    "load_image_for_analysis": register_load_image,
}


def _load_browser_tool_registry() -> dict[str, object]:
    """Skip Playwright-backed tool imports on Android."""
    if sys.platform == "android":
        return {}

    from code_puppy.tools.browser.tool_registry import BROWSER_TOOL_REGISTRY

    return BROWSER_TOOL_REGISTRY


TOOL_REGISTRY.update(_load_browser_tool_registry())

# Tools that expand into multiple tools for backward compat: requesting one
# registers the expansions INSTEAD (the original is not registered).
TOOL_EXPANSIONS: dict[str, list[str]] = {
    "edit_file": ["create_file", "replace_in_file", "delete_snippet"],
}

# File-writing tools that Codex-style models receive through one native patch
# envelope. The legacy names remain available to custom agents and configs.
_FILE_MUTATION_TOOLS = frozenset(
    {"edit", "replace_in_file", "create_file", "delete_snippet", "delete_file"}
)


def should_use_codex_patch(model_name: str | None) -> bool:
    """Return whether a model should receive the Codex patch interface.

    This deliberately uses Code Puppy's model aliases rather than a broad
    provider substring. The built-in Codex/OpenAI Responses aliases are named
    ``codex-*`` / ``chatgpt-*`` or ``gpt-5*``; GPT-4 and generic OpenAI
    Chat-Completions models keep the granular tools.
    """
    if not model_name:
        return False
    normalized = model_name.lower()
    return (
        "codex" in normalized
        or normalized.startswith("chatgpt-")
        or normalized.startswith("gpt-5")
    )


# Legacy tool names we silently ignore. Truly removed tools only — working
# aliases belong in TOOL_REGISTRY.
REMOVED_LEGACY_TOOLS: set[str] = set()

# Process-wide tool kill-switch (issue #182), set by the no_tools plugin or
# subprocess wrappers. Env var on purpose: process-scoped, never persists.
NO_TOOLS_ENV_VAR = "CODE_PUPPY_NO_TOOLS"


def tools_disabled() -> bool:
    """True when the ``CODE_PUPPY_NO_TOOLS`` kill-switch is active.

    When active, no tools are registered on any agent and no MCP toolsets
    are attached — the model runs pure text-in/text-out.
    """
    return os.environ.get(NO_TOOLS_ENV_VAR, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _load_plugin_tools() -> None:
    """Load tools registered by plugins via the register_tools callback.

    This merges plugin-provided tools into the TOOL_REGISTRY.
    Called lazily when tools are first accessed.
    """
    try:
        results = on_register_tools()
        for result in results:
            if result is None:
                continue
            # Each result should be a list of tool definitions
            tools_list = result if isinstance(result, list) else [result]
            for tool_def in tools_list:
                if (
                    isinstance(tool_def, dict)
                    and "name" in tool_def
                    and "register_func" in tool_def
                ):
                    tool_name = tool_def["name"]
                    register_func = tool_def["register_func"]
                    if callable(register_func):
                        TOOL_REGISTRY[tool_name] = register_func
    except Exception:
        # Don't let plugin failures break core functionality
        pass


def has_extended_thinking_active(model_name: str | None = None) -> bool:
    """Check if an Anthropic model has extended thinking enabled or adaptive.

    When extended thinking is active, the model already exposes its reasoning
    via thinking blocks, making the share_your_reasoning tool redundant.

    Args:
        model_name: The model name to check. If None, uses the current global model.

    Returns:
        True if the model is an Anthropic model with extended_thinking set to
        "enabled" or "adaptive".
    """
    from code_puppy.config import get_effective_model_settings, get_global_model_name

    if model_name is None:
        model_name = get_global_model_name()

    if model_name is None:
        return False

    # Only applies to Anthropic/Claude models
    if not (model_name.startswith("claude-") or model_name.startswith("anthropic-")):
        return False

    from code_puppy.model_utils import get_default_extended_thinking

    settings = get_effective_model_settings(model_name)
    default_thinking = get_default_extended_thinking(model_name)
    extended_thinking = settings.get("extended_thinking", default_thinking)

    # Handle legacy boolean values
    if extended_thinking is True:
        extended_thinking = "enabled"
    elif extended_thinking is False:
        return False

    return extended_thinking in ("enabled", "adaptive")


def register_tools_for_agent(
    agent,
    tool_names: list[str],
    model_name: str | None = None,
    agent_name: str | None = None,
):
    """Register specific tools for an agent based on tool names.

    Args:
        agent: The agent to register tools to.
        tool_names: List of tool names to register. UC tools are prefixed with "uc:".
        model_name: Optional model name. Used to determine if certain tools
            (like agent_share_your_reasoning) should be skipped. If None,
            falls back to the current global model.
        agent_name: Optional logical agent name (e.g. ``"code-puppy"``).
            Passed to the ``register_agent_tools`` and ``filter_agent_tools``
            callbacks so plugins can advertise and curate tools per agent.
    """
    from code_puppy.config import get_universal_constructor_enabled

    if tools_disabled():
        # --no-tools / CODE_PUPPY_NO_TOOLS: register nothing at all. This
        # also keeps tool schemas out of the request, trimming token usage.
        return

    _load_plugin_tools()

    # Union plugin-advertised tools in (companion to the register_tools hook:
    # this decides which agent gets which) — one shared place, no duplication.
    plugin_extras = on_register_agent_tools(agent_name)
    if plugin_extras:
        seen = set(tool_names)
        merged = list(tool_names)
        for extra in plugin_extras:
            if extra not in seen:
                merged.append(extra)
                seen.add(extra)
        tool_names = merged

    # Let policy plugins curate the complete merged surface without changing
    # registration. Specialized tools remain available to other agents.
    tool_names = on_filter_agent_tools(agent_name, tool_names)

    if os.environ.get("CODE_PUPPY_DISABLE_ASK_USER_QUESTION", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        tool_names = [name for name in tool_names if name != "ask_user_question"]

    # Expand compound tools (e.g. "edit_file" → three individual tools)
    expanded_tools: list[str] = []
    seen: set[str] = set()
    for tool_name in tool_names:
        if tool_name in TOOL_EXPANSIONS:
            for expanded in TOOL_EXPANSIONS[tool_name]:
                if expanded not in seen:
                    expanded_tools.append(expanded)
                    seen.add(expanded)
        else:
            if tool_name not in seen:
                expanded_tools.append(tool_name)
                seen.add(tool_name)
    tool_names = expanded_tools

    use_codex_patch = should_use_codex_patch(model_name)
    selected_tools: list[str] = []
    for tool_name in tool_names:
        if use_codex_patch and tool_name in _FILE_MUTATION_TOOLS:
            if "apply_patch" not in selected_tools:
                selected_tools.append("apply_patch")
            continue
        # ``edit`` is the Claude/OpenCode-facing name. Keep the old
        # replace_in_file name as a registry/config compatibility alias.
        if not use_codex_patch and tool_name == "replace_in_file":
            tool_name = "edit"
        if tool_name not in selected_tools:
            selected_tools.append(tool_name)
    tool_names = selected_tools

    for tool_name in tool_names:
        # Handle UC tools (prefixed with "uc:")
        if tool_name.startswith("uc:"):
            # Skip UC tools if UC is disabled
            if not get_universal_constructor_enabled():
                continue
            uc_tool_name = tool_name[3:]  # Remove "uc:" prefix
            _register_uc_tool_wrapper(agent, uc_tool_name)
            continue

        if tool_name in REMOVED_LEGACY_TOOLS:
            continue

        if tool_name not in TOOL_REGISTRY:
            # Skip unknown tools with a warning instead of failing
            emit_warning(f"Warning: Unknown tool '{tool_name}' requested, skipping...")
            continue

        # Check if Universal Constructor is disabled
        if (
            tool_name == "universal_constructor"
            and not get_universal_constructor_enabled()
        ):
            continue  # Skip UC if disabled in config

        # Register the individual tool
        register_func = TOOL_REGISTRY[tool_name]
        register_func(agent)


def _register_uc_tool_wrapper(agent, uc_tool_name: str):
    """Register a wrapper for a UC tool that calls it via the UC registry.

    This creates a dynamic tool that wraps the UC tool, preserving its
    parameter signature so pydantic-ai can generate proper JSON schema.

    Args:
        agent: The agent to register the tool wrapper to.
        uc_tool_name: The full name of the UC tool (e.g., "api.weather").
    """
    import inspect
    from typing import Any

    from pydantic_ai import RunContext

    # Get tool info and function from registry
    try:
        from code_puppy.universal_constructor_provider import (
            get_universal_constructor_provider,
        )

        provider = get_universal_constructor_provider()
        if provider is None:
            emit_warning("Warning: Universal Constructor provider is unavailable")
            return
        tool_info = provider.get_tool(uc_tool_name)
        if not tool_info:
            emit_warning(f"Warning: UC tool '{uc_tool_name}' not found, skipping...")
            return

        func = provider.get_tool_function(uc_tool_name)
        if not func:
            emit_warning(
                f"Warning: UC tool '{uc_tool_name}' function not found, skipping..."
            )
            return

        description = tool_info.meta.description
        docstring = tool_info.docstring or description
    except Exception as e:
        emit_warning(f"Warning: Failed to get UC tool '{uc_tool_name}' info: {e}")
        return

    # Get the original function's signature
    try:
        sig = inspect.signature(func)
        # Get annotations from the original function
        annotations = getattr(func, "__annotations__", {}).copy()
    except (ValueError, TypeError):
        sig = None
        annotations = {}

    # Create wrapper that preserves the signature
    def make_uc_wrapper(
        tool_name: str, original_func, original_sig, original_annotations
    ):
        # Build the wrapper function
        async def uc_tool_wrapper(context: RunContext, **kwargs: Any) -> Any:
            """Dynamically generated wrapper for a UC tool."""
            try:
                result = original_func(**kwargs)
                # Await async tool implementations
                if inspect.isawaitable(result):
                    result = await result
                return result
            except Exception as e:
                return {"error": f"UC tool '{tool_name}' failed: {e}"}

        # Copy signature info from original function
        uc_tool_wrapper.__name__ = tool_name.replace(".", "_")
        uc_tool_wrapper.__doc__ = (
            f"{docstring}\n\nThis is a Universal Constructor tool."
        )

        # Preserve annotations for pydantic-ai schema generation
        if original_annotations:
            # Add 'context' param and copy original params (excluding 'return')
            new_annotations = {"context": RunContext}
            for param_name, param_type in original_annotations.items():
                if param_name != "return":
                    new_annotations[param_name] = param_type
            if "return" in original_annotations:
                new_annotations["return"] = original_annotations["return"]
            else:
                new_annotations["return"] = Any
            uc_tool_wrapper.__annotations__ = new_annotations

        # Try to set __signature__ for better introspection
        if original_sig:
            try:
                # Build new parameters list: context first, then original params
                new_params = [
                    inspect.Parameter(
                        "context",
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=RunContext,
                    )
                ]
                for param in original_sig.parameters.values():
                    new_params.append(param)

                # Create new signature with return annotation
                return_annotation = original_annotations.get("return", Any)
                new_sig = original_sig.replace(
                    parameters=new_params, return_annotation=return_annotation
                )
                uc_tool_wrapper.__signature__ = new_sig
            except (ValueError, TypeError):
                pass  # Signature manipulation failed, continue without it

        return uc_tool_wrapper

    wrapper = make_uc_wrapper(uc_tool_name, func, sig, annotations)

    # Register the wrapper as a tool
    try:
        agent.tool(wrapper)
    except Exception as e:
        emit_warning(f"Warning: Failed to register UC tool '{uc_tool_name}': {e}")


def register_all_tools(agent, model_name: str | None = None):
    """Register all available tools to the provided agent.

    Args:
        agent: The agent to register tools to.
        model_name: Optional model name for conditional tool filtering.
    """
    all_tools = list(TOOL_REGISTRY.keys())
    register_tools_for_agent(agent, all_tools, model_name=model_name)


def get_available_tool_names() -> list[str]:
    """Get list of all available tool names.

    Returns:
        List of all tool names that can be registered.
    """
    _load_plugin_tools()
    return list(TOOL_REGISTRY.keys())
