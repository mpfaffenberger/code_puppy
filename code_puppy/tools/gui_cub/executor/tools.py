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
        """Execute a saved YAML workflow with optional parameters.

        This enables true automation - workflows are executed automatically
        without agent interpretation. Supports workflow chaining via run_workflow.

        NEW: Workflows can now define typed parameters and return structured outputs!

        Args:
            name: Workflow name (e.g., 'login', 'login.yaml')
            parameters: Optional dict of parameters to pass to workflow
                       Example: {"username": "user@example.com", "patient_id": "PAT-123"}

        Returns:
            Structured execution results:
            {
                "workflow": str,
                "status": "success" | "failure" | "partial",
                "execution_time": float,
                "parameters_used": dict,
                "outputs": dict,  # Extracted data from workflow
                "steps_executed": int,
                "steps_skipped": int,
                "errors": list,
                "screenshots": list
            }

        Example:
            gui_cub_execute_workflow(
                name="patient_lookup",
                parameters={"patient_id": "PAT-67890", "include_history": False}
            )
        """
        return await execute_workflow(context, name, parameters)
