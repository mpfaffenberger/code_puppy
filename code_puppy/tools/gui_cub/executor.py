"""GUI-Cub workflow executor - Execute YAML workflows with chaining support."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml
from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails."""
    pass


class WorkflowExecutor:
    """Execute YAML workflows with variable interpolation and chaining."""

    def __init__(self, context: RunContext):
        self.context = context
        self.variables: Dict[str, Any] = {}
        self.workflow_dir = Path.home() / ".code_puppy" / "gui_cub_workflows"

    def interpolate_variables(self, value: Any) -> Any:
        """Replace {{variable}} placeholders with actual values.
        
        Supports:
        - {{var_name}} - from variables dict
        - {{env.VAR_NAME}} - from environment variables
        - {{step.output}} - from previous step outputs
        """
        if not isinstance(value, str):
            return value

        # Replace {{env.VAR}} with environment variables
        def replace_env(match):
            env_var = match.group(1)
            placeholder = "{{env." + env_var + "}}"
            return os.environ.get(env_var, placeholder)  # Keep placeholder if not found

        value = re.sub(r"{{env\.([^}]+)}}", replace_env, value)

        # Replace {{variable}} with values from self.variables
        def replace_var(match):
            var_name = match.group(1)
            if var_name in self.variables:
                return str(self.variables[var_name])
            return "{{" + var_name + "}}"  # Keep placeholder if not found

        value = re.sub(r"{{([^}]+)}}", replace_var, value)
        return value

    async def execute_action(self, action: Dict[str, Any], step_index: int) -> Any:
        """Execute a single workflow action.
        
        Supported actions:
        - focus_window
        - click
        - type
        - press
        - hotkey
        - sleep
        - run_workflow
        - verify
        """
        action_type = action.get("action")
        
        if not action_type:
            raise WorkflowExecutionError(f"Step {step_index}: Missing 'action' field")

        # Interpolate all action parameters
        interpolated_action = {}
        for key, value in action.items():
            if isinstance(value, str):
                interpolated_action[key] = self.interpolate_variables(value)
            elif isinstance(value, dict):
                interpolated_action[key] = {
                    k: self.interpolate_variables(v) if isinstance(v, str) else v
                    for k, v in value.items()
                }
            elif isinstance(value, list):
                interpolated_action[key] = [
                    self.interpolate_variables(v) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                interpolated_action[key] = value

        try:
            if action_type == "focus_window":
                return await self._execute_focus_window(interpolated_action)
            elif action_type == "click":
                return await self._execute_click(interpolated_action)
            elif action_type == "type":
                return await self._execute_type(interpolated_action)
            elif action_type == "press":
                return await self._execute_press(interpolated_action)
            elif action_type == "hotkey":
                return await self._execute_hotkey(interpolated_action)
            elif action_type == "sleep":
                return await self._execute_sleep(interpolated_action)
            elif action_type == "run_workflow":
                return await self._execute_run_workflow(interpolated_action)
            elif action_type == "verify":
                return await self._execute_verify(interpolated_action)
            else:
                raise WorkflowExecutionError(f"Unknown action type: {action_type}")
        
        except Exception as e:
            # Handle on_error if specified
            if "on_error" in action:
                emit_warning(f"Action failed: {e}. Executing error handler...")
                error_steps = action["on_error"]
                if isinstance(error_steps, list):
                    for error_step in error_steps:
                        await self.execute_action(error_step, step_index)
                return {"error": str(e), "handled": True}
            else:
                raise

    async def _execute_focus_window(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Focus a window by app name."""
        from code_puppy.tools.gui_cub.window_control import focus_window
        
        app_name = action.get("app") or action.get("window")
        if not app_name:
            raise WorkflowExecutionError("focus_window requires 'app' parameter")
        
        result = await focus_window(app_name)
        return {"success": result, "app": app_name}

    async def _execute_click(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Click an element using accessibility API."""
        from code_puppy.tools.gui_cub.os_unified import ui_click_element
        
        element = action.get("element", {})
        if not element:
            raise WorkflowExecutionError("click requires 'element' parameter")
        
        title = element.get("title")
        fuzzy = element.get("fuzzy", True)
        
        result = await ui_click_element(self.context, title=title, fuzzy=fuzzy)
        return result

    async def _execute_type(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Type text using keyboard."""
        from code_puppy.tools.gui_cub.keyboard_control import keyboard_type
        
        text = action.get("text")
        if text is None:
            raise WorkflowExecutionError("type requires 'text' parameter")
        
        await keyboard_type(text)
        return {"success": True, "text": text}

    async def _execute_press(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Press a key."""
        from code_puppy.tools.gui_cub.keyboard_control import keyboard_press
        
        key = action.get("key")
        if not key:
            raise WorkflowExecutionError("press requires 'key' parameter")
        
        await keyboard_press(key)
        return {"success": True, "key": key}

    async def _execute_hotkey(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Press a keyboard shortcut."""
        from code_puppy.tools.gui_cub.keyboard_control import keyboard_hotkey
        
        keys = action.get("keys")
        if not keys:
            raise WorkflowExecutionError("hotkey requires 'keys' parameter")
        
        if isinstance(keys, str):
            keys = [keys]
        
        await keyboard_hotkey(*keys)
        return {"success": True, "keys": keys}

    async def _execute_sleep(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Sleep for specified duration."""
        import asyncio
        
        duration = action.get("duration") or action.get("seconds")
        if duration is None:
            raise WorkflowExecutionError("sleep requires 'duration' or 'seconds' parameter")
        
        await asyncio.sleep(float(duration))
        return {"success": True, "duration": duration}

    async def _execute_run_workflow(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute another workflow (chaining)."""
        workflow_name = action.get("workflow") or action.get("name")
        if not workflow_name:
            raise WorkflowExecutionError("run_workflow requires 'workflow' parameter")
        
        # Get inputs for sub-workflow
        inputs = action.get("inputs", {})
        
        # Load and execute sub-workflow
        sub_executor = WorkflowExecutor(self.context)
        sub_executor.variables = {**self.variables, **inputs}  # Merge variables
        
        result = await sub_executor.execute_workflow_file(workflow_name)
        
        # Extract outputs if specified
        if "outputs" in action:
            outputs = action["outputs"]
            if isinstance(outputs, dict):
                for var_name, output_path in outputs.items():
                    # Simple output extraction (can be enhanced)
                    self.variables[var_name] = result.get("result", {})
        
        return result

    async def _execute_verify(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Verify expected text appears on screen."""
        from code_puppy.tools.gui_cub.ocr_tools import ocr_extract_text
        
        expected_text = action.get("expected_text") or action.get("text")
        if not expected_text:
            raise WorkflowExecutionError("verify requires 'expected_text' parameter")
        
        result = await ocr_extract_text()
        found = expected_text in result.get("full_text", "")
        
        if not found:
            raise WorkflowExecutionError(f"Verification failed: '{expected_text}' not found")
        
        return {"success": True, "verified": expected_text}

    async def execute_workflow_file(self, workflow_name: str) -> Dict[str, Any]:
        """Load and execute a workflow from file."""
        # Find workflow file
        possible_paths = [
            self.workflow_dir / workflow_name,
            self.workflow_dir / f"{workflow_name}.yaml",
            self.workflow_dir / f"{workflow_name}.yml",
        ]
        
        workflow_path = None
        for path in possible_paths:
            if path.exists():
                workflow_path = path
                break
        
        if not workflow_path:
            raise WorkflowExecutionError(f"Workflow not found: {workflow_name}")
        
        # Load YAML
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow_data = yaml.safe_load(f)
        
        return await self.execute_workflow(workflow_data)

    async def execute_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a workflow from parsed YAML data."""
        # Extract workflow variables
        if "variables" in workflow:
            workflow_vars = workflow["variables"]
            # Interpolate variable defaults
            for var_name, var_value in workflow_vars.items():
                if var_name not in self.variables:  # Don't override passed-in variables
                    self.variables[var_name] = self.interpolate_variables(var_value)
        
        # Execute steps
        steps = workflow.get("steps", [])
        if not steps:
            raise WorkflowExecutionError("Workflow has no steps")
        
        results = []
        for i, step in enumerate(steps):
            emit_info(f"Executing step {i + 1}/{len(steps)}: {step.get('action', 'unknown')}")
            result = await self.execute_action(step, i + 1)
            results.append(result)
        
        return {
            "success": True,
            "workflow": workflow.get("name", "unnamed"),
            "steps_executed": len(results),
            "results": results,
        }


async def execute_workflow(
    context: RunContext,
    name: str,
    variables: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Execute a saved workflow with optional variables.
    
    Args:
        context: RunContext from pydantic-ai
        name: Workflow name (with or without .yaml extension)
        variables: Optional variables to pass to workflow
    
    Returns:
        Execution results with success status
    """
    group_id = generate_group_id("execute_workflow", name)
    emit_info(
        f"[bold white on green] EXECUTE WORKFLOW [/bold white on green] ▶️ name='{name}'",
        message_group=group_id,
    )
    
    try:
        executor = WorkflowExecutor(context)
        
        if variables:
            executor.variables = variables
        
        result = await executor.execute_workflow_file(name)
        
        emit_info(
            f"[green]✅ Workflow executed successfully: {result['steps_executed']} steps[/green]",
            message_group=group_id,
        )
        
        return result
    
    except Exception as e:
        emit_error(
            f"[red]❌ Workflow execution failed: {e}[/red]",
            message_group=group_id,
        )
        return {
            "success": False,
            "error": str(e),
            "workflow": name,
        }


def register_executor_tool(agent):
    """Register the workflow executor tool."""

    @agent.tool
    async def gui_cub_execute_workflow(
        context: RunContext,
        name: str,
        variables: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Execute a saved YAML workflow with optional variables.
        
        This enables true automation - workflows are executed automatically
        without agent interpretation. Supports workflow chaining via run_workflow.
        
        Args:
            name: Workflow name (e.g., 'login', 'login.yaml')
            variables: Optional dict of variables to pass to workflow
                      Example: {"username": "user@example.com", "product": "Widget"}
        
        Returns:
            Execution results with steps_executed, success status, and any errors
        
        Example:
            gui_cub_execute_workflow(
                name="complete_purchase",
                variables={"username": "test@example.com", "product_id": "12345"}
            )
        """
        return await execute_workflow(context, name, variables)
