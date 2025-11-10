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
    workflows_dir = home_dir / ".code_puppy" / "agents" / "gui_cub" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    return workflows_dir


async def save_workflow(
    name: str, content: str, format: str = "markdown"
) -> Dict[str, Any]:
    """Save a GUI-Cub workflow as YAML or Markdown.

    Args:
        name: Workflow name
        content: Workflow content (YAML or Markdown)
        format: "markdown" or "yaml" (default: "markdown")
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
        format: str = "markdown",
    ) -> Dict[str, Any]:
        """Save a GUI-Cub workflow as guidance documentation.

        Workflows document proven patterns and approaches for accomplishing tasks.
        They should be GUIDANCE that you interpret intelligently, NOT rigid automation.

        **PREFERRED FORMAT: Markdown** - Use this for all new workflows!

        Workflows should contain:
        - Goals and objectives (WHAT to accomplish)
        - Recommended approaches with suggested tools
        - Multiple strategies and alternatives
        - Common issues and solutions
        - Success criteria and tips

        Args:
            name: Workflow name (e.g., 'login_pattern', 'calculator_usage')
            content: Workflow content as Markdown documentation
            format: 'markdown' (preferred) or 'yaml' (legacy) - default: 'markdown'

        Returns:
            Dict with success status, path, and metadata

        Example Markdown workflow (PREFERRED):
        ```markdown
        # Login to Application

        ## Goal
        Authenticate user to the application

        ## Recommended Approach

        1. **Focus application window**
           - Tool: `desktop_focus_window(app="AppName")`

        2. **Locate username field**
           - Try OCR: `desktop_find_text("Username")`
           - Try UI: `ui_find_element(title="Username")`

        3. **Enter credentials**
           - Type username, tab to password, type password
           - Press Enter to submit

        ## Common Issues
        - Window not focused → Call focus_window first

        ## Success Criteria
        - Dashboard visible, no errors
        ```
        """
        return await save_workflow(name, content, format)

    @agent.tool
    async def gui_cub_list_workflows(context: RunContext) -> Dict[str, Any]:
        """List all saved GUI-Cub workflow guidance documents.

        Returns workflows sorted by modification time (newest first).

        **ALWAYS use this FIRST** before starting new tasks to:
        - Check if a similar workflow already exists
        - Learn from proven patterns
        - Avoid duplicating work

        Returns:
            Dict with workflows list, count, and directory path
        """
        return await list_workflows()

    @agent.tool
    async def gui_cub_read_workflow(
        context: RunContext,
        name: str,
    ) -> Dict[str, Any]:
        """Read a saved GUI-Cub workflow guidance document.

        **This is the CORRECT way to use workflows!**

        Read workflow content as GUIDANCE, then:
        1. Review the recommended approaches
        2. Interpret suggestions intelligently
        3. Decide which tools to use based on current context
        4. Adapt if steps don't work exactly as documented
        5. Use YOUR intelligence to accomplish the goal

        Workflows are DOCUMENTATION of proven patterns, NOT automation scripts.

        Args:
            name: Workflow name (with or without extension)

        Returns:
            Dict with content (Markdown or YAML), parsed data, and metadata
        """
        return await read_workflow(name)
