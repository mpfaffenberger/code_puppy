"""Browser workflow management tools for saving and reusing automation patterns."""

from pathlib import Path
from typing import Any, Dict

from pydantic_ai import RunContext

from code_puppy.messaging import emit_info
from code_puppy.tools.common import generate_group_id


def get_workflows_directory() -> Path:
    """Get the browser workflows directory, creating it if it doesn't exist."""
    home_dir = Path.home()
    workflows_dir = home_dir / ".code_puppy" / "browser_workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    return workflows_dir


async def save_workflow(name: str, content: str) -> Dict[str, Any]:
    """Save a browser workflow as a markdown file."""
    group_id = generate_group_id("save_workflow", name)
    emit_info(
        f"[bold white on blue] SAVE WORKFLOW [/bold white on blue] 💾 name='{name}'",
        message_group=group_id,
    )

    try:
        workflows_dir = get_workflows_directory()

        # Clean up the filename - remove spaces, special chars, etc.
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).lower()
        if not safe_name:
            safe_name = "workflow"

        # Ensure .md extension
        if not safe_name.endswith(".md"):
            safe_name += ".md"

        workflow_path = workflows_dir / safe_name

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
        }

    except Exception as e:
        emit_info(
            f"[red]❌ Failed to save workflow: {e}[/red]",
            message_group=group_id,
        )
        return {"success": False, "error": str(e), "name": name}


async def list_workflows() -> Dict[str, Any]:
    """List all available browser workflows."""
    group_id = generate_group_id("list_workflows")
    emit_info(
        "[bold white on blue] LIST WORKFLOWS [/bold white on blue] 📋",
        message_group=group_id,
    )

    try:
        workflows_dir = get_workflows_directory()

        # Find all .md files in the workflows directory
        workflow_files = list(workflows_dir.glob("*.md"))

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
    """Read a saved browser workflow."""
    group_id = generate_group_id("read_workflow", name)
    emit_info(
        f"[bold white on blue] READ WORKFLOW [/bold white on blue] 📖 name='{name}'",
        message_group=group_id,
    )

    try:
        workflows_dir = get_workflows_directory()

        # Handle both with and without .md extension
        if not name.endswith(".md"):
            name += ".md"

        workflow_path = workflows_dir / name

        if not workflow_path.exists():
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

        emit_info(
            f"[green]✅ Workflow read successfully: {len(content)} characters[/green]",
            message_group=group_id,
        )

        return {
            "success": True,
            "name": name,
            "content": content,
            "path": str(workflow_path),
            "size": len(content),
        }

    except Exception as e:
        emit_info(
            f"[red]❌ Failed to read workflow: {e}[/red]",
            message_group=group_id,
        )
        return {"success": False, "error": str(e), "name": name}


def register_save_workflow(agent):
    """Register the save workflow tool."""

    @agent.tool
    async def browser_save_workflow(
        context: RunContext,
        name: str,
        content: str,
    ) -> Dict[str, Any]:
        """Save a browser automation workflow to disk for future reuse."""
        return await save_workflow(name, content)


def register_list_workflows(agent):
    """Register the list workflows tool."""

    @agent.tool
    async def browser_list_workflows(context: RunContext) -> Dict[str, Any]:
        """List all saved browser automation workflows."""
        return await list_workflows()


def register_read_workflow(agent):
    """Register the read workflow tool."""

    @agent.tool
    async def browser_read_workflow(
        context: RunContext,
        name: str,
    ) -> Dict[str, Any]:
        """Read the contents of a saved browser automation workflow."""
        return await read_workflow(name)
