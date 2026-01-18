"""Universal Constructor Tool - Dynamic tool creation and management.

This module provides the universal_constructor tool that enables users
to create, manage, and call custom tools dynamically during a session.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from code_puppy.plugins.universal_constructor.models import (
    UCCallOutput,
    UCCreateOutput,
    UCInfoOutput,
    UCListOutput,
    UCUpdateOutput,
)


class UniversalConstructorOutput(BaseModel):
    """Unified response model for universal_constructor operations.

    Wraps all action-specific outputs with a common interface.
    """

    action: str = Field(..., description="The action that was performed")
    success: bool = Field(..., description="Whether the operation succeeded")
    error: Optional[str] = Field(default=None, description="Error message if failed")

    # Action-specific results (only one will be populated based on action)
    list_result: Optional[UCListOutput] = Field(
        default=None, description="Result of list action"
    )
    call_result: Optional[UCCallOutput] = Field(
        default=None, description="Result of call action"
    )
    create_result: Optional[UCCreateOutput] = Field(
        default=None, description="Result of create action"
    )
    update_result: Optional[UCUpdateOutput] = Field(
        default=None, description="Result of update action"
    )
    info_result: Optional[UCInfoOutput] = Field(
        default=None, description="Result of info action"
    )

    model_config = {"arbitrary_types_allowed": True}


def _stub_not_implemented(action: str) -> UniversalConstructorOutput:
    """Return a stub response for unimplemented actions."""
    return UniversalConstructorOutput(
        action=action,
        success=False,
        error="Not implemented yet",
    )


async def universal_constructor_impl(
    context: RunContext,
    action: Literal["list", "call", "create", "update", "info"],
    tool_name: Optional[str] = None,
    tool_args: Optional[dict] = None,
    python_code: Optional[str] = None,
    description: Optional[str] = None,
) -> UniversalConstructorOutput:
    """Implementation of the universal_constructor tool.

    Routes to appropriate action handler based on the action parameter.
    All actions are currently stubbed out and will return "Not implemented yet".

    Args:
        context: The run context from pydantic-ai
        action: The operation to perform:
            - "list": List all available UC tools
            - "call": Execute a specific UC tool
            - "create": Create a new UC tool from Python code
            - "update": Modify an existing UC tool
            - "info": Get detailed info about a specific tool
        tool_name: Name of tool (for call/update/info). Supports "namespace.name" format.
        tool_args: Arguments to pass when calling a tool (for call action)
        python_code: Python source code for the tool (for create/update actions)
        description: Human-readable description (for create action)

    Returns:
        UniversalConstructorOutput with action-specific results
    """
    # Route to appropriate action handler (all stubbed for now)
    if action == "list":
        return _handle_list_action(context)
    elif action == "call":
        return _handle_call_action(context, tool_name, tool_args)
    elif action == "create":
        return _handle_create_action(context, tool_name, python_code, description)
    elif action == "update":
        return _handle_update_action(context, tool_name, python_code, description)
    elif action == "info":
        return _handle_info_action(context, tool_name)
    else:
        return UniversalConstructorOutput(
            action=action,
            success=False,
            error=f"Unknown action: {action}",
        )


def _handle_list_action(context: RunContext) -> UniversalConstructorOutput:
    """Handle the 'list' action - list all available UC tools.

    Stub implementation - returns "Not implemented yet".
    """
    return _stub_not_implemented("list")


def _handle_call_action(
    context: RunContext,
    tool_name: Optional[str],
    tool_args: Optional[dict],
) -> UniversalConstructorOutput:
    """Handle the 'call' action - execute a UC tool.

    Stub implementation - returns "Not implemented yet".
    """
    if not tool_name:
        return UniversalConstructorOutput(
            action="call",
            success=False,
            error="tool_name is required for call action",
        )
    return _stub_not_implemented("call")


def _handle_create_action(
    context: RunContext,
    tool_name: Optional[str],
    python_code: Optional[str],
    description: Optional[str],
) -> UniversalConstructorOutput:
    """Handle the 'create' action - create a new UC tool.

    Stub implementation - returns "Not implemented yet".
    """
    if not python_code:
        return UniversalConstructorOutput(
            action="create",
            success=False,
            error="python_code is required for create action",
        )
    return _stub_not_implemented("create")


def _handle_update_action(
    context: RunContext,
    tool_name: Optional[str],
    python_code: Optional[str],
    description: Optional[str],
) -> UniversalConstructorOutput:
    """Handle the 'update' action - modify an existing UC tool.

    Stub implementation - returns "Not implemented yet".
    """
    if not tool_name:
        return UniversalConstructorOutput(
            action="update",
            success=False,
            error="tool_name is required for update action",
        )
    return _stub_not_implemented("update")


def _handle_info_action(
    context: RunContext,
    tool_name: Optional[str],
) -> UniversalConstructorOutput:
    """Handle the 'info' action - get detailed tool information.

    Stub implementation - returns "Not implemented yet".
    """
    if not tool_name:
        return UniversalConstructorOutput(
            action="info",
            success=False,
            error="tool_name is required for info action",
        )
    return _stub_not_implemented("info")


def register_universal_constructor(agent):
    """Register the universal_constructor tool with an agent.

    Args:
        agent: The pydantic-ai agent to register the tool with
    """

    @agent.tool
    async def universal_constructor(
        context: RunContext,
        action: Literal["list", "call", "create", "update", "info"],
        tool_name: Optional[str] = None,
        tool_args: Optional[dict] = None,
        python_code: Optional[str] = None,
        description: Optional[str] = None,
    ) -> UniversalConstructorOutput:
        """Universal Constructor - Create, manage, and call custom tools dynamically.

        The Universal Constructor allows you to extend your capabilities by creating
        new tools on-the-fly, managing existing custom tools, and executing them
        within the current session.

        Args:
            action: The operation to perform:
                - "list": List all available custom tools with their metadata
                - "call": Execute a specific custom tool with provided arguments
                - "create": Create a new tool from Python code
                - "update": Modify an existing tool's code or metadata
                - "info": Get detailed information about a specific tool
            tool_name: Name of the tool (required for call/update/info actions).
                Supports namespaced format like "namespace.tool_name".
            tool_args: Dictionary of arguments to pass when calling a tool.
                Only used with action="call".
            python_code: Python source code defining the tool function.
                Required for action="create", optional for action="update".
            description: Human-readable description of what the tool does.
                Used with action="create".

        Returns:
            UniversalConstructorOutput: Contains:
                - action: The action that was performed
                - success: Whether the operation succeeded
                - error: Error message if the operation failed
                - list_result: Results when action="list"
                - call_result: Results when action="call"
                - create_result: Results when action="create"
                - update_result: Results when action="update"
                - info_result: Results when action="info"

        Examples:
            >>> # List all available custom tools
            >>> result = universal_constructor(ctx, action="list")
            >>> print(result.list_result.tools)

            >>> # Get info about a specific tool
            >>> result = universal_constructor(ctx, action="info", tool_name="api.weather")
            >>> print(result.info_result.tool.meta.description)

            >>> # Call a custom tool
            >>> result = universal_constructor(
            ...     ctx,
            ...     action="call",
            ...     tool_name="utils.formatter",
            ...     tool_args={"text": "hello world", "style": "title"}
            ... )
            >>> print(result.call_result.result)

            >>> # Create a new tool
            >>> code = '''
            ... TOOL_META = {
            ...     "name": "greet",
            ...     "description": "Generate a greeting message"
            ... }
            ...
            ... def greet(name: str) -> str:
            ...     return f"Hello, {name}!"
            ... '''
            >>> result = universal_constructor(
            ...     ctx,
            ...     action="create",
            ...     python_code=code,
            ...     description="A friendly greeting tool"
            ... )

        Note:
            Custom tools are stored in ~/.code_puppy/plugins/universal_constructor/
            and persist across sessions. Tools can be organized into namespaces
            by placing them in subdirectories.
        """
        return await universal_constructor_impl(
            context, action, tool_name, tool_args, python_code, description
        )
