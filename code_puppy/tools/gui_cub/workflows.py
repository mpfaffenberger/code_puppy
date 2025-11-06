"""GUI-Cub workflow management tools for saving and reusing automation patterns."""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.common import generate_group_id


class WorkflowParameter(BaseModel):
    """Define an input parameter for a workflow."""

    name: str = Field(..., description="Parameter name")
    type: str = Field(
        default="string",
        description="Parameter type: string, number, boolean, array, object",
    )
    description: str = Field(default="", description="Human-readable description")
    required: bool = Field(
        default=True, description="Whether this parameter is required"
    )
    default: Any = Field(default=None, description="Default value if not provided")
    sensitive: bool = Field(
        default=False, description="Whether to redact from logs (e.g., passwords)"
    )
    example: Optional[str] = Field(
        default=None, description="Example value for documentation"
    )


class WorkflowOutput(BaseModel):
    """Define an output that the workflow should return."""

    name: str = Field(..., description="Output variable name")
    description: str = Field(default="", description="What this output contains")
    extraction_method: str = Field(
        default="manual", description="How to extract: ocr, screenshot, manual"
    )


def get_workflows_directory() -> Path:
    """Get the GUI-Cub workflows directory, creating it if it doesn't exist."""
    home_dir = Path.home()
    workflows_dir = home_dir / ".code_puppy" / "agents" / "gui_cub" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    return workflows_dir


def parse_workflow_parameters(workflow_data: Dict[str, Any]) -> List[WorkflowParameter]:
    """Parse parameter definitions from workflow YAML.

    Args:
        workflow_data: Parsed workflow YAML

    Returns:
        List of WorkflowParameter objects
    """
    if "parameters" not in workflow_data:
        return []

    parameters = []
    for param_dict in workflow_data["parameters"]:
        try:
            param = WorkflowParameter(**param_dict)
            parameters.append(param)
        except Exception as e:
            emit_warning(f"Invalid parameter definition: {param_dict}. Error: {e}")

    return parameters


def parse_workflow_outputs(workflow_data: Dict[str, Any]) -> List[WorkflowOutput]:
    """Parse output definitions from workflow YAML.

    Args:
        workflow_data: Parsed workflow YAML

    Returns:
        List of WorkflowOutput objects
    """
    if "outputs" not in workflow_data:
        return []

    outputs = []
    for output_dict in workflow_data["outputs"]:
        try:
            output = WorkflowOutput(**output_dict)
            outputs.append(output)
        except Exception as e:
            emit_warning(f"Invalid output definition: {output_dict}. Error: {e}")

    return outputs


