from code_puppy.tools.command_runner import register_command_runner_tools
from code_puppy.tools.file_modifications import register_file_modifications_tools
from code_puppy.tools.file_operations import register_file_operations_tools
from code_puppy.tools.web_search import register_web_search_tools


def register_all_tools(agent):
    """Register all available tools to the provided agent."""
    register_file_operations_tools(agent)
    register_file_modifications_tools(agent)
    register_command_runner_tools(agent)
    register_web_search_tools(agent)
