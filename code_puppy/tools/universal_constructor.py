"""Universal Constructor Tool - Dynamic tool creation and management.

This module provides the universal_constructor tool that enables users
to create, manage, and call custom tools dynamically during a session.
"""

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Literal, Optional

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from code_puppy.messaging import get_message_bus
from code_puppy.messaging.messages import UniversalConstructorMessage
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


def _run_ruff_format(file_path) -> Optional[str]:
    """Run ruff format on a file.

    Args:
        file_path: Path to the file to format (str or Path)

    Returns:
        Warning message if formatting failed, None on success
    """
    try:
        result = subprocess.run(
            ["ruff", "format", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return f"ruff format failed: {result.stderr.strip()}"
        return None
    except FileNotFoundError:
        return "ruff not found - code not formatted"
    except subprocess.TimeoutExpired:
        return "ruff format timed out"
    except Exception as e:
        return f"ruff format error: {e}"


def _generate_preview(code: str, max_lines: int = 10) -> str:
    """Generate a preview of the first N lines of code.

    Args:
        code: The source code to preview
        max_lines: Maximum number of lines to include (default 10)

    Returns:
        A string with the first N lines, with "..." appended if truncated
    """
    lines = code.splitlines()
    if len(lines) <= max_lines:
        return code
    preview_lines = lines[:max_lines]
    return "\n".join(preview_lines) + "\n... (truncated)"


def _emit_uc_message(
    action: str,
    success: bool,
    summary: str,
    tool_name: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """Emit a UniversalConstructorMessage to the message bus.

    Args:
        action: The UC action performed (list/call/create/update/info)
        success: Whether the operation succeeded
        summary: Brief summary of the result
        tool_name: Tool name if applicable
        details: Additional details (optional)
    """
    bus = get_message_bus()
    msg = UniversalConstructorMessage(
        action=action,
        tool_name=tool_name,
        success=success,
        summary=summary,
        details=details,
    )
    bus.emit(msg)


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
    # Route to appropriate action handler
    if action == "list":
        result = _handle_list_action(context)
    elif action == "call":
        result = _handle_call_action(context, tool_name, tool_args)
    elif action == "create":
        result = _handle_create_action(context, tool_name, python_code, description)
    elif action == "update":
        result = _handle_update_action(context, tool_name, python_code, description)
    elif action == "info":
        result = _handle_info_action(context, tool_name)
    else:
        result = UniversalConstructorOutput(
            action=action,
            success=False,
            error=f"Unknown action: {action}",
        )

    # Emit the banner message after the action completes
    summary = _build_summary(result)
    _emit_uc_message(
        action=action,
        success=result.success,
        summary=summary,
        tool_name=tool_name,
        details=result.error if not result.success else None,
    )

    return result


def _build_summary(result: UniversalConstructorOutput) -> str:
    """Build a brief summary string from a UC result.

    Args:
        result: The UniversalConstructorOutput to summarize

    Returns:
        A brief human-readable summary string
    """
    if not result.success:
        return result.error or "Operation failed"

    if result.list_result:
        return f"Found {result.list_result.enabled_count} enabled tools (of {result.list_result.total_count} total)"
    elif result.call_result:
        exec_time = result.call_result.execution_time or 0
        return f"Executed in {exec_time:.2f}s"
    elif result.create_result:
        return f"Created {result.create_result.tool_name}"
    elif result.update_result:
        return f"Updated {result.update_result.tool_name}"
    elif result.info_result and result.info_result.tool:
        return f"Info for {result.info_result.tool.full_name}"
    else:
        return "Operation completed"


def _handle_list_action(context: RunContext) -> UniversalConstructorOutput:
    """Handle the 'list' action - list all available UC tools.

    Lists all enabled tools from the UC registry, returning their
    metadata, signatures, and source paths.

    Args:
        context: The run context from pydantic-ai (unused for list action)

    Returns:
        UniversalConstructorOutput with list_result containing all enabled tools.
    """
    from code_puppy.plugins.universal_constructor.registry import get_registry

    try:
        registry = get_registry()
        # Get all tools (including disabled for count)
        all_tools = registry.list_tools(include_disabled=True)
        enabled_tools = [t for t in all_tools if t.meta.enabled]

        return UniversalConstructorOutput(
            action="list",
            success=True,
            list_result=UCListOutput(
                tools=enabled_tools,
                total_count=len(all_tools),
                enabled_count=len(enabled_tools),
            ),
        )
    except Exception as e:
        return UniversalConstructorOutput(
            action="list",
            success=False,
            error=f"Failed to list tools: {e}",
            list_result=UCListOutput(
                tools=[],
                total_count=0,
                enabled_count=0,
                error=str(e),
            ),
        )


def _handle_call_action(
    context: RunContext,
    tool_name: Optional[str],
    tool_args: Optional[dict],
) -> UniversalConstructorOutput:
    """Handle the 'call' action - execute a UC tool.

    Validates the tool exists and is enabled, then executes it with a timeout.

    Args:
        context: The run context from pydantic-ai
        tool_name: Name of the tool to call (required)
        tool_args: Arguments to pass to the tool function

    Returns:
        UniversalConstructorOutput with call_result on success or error on failure
    """
    if not tool_name:
        return UniversalConstructorOutput(
            action="call",
            success=False,
            error="tool_name is required for call action",
        )

    from code_puppy.plugins.universal_constructor.registry import get_registry

    registry = get_registry()
    tool = registry.get_tool(tool_name)

    if not tool:
        return UniversalConstructorOutput(
            action="call",
            success=False,
            error=f"Tool '{tool_name}' not found",
        )

    if not tool.meta.enabled:
        return UniversalConstructorOutput(
            action="call",
            success=False,
            error=f"Tool '{tool_name}' is disabled",
        )

    # Read source for preview
    source_preview = None
    if tool.source_path:
        try:
            from pathlib import Path

            source_code = Path(tool.source_path).read_text(encoding="utf-8")
            source_preview = _generate_preview(source_code)
        except Exception:
            pass  # Preview is optional, don't fail on read errors

    func = registry.get_tool_function(tool_name)
    if not func:
        return UniversalConstructorOutput(
            action="call",
            success=False,
            error=f"Could not load function for '{tool_name}'",
        )

    # Handle tool_args being passed as a JSON string (XML marshaling issue)
    args = tool_args or {}
    if isinstance(args, str):
        try:
            import json

            args = json.loads(args)
        except json.JSONDecodeError:
            return UniversalConstructorOutput(
                action="call",
                success=False,
                error=f"Invalid tool_args: expected dict or JSON string, got: {args[:100]}",
            )
    if not isinstance(args, dict):
        return UniversalConstructorOutput(
            action="call",
            success=False,
            error=f"tool_args must be a dict, got {type(args).__name__}",
        )
    start_time = time.time()

    try:
        # Execute with timeout using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, **args)
            result = future.result(timeout=30)

        execution_time = time.time() - start_time

        return UniversalConstructorOutput(
            action="call",
            success=True,
            call_result=UCCallOutput(
                success=True,
                tool_name=tool_name,
                result=result,
                execution_time=execution_time,
                source_preview=source_preview,
            ),
        )
    except FuturesTimeoutError:
        return UniversalConstructorOutput(
            action="call",
            success=False,
            error=f"Tool '{tool_name}' timed out after 30s",
        )
    except TypeError as e:
        # Invalid arguments
        return UniversalConstructorOutput(
            action="call",
            success=False,
            error=f"Invalid arguments for '{tool_name}': {e!s}",
        )
    except Exception as e:
        return UniversalConstructorOutput(
            action="call",
            success=False,
            error=f"Tool execution failed: {e!s}",
        )


def _handle_create_action(
    context: RunContext,
    tool_name: Optional[str],
    python_code: Optional[str],
    description: Optional[str],
) -> UniversalConstructorOutput:
    """Handle the 'create' action - create a new UC tool.

    Creates a new tool from Python source code. The code can either include
    a TOOL_META dictionary, or one will be generated from the provided
    tool_name and description parameters.

    Supports namespacing via dot notation in tool_name:
    - "weather" → weather.py
    - "api.weather" → api/weather.py
    - "api.finance.stocks" → api/finance/stocks.py

    Args:
        context: The run context from pydantic-ai
        tool_name: Name of the tool (with optional namespace). Required if
            code doesn't contain TOOL_META.
        python_code: Python source code defining the tool function (required)
        description: Description of what the tool does. Used if no TOOL_META
            in code.

    Returns:
        UniversalConstructorOutput with create_result on success
    """
    from datetime import datetime
    from pathlib import Path

    from code_puppy.plugins.universal_constructor import USER_UC_DIR
    from code_puppy.plugins.universal_constructor.registry import get_registry
    from code_puppy.plugins.universal_constructor.sandbox import (
        _extract_tool_meta,
        _validate_tool_meta,
        check_dangerous_patterns,
        extract_function_info,
        validate_syntax,
    )

    # Validate python_code is provided
    if not python_code or not python_code.strip():
        return UniversalConstructorOutput(
            action="create",
            success=False,
            error="python_code is required for create action",
        )

    # Validate syntax
    syntax_result = validate_syntax(python_code)
    if not syntax_result.valid:
        error_msg = "; ".join(syntax_result.errors)
        return UniversalConstructorOutput(
            action="create",
            success=False,
            error=f"Syntax error in code: {error_msg}",
        )

    # Extract function info
    func_result = extract_function_info(python_code)
    if not func_result.functions:
        return UniversalConstructorOutput(
            action="create",
            success=False,
            error="No functions found in code - tool must have at least one function",
        )

    # Get the first function as the main tool function
    main_func = func_result.functions[0]

    # Try to extract TOOL_META from code
    existing_meta = _extract_tool_meta(python_code)

    # Determine final tool name and namespace
    if existing_meta and "name" in existing_meta:
        # Use name from TOOL_META
        final_name = existing_meta["name"]
        final_namespace = existing_meta.get("namespace", "")
    elif tool_name:
        # Parse namespace from tool_name (e.g., "api.weather" → namespace="api", name="weather")
        parts = tool_name.rsplit(".", 1)
        if len(parts) == 2:
            final_namespace, final_name = parts[0], parts[1]
        else:
            final_namespace, final_name = "", parts[0]
    else:
        # Use function name as tool name
        final_name = main_func.name
        final_namespace = ""

    # Validate we have a name
    if not final_name:
        return UniversalConstructorOutput(
            action="create",
            success=False,
            error="Could not determine tool name - provide tool_name or include TOOL_META in code",
        )

    # Build file path based on namespace
    if final_namespace:
        # Convert dot notation to path (api.finance → api/finance/)
        namespace_path = Path(*final_namespace.split("."))
        file_dir = USER_UC_DIR / namespace_path
    else:
        file_dir = USER_UC_DIR

    file_path = file_dir / f"{final_name}.py"

    # Build the final code to write
    validation_warnings = []

    if existing_meta:
        # Validate existing TOOL_META has required fields
        meta_errors = _validate_tool_meta(existing_meta)
        if meta_errors:
            return UniversalConstructorOutput(
                action="create",
                success=False,
                error="Invalid TOOL_META: " + "; ".join(meta_errors),
            )
        # Code already has TOOL_META, use as-is
        final_code = python_code
        # Collect any validation warnings
        validation_warnings.extend(func_result.warnings)
    else:
        # Generate TOOL_META and prepend to code
        final_description = description or main_func.docstring or f"Tool: {final_name}"

        generated_meta = {
            "name": final_name,
            "namespace": final_namespace,
            "description": final_description,
            "enabled": True,
            "version": "1.0.0",
            "author": "user",
            "created_at": datetime.now().isoformat(),
        }

        # Format TOOL_META as a dict literal
        meta_str = f"TOOL_META = {repr(generated_meta)}\n\n"
        final_code = meta_str + python_code
        validation_warnings.append("TOOL_META was auto-generated")
        validation_warnings.extend(func_result.warnings)

    # Check for dangerous patterns (warning only, don't block)
    safety_result = check_dangerous_patterns(python_code)
    validation_warnings.extend(safety_result.warnings)

    # Ensure directory exists and write file
    try:
        file_dir.mkdir(parents=True, exist_ok=True)
        file_path.write_text(final_code, encoding="utf-8")
    except Exception as e:
        return UniversalConstructorOutput(
            action="create",
            success=False,
            error=f"Failed to write tool file: {e}",
        )

    # Run ruff format on the new file
    format_warning = _run_ruff_format(file_path)
    if format_warning:
        validation_warnings.append(format_warning)

    # Read formatted code for preview
    formatted_code = file_path.read_text(encoding="utf-8")

    # Reload registry to pick up the new tool
    try:
        registry = get_registry()
        registry.reload()
    except Exception as e:
        # Tool was written but registry reload failed - still a partial success
        validation_warnings.append(f"Tool created but registry reload failed: {e}")

    # Build full name for response
    full_name = f"{final_namespace}.{final_name}" if final_namespace else final_name

    return UniversalConstructorOutput(
        action="create",
        success=True,
        create_result=UCCreateOutput(
            success=True,
            tool_name=full_name,
            source_path=str(file_path),
            preview=_generate_preview(formatted_code),
            validation_warnings=validation_warnings,
        ),
    )


def _handle_update_action(
    context: RunContext,
    tool_name: Optional[str],
    python_code: Optional[str],
    description: Optional[str],
) -> UniversalConstructorOutput:
    """Handle the 'update' action - modify an existing UC tool.

    Replaces an existing tool's code with new Python source code.
    The new code must contain a valid TOOL_META dictionary.

    Note: To update description or other metadata, include the changes
    in the TOOL_META of the python_code. The description parameter is
    reserved for future use but currently ignored.

    Args:
        context: The run context from pydantic-ai
        tool_name: Name of the tool to update (required)
        python_code: New Python source code (required)
        description: Reserved for future use (currently ignored)

    Returns:
        UniversalConstructorOutput with update_result on success
    """
    from pathlib import Path

    from code_puppy.plugins.universal_constructor.registry import get_registry
    from code_puppy.plugins.universal_constructor.sandbox import (
        _extract_tool_meta,
        _validate_tool_meta,
        validate_syntax,
    )

    if not tool_name:
        return UniversalConstructorOutput(
            action="update",
            success=False,
            error="tool_name is required for update action",
        )

    # python_code is required for updates
    if not python_code:
        return UniversalConstructorOutput(
            action="update",
            success=False,
            error="python_code is required for update action",
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
    source_path_obj = Path(source_path) if source_path else None
    if not source_path_obj or not source_path_obj.exists():
        return UniversalConstructorOutput(
            action="update",
            success=False,
            error="Tool has no source path or file does not exist",
        )

    try:
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

        # Validate TOOL_META has required fields
        meta_errors = _validate_tool_meta(new_meta)
        if meta_errors:
            return UniversalConstructorOutput(
                action="update",
                success=False,
                error="Invalid TOOL_META: " + "; ".join(meta_errors),
            )

        # Write updated code
        source_path_obj.write_text(python_code, encoding="utf-8")

        # Run ruff format on the updated file
        format_warning = _run_ruff_format(source_path_obj)
        changes = ["Replaced source code"]
        if format_warning:
            changes.append(f"Format warning: {format_warning}")
        else:
            changes.append("Formatted with ruff")

        # Read formatted code for preview
        formatted_code = source_path_obj.read_text(encoding="utf-8")

        # Reload registry to pick up changes
        registry.reload()

        return UniversalConstructorOutput(
            action="update",
            success=True,
            update_result=UCUpdateOutput(
                success=True,
                tool_name=tool_name,
                source_path=source_path,
                preview=_generate_preview(formatted_code),
                changes_applied=changes,
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
    from pathlib import Path

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
    source_path_obj = Path(source_path) if source_path else None
    if source_path_obj and source_path_obj.exists():
        try:
            source_code = source_path_obj.read_text(encoding="utf-8")
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
        """Universal Constructor - Your gateway to unlimited capabilities.

        **YOU CAN BUILD ANYTHING.** The Universal Constructor empowers you to create
        any tool you can imagine using Python. If you can write Python code for it,
        you can make it a permanent, reusable tool. This is your superpower.

        **CAPABILITIES YOU CAN CREATE:**
        - API integrations (REST, GraphQL, webhooks, any HTTP service)
        - Database connectors (SQL, NoSQL, any data store)
        - File processors (parsers, converters, analyzers for any format)
        - Web scrapers and data extractors
        - Mathematical and scientific computations
        - Text processing and NLP utilities
        - Image and media manipulation (with PIL, etc.)
        - System utilities and automation scripts
        - Network tools (DNS, HTTP, socket operations)
        - Cryptographic functions
        - Data transformation pipelines
        - Custom business logic for any domain
        - Integration with any Python library (requests, pandas, numpy, etc.)
        - Scheduled tasks and background operations
        - Custom validators and formatters
        - Domain-specific calculators
        - ANY Python functionality you need!

        **WHEN TO USE THIS:**
        - User asks for something your current tools can't do
        - You need to call an external API or service
        - You need custom data processing logic
        - You want to automate a repetitive task
        - You need domain-specific functionality
        - ANY time you think "I wish I had a tool that..."

        **PHILOSOPHY:** Don't say "I can't do that" - instead, BUILD a tool that can!
        Tools you create persist across sessions, so build once, use forever.

        Args:
            action: The operation to perform:
                - "list": List all available custom tools with their metadata
                - "call": Execute a specific custom tool with provided arguments
                - "create": Create a new tool from Python code
                - "update": Modify an existing tool's code or metadata
                - "info": Get detailed information about a specific tool
            tool_name: Name of the tool (required for call/update/info actions).
                Supports namespaced format like "namespace.tool_name" for organization.
            tool_args: Dictionary of arguments to pass when calling a tool.
                Only used with action="call".
            python_code: Python source code defining the tool function.
                Required for action="create" and action="update".
                You have access to the FULL Python standard library plus any
                installed packages (requests, etc.).
            description: Human-readable description of what the tool does.
                Used with action="create".

        Returns:
            UniversalConstructorOutput with action-specific results.

        Examples:
            # Create an API client tool
            code = '''
            import requests
            TOOL_META = {"name": "weather", "description": "Get weather data"}
            def weather(city: str) -> dict:
                resp = requests.get(f"https://wttr.in/{city}?format=j1")
                return resp.json()
            '''
            universal_constructor(ctx, action="create", python_code=code)

            # Create a data processor
            code = '''
            import json
            TOOL_META = {"name": "csv_to_json", "description": "Convert CSV to JSON"}
            def csv_to_json(csv_text: str) -> list:
                lines = csv_text.strip().split("\\n")
                headers = lines[0].split(",")
                return [{h: v for h, v in zip(headers, line.split(","))}
                        for line in lines[1:]]
            '''
            universal_constructor(ctx, action="create", python_code=code)

            # Create a utility tool
            code = '''
            import hashlib
            TOOL_META = {"name": "hasher", "description": "Hash strings"}
            def hasher(text: str, algorithm: str = "sha256") -> str:
                h = hashlib.new(algorithm)
                h.update(text.encode())
                return h.hexdigest()
            '''
            universal_constructor(ctx, action="create", python_code=code)

        Note:
            Tools are stored in ~/.code_puppy/plugins/universal_constructor/ and
            persist forever. Organize with namespaces: "api.weather", "utils.hasher".
            Code is auto-formatted with ruff. Check existing tools with action="list".
        """
        return await universal_constructor_impl(
            context, action, tool_name, tool_args, python_code, description
        )
