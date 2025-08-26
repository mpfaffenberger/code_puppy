from code_puppy.tools.command_runner import register_command_runner_tools
from code_puppy.tools.file_modifications import register_file_modifications_tools
from code_puppy.tools.file_operations import register_file_operations_tools


# Map of tool names to their registration functions and categories
TOOL_REGISTRY = {
    # File Operations
    "list_files": (register_file_operations_tools, "file_operations"),
    "read_file": (register_file_operations_tools, "file_operations"),
    "grep": (register_file_operations_tools, "file_operations"),
    
    # File Modifications
    "edit_file": (register_file_modifications_tools, "file_modifications"),
    "delete_file": (register_file_modifications_tools, "file_modifications"),
    
    # Command Runner
    "agent_run_shell_command": (register_command_runner_tools, "command_runner"),
    "agent_share_your_reasoning": (register_command_runner_tools, "command_runner"),
}


def register_tools_for_agent(agent, tool_names: list[str]):
    """Register specific tools for an agent based on tool names.
    
    Args:
        agent: The agent to register tools to.
        tool_names: List of tool names to register.
    """
    # Group tools by their registration function to avoid duplicate calls
    categories_to_register = set()
    
    for tool_name in tool_names:
        if tool_name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        _, category = TOOL_REGISTRY[tool_name]
        categories_to_register.add(category)
    
    # Register tools by category
    for category in categories_to_register:
        if category == "file_operations":
            register_file_operations_tools(agent)
        elif category == "file_modifications":
            register_file_modifications_tools(agent)
        elif category == "command_runner":
            register_command_runner_tools(agent)


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
