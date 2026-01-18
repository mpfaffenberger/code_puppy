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

    Updates an existing tool's code and/or metadata. At least one of
    python_code or description must be provided.

    Args:
        context: The run context from pydantic-ai
        tool_name: Name of the tool to update (required)
        python_code: New Python source code (optional)
        description: New description to update in TOOL_META (optional)

    Returns:
        UniversalConstructorOutput with update_result on success
    """

    from code_puppy.plugins.universal_constructor.registry import get_registry
    from code_puppy.plugins.universal_constructor.sandbox import (
        _extract_tool_meta,
        validate_syntax,
    )

    if not tool_name:
        return UniversalConstructorOutput(
            action="update",
            success=False,
            error="tool_name is required for update action",
        )

    # Check that at least one update field is provided
    if not python_code and not description:
        return UniversalConstructorOutput(
            action="update",
            success=False,
            error="At least one of python_code or description must be provided",
        )

    registry = get_registry()
    tool = registry.get_tool(tool_name)

    if not tool:
        return UniversalConstructorOutput(
            action="update",
            success=False,
            error=f"Tool '{tool_name}' not found",
        )

    source_path = tool.source_path
    if not source_path or not source_path.exists():
        return UniversalConstructorOutput(
            action="update",
            success=False,
            error="Tool has no source path or file does not exist",
        )

    changes_applied = []

    try:
        # Read existing code
        existing_code = source_path.read_text(encoding="utf-8")
        new_code = existing_code

        if python_code:
            # Validate new code syntax
            syntax_result = validate_syntax(python_code)
            if not syntax_result.valid:
                error_msg = "; ".join(syntax_result.errors)
                return UniversalConstructorOutput(
                    action="update",
                    success=False,
                    error=f"Syntax error in new code: {error_msg}",
                )

            # Validate TOOL_META exists in new code
            new_meta = _extract_tool_meta(python_code)
            if new_meta is None:
                return UniversalConstructorOutput(
                    action="update",
                    success=False,
                    error="New code must contain a valid TOOL_META dictionary",
                )

            new_code = python_code
            changes_applied.append("Replaced source code")

        if description:
            # Update description in the code's TOOL_META
            # Parse existing meta and update description
            current_meta = _extract_tool_meta(new_code)
            if current_meta is None:
                return UniversalConstructorOutput(
                    action="update",
                    success=False,
                    error="Could not parse TOOL_META from code",
                )

            # Simple string replacement for description
            old_desc = current_meta.get("description", "")
            if old_desc:
                # Try to replace the old description with new one
                new_code = new_code.replace(
                    f'"description": "{old_desc}"',
                    f'"description": "{description}"',
                ).replace(
                    f"'description': '{old_desc}'",
                    f"'description': '{description}'",
                )
                if f'"description": "{description}"' in new_code or f"'description': '{description}'" in new_code:
                    changes_applied.append(f"Updated description to: {description}")

        # Write updated code
        source_path.write_text(new_code, encoding="utf-8")

        # Reload registry to pick up changes
        registry.reload()

        return UniversalConstructorOutput(
            action="update",
            success=True,
            update_result=UCUpdateOutput(
                success=True,
                tool_name=tool_name,
                source_path=source_path,
                changes_applied=changes_applied,
            ),
        )

    except Exception as e:
        return UniversalConstructorOutput(
            action="update",
            success=False,
            error=f"Failed to update tool: {e}",
        )


def _handle_info_action(
    context: RunContext,
    tool_name: Optional[str],
) -> UniversalConstructorOutput:
    """Handle the 'info' action - get detailed tool information.

    Retrieves comprehensive information about a UC tool including its
    metadata, source code, and function signature.

    Args:
        context: The run context from pydantic-ai
        tool_name: Full name of the tool (including namespace)

    Returns:
        UniversalConstructorOutput with info_result containing tool details
    """
    from code_puppy.plugins.universal_constructor.registry import get_registry

    if not tool_name:
        return UniversalConstructorOutput(
            action="info",
            success=False,
            error="tool_name is required for info action",
        )

    registry = get_registry()
    tool = registry.get_tool(tool_name)

    if not tool:
        return UniversalConstructorOutput(
            action="info",
            success=False,
            error=f"Tool '{tool_name}' not found",
        )

    # Read source code from file
    source_code = ""
    source_path = tool.source_path
    if source_path and source_path.exists():
        try:
            source_code = source_path.read_text(encoding="utf-8")
        except Exception:
            source_code = "[Could not read source]"
    else:
        source_code = "[Source file not found]"

    return UniversalConstructorOutput(
        action="info",
        success=True,
        info_result=UCInfoOutput(
            success=True,
            tool=tool,
            source_code=source_code,
        ),
    )


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
