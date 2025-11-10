from __future__ import annotations

from typing import Any, Dict

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info
from code_puppy.tools.common import generate_group_id

from .workflow_executor import WorkflowExecutor


async def execute_workflow(
    context: RunContext,
    name: str,
    parameters: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Execute a saved workflow with optional parameters.

    Args:
        context: RunContext from pydantic-ai
        name: Workflow name (with or without .yaml extension)
        parameters: Optional parameters to pass to workflow (replaces variables)

    Returns:
        Execution results as dict (converted from WorkflowExecutionResult)
    """
    group_id = generate_group_id("execute_workflow", name)
    emit_info(
        f"[bold white on green] EXECUTE WORKFLOW [/bold white on green] ▶️ name='{name}'",
        message_group=group_id,
    )

    try:
        executor = WorkflowExecutor(context)

        # Support legacy 'variables' alongside new 'parameters'
        if parameters:
            executor.variables = parameters

        result = await executor.execute_workflow_file(name, parameters)

        # Redact sensitive parameters from logs
        if parameters:
            # TODO: Check parameter definitions for 'sensitive' flag
            {
                k: "***" if "password" in k.lower() or "secret" in k.lower() else v
                for k, v in parameters.items()
            }

        emit_info(
            f"[green]✅ Workflow '{result.workflow}' completed: "
            f"{result.status} - {result.steps_executed} executed, {result.steps_skipped} skipped[/green]",
            message_group=group_id,
        )

        if result.outputs:
            emit_info(
                f"📤 Outputs: {list(result.outputs.keys())}", message_group=group_id
            )

        # Convert Pydantic model to dict for backward compatibility
        return result.model_dump()

    except Exception as e:
        emit_error(
            f"[red]❌ Workflow execution failed: {e}[/red]",
            message_group=group_id,
        )
        return {
            "workflow": name,
            "status": "failure",
            "execution_time": 0,
            "parameters_used": parameters or {},
            "outputs": {},
            "steps_executed": 0,
            "steps_skipped": 0,
            "errors": [str(e)],
            "screenshots": [],
        }


def register_executor_tool(agent):
    """Register the workflow executor tool."""

    @agent.tool
    async def gui_cub_execute_workflow(
        context: RunContext,
        name: str,
        parameters: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """⚠️ DEPRECATED - DO NOT USE - Use gui_cub_read_workflow instead!

        **WHY DEPRECATED:**
        This tool executes workflows MECHANICALLY without agent intelligence.
        Workflows should be GUIDANCE that you INTERPRET and ACT ON intelligently,
        not automation scripts that execute blindly.

        **USE THIS INSTEAD:**
        ```python
        # ✅ CORRECT - Read workflow guidance and interpret intelligently
        workflow = gui_cub_read_workflow(name="login")
        content = workflow["content"]
        
        # Review the guidance, plan your approach, use your intelligence
        # Decide which tools to call based on current context
        # Adapt if steps don't work as expected
        ```

        **WHY THIS IS WRONG:**
        - Bypasses your intelligence and decision-making
        - Cannot adapt when steps fail
        - Treats workflows as rigid automation scripts
        - Ignores current UI state and context
        
        **This tool remains functional ONLY for backward compatibility.**
        **It will be removed in a future release.**
        **DO NOT use this tool in new code.**

        Args:
            name: Workflow name (e.g., 'login', 'login.yaml')
            parameters: Optional dict of parameters

        Returns:
            Execution results (but you should use gui_cub_read_workflow instead!)
        """
        # Emit deprecation warning
        from code_puppy.messaging import emit_warning
        emit_warning(
            "⚠️ gui_cub_execute_workflow is DEPRECATED. "
            "Use gui_cub_read_workflow to read guidance and make intelligent decisions. "
            "Mechanical workflow execution bypasses agent intelligence."
        )
        
        return await execute_workflow(context, name, parameters)