def validate_workflow_parameters(
    parameters: List[WorkflowParameter], provided_values: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate provided parameter values against workflow schema.

    Args:
        parameters: List of parameter definitions
        provided_values: Dict of parameter values provided by caller

    Returns:
        Validated parameter dict with defaults applied

    Raises:
        ValueError: If required parameters are missing or types don't match
    """
    validated = {}

    for param in parameters:
        value = provided_values.get(param.name)

        # Check if required parameter is missing
        if param.required and value is None:
            if param.default is not None:
                value = param.default
            else:
                raise ValueError(f"Missing required parameter: {param.name}")

        # Use default if not provided and default exists
        if value is None and param.default is not None:
            value = param.default

        # Type validation
        if value is not None:
            if param.type == "string" and not isinstance(value, str):
                # Auto-convert to string for string parameters
                value = str(value)
            elif param.type == "number":
                if not isinstance(value, (int, float)):
                    try:
                        value = float(value) if "." in str(value) else int(value)
                    except ValueError:
                        raise TypeError(
                            f"Parameter '{param.name}' must be number, got {type(value).__name__}"
                        )
            elif param.type == "boolean":
                if not isinstance(value, bool):
                    # Convert string boolean representations
                    if isinstance(value, str):
                        if value.lower() in ("true", "yes", "1"):
                            value = True
                        elif value.lower() in ("false", "no", "0"):
                            value = False
                        else:
                            raise TypeError(
                                f"Parameter '{param.name}' must be boolean, got '{value}'"
                            )
                    else:
                        value = bool(value)
            elif param.type == "array" and not isinstance(value, list):
                raise TypeError(
                    f"Parameter '{param.name}' must be array, got {type(value).__name__}"
                )
            elif param.type == "object" and not isinstance(value, dict):
                raise TypeError(
                    f"Parameter '{param.name}' must be object, got {type(value).__name__}"
                )

        if value is not None:
            validated[param.name] = value

    return validated


async def save_workflow(
    name: str, content: str, format: str = "yaml"
) -> Dict[str, Any]:
    """Save a GUI-Cub workflow as YAML or Markdown.

    Args:
        name: Workflow name
        content: Workflow content (YAML or Markdown)
        format: "yaml" or "markdown" (default: "yaml")
    """
    group_id = generate_group_id("save_workflow", name)
    emit_info(
        f"[bold white on green] SAVE WORKFLOW [/bold white on green] 💾 name='{name}', format='{format}'",
        message_group=group_id,
    )

    try:
        workflows_dir = get_workflows_directory()

        # Clean up the filename
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).lower()
        if not safe_name:
            safe_name = "workflow"

        # Add extension based on format
        if format == "yaml":
            if not safe_name.endswith((".yaml", ".yml")):
                safe_name += ".yaml"
        else:  # markdown
            if not safe_name.endswith(".md"):
                safe_name += ".md"

        workflow_path = workflows_dir / safe_name

        # Validate YAML if format is yaml
        if format == "yaml":
            try:
                yaml.safe_load(content)
            except yaml.YAMLError as e:
                emit_warning(f"Warning: YAML validation failed: {e}")

        # Write the workflow content
        with open(workflow_path, "w", encoding="utf-8") as f:
            f.write(content)

        emit_info(
            f"[green]✅ Workflow saved successfully: {workflow_path}[/green]",
            message_group=group_id,
        )

        return {
            "success": True,
            "path": str(workflow_path),
            "name": safe_name,
            "size": len(content),
            "format": format,
        }

    except Exception as e:
        emit_info(
            f"[red]❌ Failed to save workflow: {e}[/red]",
            message_group=group_id,
        )
        return {"success": False, "error": str(e), "name": name}


async def list_workflows() -> Dict[str, Any]:
    """List all available GUI-Cub workflows."""
    group_id = generate_group_id("list_workflows")
    emit_info(
        "[bold white on green] LIST WORKFLOWS [/bold white on green] 📋",
        message_group=group_id,
    )

    try:
        workflows_dir = get_workflows_directory()

        # Find all workflow files (.yaml, .yml, .md)
        workflow_files = list(workflows_dir.glob("*.yaml"))
        workflow_files.extend(workflows_dir.glob("*.yml"))
        workflow_files.extend(workflows_dir.glob("*.md"))

        workflows = []
        for workflow_file in workflow_files:
            try:
                stat = workflow_file.stat()
                workflows.append(
                    {
                        "name": workflow_file.name,
                        "path": str(workflow_file),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "format": "yaml"
                        if workflow_file.suffix in (".yaml", ".yml")
                        else "markdown",
                    }
                )
            except Exception as e:
                emit_info(
                    f"[yellow]Warning: Could not read {workflow_file}: {e}[/yellow]"
                )

        # Sort by modification time (newest first)
        workflows.sort(key=lambda x: x["modified"], reverse=True)

        emit_info(
            f"[green]✅ Found {len(workflows)} workflow(s)[/green]",
            message_group=group_id,
        )

        return {
            "success": True,
            "workflows": workflows,
            "count": len(workflows),
            "directory": str(workflows_dir),
        }

    except Exception as e:
        emit_info(
            f"[red]❌ Failed to list workflows: {e}[/red]",
            message_group=group_id,
        )
        return {"success": False, "error": str(e)}


async def read_workflow(name: str) -> Dict[str, Any]:
    """Read a saved GUI-Cub workflow."""
    group_id = generate_group_id("read_workflow", name)
    emit_info(
        f"[bold white on green] READ WORKFLOW [/bold white on green] 📖 name='{name}'",
        message_group=group_id,
    )

    try:
        workflows_dir = get_workflows_directory()

        # Try multiple extensions
        possible_paths = [
            workflows_dir / name,
            workflows_dir / f"{name}.yaml",
            workflows_dir / f"{name}.yml",
            workflows_dir / f"{name}.md",
        ]

        workflow_path = None
        for path in possible_paths:
            if path.exists():
                workflow_path = path
                break

        if not workflow_path:
            emit_info(
                f"[red]❌ Workflow not found: {name}[/red]",
                message_group=group_id,
            )
            return {
                "success": False,
                "error": f"Workflow '{name}' not found",
                "name": name,
            }

        # Read the workflow content
        with open(workflow_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Determine format
        format_type = (
            "yaml" if workflow_path.suffix in (".yaml", ".yml") else "markdown"
        )

        # Parse YAML if applicable
        parsed_data = None
        if format_type == "yaml":
            try:
                parsed_data = yaml.safe_load(content)
            except yaml.YAMLError as e:
                emit_warning(f"Warning: Failed to parse YAML: {e}")

        emit_info(
            f"[green]✅ Workflow read successfully: {workflow_path.name}[/green]",
            message_group=group_id,
        )

        return {
            "success": True,
            "name": workflow_path.name,
            "path": str(workflow_path),
            "content": content,
            "format": format_type,
            "parsed": parsed_data,
            "size": len(content),
        }

    except Exception as e:
        emit_info(
            f"[red]❌ Failed to read workflow: {e}[/red]",
            message_group=group_id,
        )
        return {"success": False, "error": str(e), "name": name}


def register_workflow_tools(agent):
    """Register workflow management tools."""

    @agent.tool
    async def gui_cub_save_workflow(
        context: RunContext,
        name: str,
        content: str,
        format: str = "yaml",
    ) -> Dict[str, Any]:
        """Save a GUI-Cub workflow for reuse.

        Workflows are reusable automation patterns that can be:
        - Executed automatically with gui_cub_execute_workflow()
        - Adapted for similar tasks
        - Shared across sessions

        Args:
            name: Workflow name (e.g., 'login_flow', 'data_entry')
            content: Workflow content (YAML structure or Markdown documentation)
            format: 'yaml' for executable workflows, 'markdown' for docs (default: 'yaml')

        Returns:
            Dict with success status, path, and metadata

        Example YAML workflow:
        ```yaml
        name: "Login Flow"
        variables:
          username: "user@example.com"
          password: "{{env.PASSWORD}}"

        steps:
          - action: focus_window
            app: "TextEdit"
          - action: click
            element: {title: "Username"}
          - action: type
            text: "{{username}}"
          - action: click
            element: {title: "Password"}
          - action: type
            text: "{{password}}"
          - action: press
            key: "enter"
        ```
        """
        return await save_workflow(name, content, format)

    @agent.tool
    async def gui_cub_list_workflows(context: RunContext) -> Dict[str, Any]:
        """List all saved GUI-Cub workflows.

        Returns workflows sorted by modification time (newest first).
        Use this BEFORE creating new workflows to avoid duplication.

        Returns:
            Dict with workflows list, count, and directory path
        """
        return await list_workflows()

    @agent.tool
    async def gui_cub_read_workflow(
        context: RunContext,
        name: str,
    ) -> Dict[str, Any]:
        """Read a saved GUI-Cub workflow.

        Use this to:
        - Review existing workflows before adapting
        - Load workflows for execution
        - Check workflow structure

        Args:
            name: Workflow name (with or without extension)

        Returns:
            Dict with content, parsed YAML (if applicable), and metadata
        """
        return await read_workflow(name)
