from code_puppy.messaging import emit_warning
from code_puppy.tools.agent_tools import (
    register_list_agents,
    register_invoke_agent,
)
from code_puppy.tools.command_runner import (
    register_agent_run_shell_command,
    register_agent_share_your_reasoning,
)
from code_puppy.tools.file_modifications import register_edit_file, register_delete_file
from code_puppy.tools.file_operations import (
    register_list_files,
    register_read_file,
    register_grep,
)


# Map of tool names to their individual registration functions
TOOL_REGISTRY = {
    # Agent Tools
    "list_agents": register_list_agents,
    "invoke_agent": register_invoke_agent,
    # File Operations
    "list_files": register_list_files,
    "read_file": register_read_file,
    "grep": register_grep,
    # File Modifications
    "edit_file": register_edit_file,
    "delete_file": register_delete_file,
    # Command Runner
    "agent_run_shell_command": register_agent_run_shell_command,
    "agent_share_your_reasoning": register_agent_share_your_reasoning,
}


def register_tools_for_agent(agent, tool_names: list[str]):
    """Register specific tools for an agent based on tool names.

    Args:
        agent: The agent to register tools to.
        tool_names: List of tool names to register.
    """
    for tool_name in tool_names:
        if tool_name not in TOOL_REGISTRY:
            # Skip unknown tools with a warning instead of failing
            emit_warning(f"Warning: Unknown tool '{tool_name}' requested, skipping...")
            continue

        # Register the individual tool
        register_func = TOOL_REGISTRY[tool_name]
        register_func(agent)


def register_all_tools(agent):
    """Register all available tools to the provided agent.

    Args:
        agent: The agent to register tools to.
    """
    all_tools = list(TOOL_REGISTRY.keys())
    register_tools_for_agent(agent, all_tools)


def get_available_tool_names() -> list[str]:
    """Get list of all available tool names.

    Returns:
        List of all tool names that can be registered.
    """
    return list(TOOL_REGISTRY.keys())
