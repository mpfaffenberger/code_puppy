"""Code Mode agent for Monty-powered code execution with MCP optimization."""

from typing import Any, List

from .base_agent import BaseAgent


class CodeModeAgent(BaseAgent):
    """Monty-powered code execution agent with MCP object caching and intelligent tool search."""

    def __init__(self):
        super().__init__()
        # CodeMode capability integration
        # Wraps all tools into a single run_code tool powered by Monty sandbox
        # The model writes Python code that calls multiple tools with loops,
        # conditionals, variables, and asyncio.gather
        self._capabilities = None  # Lazy-loaded in get_capabilities()

    @property
    def name(self) -> str:
        return "codemode"

    @property
    def display_name(self) -> str:
        return "Code Mode 🐹"

    @property
    def description(self) -> str:
        return "Monty-powered code execution agent with MCP object caching and intelligent tool search"

    def get_available_tools(self) -> list[str]:
        """Standard development toolkit for safe code execution.

        Note: With CodeMode, these tools become callables inside a sandboxed
        run_code environment. The model writes Python code that can:
        - Call tools as functions instead of individual tool calls
        - Use loops, conditionals, and variables
        - Parallelize calls with asyncio.gather
        """
        return [
            "list_agents",
            "invoke_agent",
            "list_files",
            "read_file",
            "grep",
            "create_file",
            "replace_in_file",
            "delete_snippet",
            "delete_file",
            "agent_run_shell_command",
        ]

    def get_capabilities(self) -> List[Any]:
        """Get CodeMode capability with Monty sandbox execution.

        Returns:
            List containing CodeMode capability instance.
        """
        if self._capabilities is None:
            try:
                from pydantic_harness import CodeMode

                # CodeMode wraps all tools into a single run_code tool
                # The model writes Python code that calls tools as functions
                # with full control over flow, variables, and parallelism
                self._capabilities = [CodeMode()]
            except ImportError:
                # Fallback if pydantic-harness not available
                self._capabilities = []
        return self._capabilities

    def get_system_prompt(self) -> str:
        return """
You are Code Mode.

Be concise.

You only use the `run_code` tool.
Do not call any other tool directly.
Do not describe how to use other tools.
Do not ask to use other tools.

Solve tasks by writing Python inside `run_code`.
Inside that code, use the provided tool callables as needed.
Prefer one `run_code` call that fully completes the task.
If needed, inspect files, read content, edit files, and run shell commands from inside `run_code`.

Before acting, think briefly about the simplest correct plan.
Then use `run_code`.
After it finishes, give a short plain-English result.
"""
