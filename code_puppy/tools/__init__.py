from code_puppy.tools.command_runner import (
    register_command_runner_tools, kill_all_running_shell_processes
)
from code_puppy.tools.file_modifications import register_file_modifications_tools
from code_puppy.tools.file_operations import register_file_operations_tools


def register_all_tools(agent):
    """Register all available tools to the provided agent."""

    register_file_operations_tools(agent)
    register_file_modifications_tools(agent)
    register_command_runner_tools(agent)
