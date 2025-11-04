"""GUI-Cub workflow management tools for saving and reusing automation patterns."""

from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic_ai import RunContext

from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.common import generate_group_id


def get_workflows_directory() -> Path:
    """Get the GUI-Cub workflows directory, creating it if it doesn't exist."""
    home_dir = Path.home()
    workflows_dir = home_dir / ".code_puppy" / "gui_cub_workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    return workflows_dir


async def save_workflow(name: str, content: str, format: str = "yaml") -> Dict[str, Any]:
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
                        "format": "yaml" if workflow_file.suffix in (".yaml", ".yml") else "markdown",
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
        format_type = "yaml" if workflow_path.suffix in (".yaml", ".yml") else "markdown"

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
            app: "Chrome"
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
