"""Type stubs for workflow management.

Provides workflow saving, listing, and reading.
"""

from typing import Any

async def save_workflow(
    name: str,
    content: str,
    format: str = ...,
) -> dict[str, Any]:
    """Save a GUI-Cub workflow for reuse.

    Args:
        name: Workflow name (e.g., 'login_flow', 'data_entry')
        content: Workflow content (YAML structure or Markdown documentation)
        format: 'yaml' for executable workflows, 'markdown' for docs (default: 'yaml')

    Returns:
        Dict with success status, path, and metadata

    Example:
        workflow_yaml = '''
        name: "Login Flow"
        steps:
          - action: focus_window
            app: "Safari"
          - action: type
            text: "username"
        '''
        result = await save_workflow("login_flow", workflow_yaml)
    """
    ...

async def list_workflows() -> dict[str, Any]:
    """List all saved GUI-Cub workflows.

    Returns:
        Dict with workflows list, count, and directory path

    Example:
        result = await list_workflows()
        for workflow in result["workflows"]:
            print(workflow["name"])
    """
    ...

async def read_workflow(
    name: str,
) -> dict[str, Any]:
    """Read a saved GUI-Cub workflow.

    Args:
        name: Workflow name (with or without extension)

    Returns:
        Dict with content, parsed YAML (if applicable), and metadata

    Example:
        result = await read_workflow("login_flow")
        print(result["content"])
    """
    ...
