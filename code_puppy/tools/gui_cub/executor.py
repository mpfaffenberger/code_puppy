"""GUI-Cub workflow executor - Execute YAML workflows with chaining support."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List

import yaml
from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id
from code_puppy.tools.gui_cub.workflows import (
    parse_workflow_parameters,
    validate_workflow_parameters,
)


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails."""

    pass


class WorkflowExecutionResult(BaseModel):
    """Structured result from workflow execution."""

    workflow: str = Field(..., description="Workflow name")
    status: str = Field(..., description="success, failure, or partial")
    execution_time: float = Field(..., description="Total execution time in seconds")
    parameters_used: Dict[str, Any] = Field(
        default_factory=dict, description="Parameters passed to workflow"
    )
    outputs: Dict[str, Any] = Field(
        default_factory=dict, description="Extracted output data"
    )
    steps_executed: int = Field(
        default=0, description="Number of steps successfully executed"
    )
    steps_skipped: int = Field(
        default=0, description="Number of steps skipped (conditional)"
    )
    errors: List[str] = Field(default_factory=list, description="Error messages if any")
    screenshots: List[str] = Field(
        default_factory=list, description="Paths to screenshots taken"
    )


class WorkflowExecutor:
    """Execute YAML workflows with variable interpolation and chaining.

    ARCHITECTURE NOTE - Tool Naming Convention:
    ==========================================
    This executor calls GUI-Cub desktop automation tools which follow a specific
    naming pattern:

    - Agent Tools (registered via @agent.tool): Use `desktop_*` prefix
      Examples: desktop_keyboard_type, desktop_mouse_click, desktop_find_text
      These are callable by the AI agent and wrapped with @desktop_tool decorator.

    - Executor Methods (internal): Use `_execute_*` prefix
      Examples: _execute_type, _execute_click, _execute_hotkey
      These are internal workflow step handlers that call the desktop_* tools.

    WHY: The desktop_* functions are designed as agent tools with rich logging,
    error handling, and user-facing output. The executor reuses these tools
    directly rather than duplicating logic.

    ASYNC/SYNC PATTERN:
    ===================
    - Executor methods are async (support await for other async operations)
    - Desktop tool functions are sync (wrapped with @desktop_tool decorator)
    - Executor calls sync tools directly without await (correct pattern)
    - Some executor methods await other async functions (focus_window, ui_click_element)

    This mixed pattern is intentional and correct - async executor methods can
    call both sync tools (direct call) and async tools (with await).
    """

    def __init__(self, context: RunContext):
        self.context = context
        self.variables: Dict[str, Any] = {}
        self.outputs: Dict[str, Any] = {}  # Collected output variables
        self.screenshots: List[str] = []  # Screenshot paths
        self.steps_executed: int = 0
        self.steps_skipped: int = 0
        self.errors: List[str] = []
        self.workflow_dir = Path.home() / ".code_puppy" / "gui_cub_workflows"

    def interpolate_variables(self, value: Any) -> Any:
        """Replace {{variable}} and ${variable} placeholders with actual values.

        Supports:
        - {{var_name}} or ${var_name} - from variables dict
        - {{env.VAR_NAME}} or ${env.VAR_NAME} - from environment variables
        - {{step.output}} or ${step.output} - from previous step outputs
        """
        if not isinstance(value, str):
            return value

        # Replace {{env.VAR}} and ${env.VAR} with environment variables
        def replace_env_double_brace(match):
            env_var = match.group(1)
            placeholder = "{{env." + env_var + "}}"
            return os.environ.get(env_var, placeholder)  # Keep placeholder if not found

        def replace_env_dollar(match):
            env_var = match.group(1)
            placeholder = "${env." + env_var + "}"
            return os.environ.get(env_var, placeholder)  # Keep placeholder if not found

        value = re.sub(r"{{env\.([^}]+)}}", replace_env_double_brace, value)
        value = re.sub(r"\$\{env\.([^}]+)\}", replace_env_dollar, value)

        # Replace {{variable}} and ${variable} with values from self.variables
        def replace_var_double_brace(match):
            var_name = match.group(1)
            if var_name in self.variables:
                return str(self.variables[var_name])
            # Check outputs as well
            if var_name in self.outputs:
                return str(self.outputs[var_name])
            return "{{" + var_name + "}}"  # Keep placeholder if not found

        def replace_var_dollar(match):
            var_name = match.group(1)
            if var_name in self.variables:
                return str(self.variables[var_name])
            # Check outputs as well
            if var_name in self.outputs:
                return str(self.outputs[var_name])
            return "${" + var_name + "}"  # Keep placeholder if not found

        value = re.sub(r"{{([^}]+)}}", replace_var_double_brace, value)
        value = re.sub(r"\$\{([^}]+)\}", replace_var_dollar, value)
        return value

    def should_execute_step(self, step: Dict[str, Any]) -> bool:
        """Evaluate whether a step should be executed based on its condition.

        Supports basic boolean expressions:
        - ${var} == value
        - ${var} != value
        - ${var} (truthy check)

        Args:
            step: The workflow step with potential 'condition' field

        Returns:
            True if step should execute, False to skip
        """
        if "condition" not in step:
            return True

        condition = step["condition"]

        # Interpolate variables in condition
        condition = self.interpolate_variables(condition)

        # Simple boolean evaluation
        # Support: "true", "false", "var == value", "var != value"
        condition = condition.strip()

        # Handle direct boolean strings
        if condition.lower() == "true":
            return True
        if condition.lower() == "false":
            return False

        # Handle == comparisons
        if " == " in condition:
            left, right = condition.split(" == ", 1)
            left = left.strip()
            right = right.strip()

            # Handle boolean comparisons
            if right.lower() == "true":
                return left.lower() == "true"
            if right.lower() == "false":
                return left.lower() == "false"

            return left == right

        # Handle != comparisons
        if " != " in condition:
            left, right = condition.split(" != ", 1)
            left = left.strip()
            right = right.strip()

            # Handle boolean comparisons
            if right.lower() == "true":
                return left.lower() != "true"
            if right.lower() == "false":
                return left.lower() != "false"

            return left != right

        # Default: treat as truthy check
        return bool(condition)

    async def execute_action(self, action: Dict[str, Any], step_index: int) -> Any:
        """Execute a single workflow action.

        Supported actions:
        - focus_window: Focus a window by app name
        - click: Click element using accessibility API (basic)
        - smart_click: Multi-strategy click (UIA → OCR → VQA)
        - ocr_click: Click using OCR text recognition
        - ui_click: Click using UI automation with automation_id/name
        - mouse_click: Click at specific coordinates
        - type: Type text using keyboard
        - press: Press a single key
        - hotkey: Press keyboard shortcut combination
        - sleep: Wait for specified duration
        - run_workflow: Execute another workflow (chaining)
        - verify: Verify text appears on screen
        - screenshot: Take screenshot + auto-analyze with OCR/VQA (default: OCR)
        - extract_text: Extract text from screen region using OCR
        - manual_step: Pause for user intervention (input/confirmation)

        Screenshot behavior:
        - Default: Captures screenshot and analyzes with OCR (extracts all text)
        - VQA mode: Set analyze_method='vqa' with question parameter
        - Save to file: Set save_to_file=true to skip analysis (saves to CWD)
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
            elif action_type == "smart_click":
                return await self._execute_smart_click(interpolated_action)
            elif action_type == "ocr_click":
                return await self._execute_ocr_click(interpolated_action)
            elif action_type == "ui_click":
                return await self._execute_ui_click(interpolated_action)
            elif action_type == "mouse_click":
                return await self._execute_mouse_click(interpolated_action)
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
            elif action_type == "screenshot":
                result = await self._execute_screenshot(interpolated_action)
                # Store screenshot path in outputs if output_variable specified
                if "output_variable" in action:
                    var_name = action["output_variable"]
                    if result.get("success") and "screenshot_path" in result:
                        self.outputs[var_name] = result["screenshot_path"]
                        self.screenshots.append(result["screenshot_path"])
                return result
            elif action_type == "extract_text":
                return await self._execute_extract_text(interpolated_action)
            elif action_type == "manual_step":
                return await self._execute_manual_step(interpolated_action)
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
        """Focus a window by app name.

        Calls focus_window (sync function) directly without await.
        """
        from code_puppy.tools.gui_cub.window_control import focus_window

        app_name = action.get("app") or action.get("window")
        if not app_name:
            raise WorkflowExecutionError("focus_window requires 'app' parameter")

        result = focus_window(app_name)
        return {
            "success": result.success if hasattr(result, "success") else result,
            "app": app_name,
        }

    async def _execute_click(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Click an element using accessibility API.

        Calls ui_click_element (sync tool) directly without await.
        """
        from code_puppy.tools.gui_cub.os_unified import ui_click_element

        element = action.get("element", {})
        if not element:
            raise WorkflowExecutionError("click requires 'element' parameter")

        title = element.get("title")
        fuzzy = element.get("fuzzy", True)

        result = ui_click_element(self.context, title=title, fuzzy=fuzzy)
        return result

    async def _execute_type(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Type text using keyboard.

        Calls desktop_keyboard_type (sync tool) directly without await.
        """
        from code_puppy.tools.gui_cub.keyboard_control import desktop_keyboard_type

        text = action.get("text")
        if text is None:
            raise WorkflowExecutionError("type requires 'text' parameter")

        desktop_keyboard_type(self.context, text)
        return {"success": True, "text": text}

    async def _execute_press(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Press a key.

        Calls desktop_keyboard_press (sync tool) directly without await.
        """
        from code_puppy.tools.gui_cub.keyboard_control import desktop_keyboard_press

        key = action.get("key")
        if not key:
            raise WorkflowExecutionError("press requires 'key' parameter")

        desktop_keyboard_press(self.context, key)
        return {"success": True, "key": key}

    async def _execute_hotkey(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Press a keyboard shortcut.

        Calls desktop_keyboard_hotkey (sync tool) directly without await.
        """
        from code_puppy.tools.gui_cub.keyboard_control import desktop_keyboard_hotkey

        keys = action.get("keys")
        if not keys:
            raise WorkflowExecutionError("hotkey requires 'keys' parameter")

        if isinstance(keys, str):
            keys = [keys]

        desktop_keyboard_hotkey(self.context, *keys)
        return {"success": True, "keys": keys}

    async def _execute_sleep(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Sleep for specified duration."""
        import asyncio

        duration = action.get("duration") or action.get("seconds")
        if duration is None:
            raise WorkflowExecutionError(
                "sleep requires 'duration' or 'seconds' parameter"
            )

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

    async def _execute_smart_click(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Click using multi-strategy approach (UIA → OCR → VQA).

        Calls desktop_click_element_smart (sync tool) directly without await.
        """
        from code_puppy.tools.gui_cub.multi_strategy_click import (
            desktop_click_element_smart,
        )

        text = action.get("text") or action.get("label")
        if not text:
            raise WorkflowExecutionError(
                "smart_click requires 'text' or 'label' parameter"
            )

        result = desktop_click_element_smart(self.context, text=text)
        return result

    async def _execute_ocr_click(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Click using OCR text recognition.

        Uses desktop_find_text (async) then desktop_mouse_click (sync).
        """
        from code_puppy.tools.gui_cub.ocr_tools import desktop_find_text
        from code_puppy.tools.gui_cub.mouse_control import desktop_mouse_click

        text = action.get("text") or action.get("label")
        if not text:
            raise WorkflowExecutionError(
                "ocr_click requires 'text' or 'label' parameter"
            )

        # Find text using OCR
        find_result = desktop_find_text(
            self.context, search_text=text, use_active_window=True
        )

        if not find_result.get("found"):
            raise WorkflowExecutionError(f"OCR could not find text: {text}")

        # Get first match and click
        matches = find_result.get("matches", [])
        if matches:
            match = matches[0]
            x, y = match.get("center_x"), match.get("center_y")
            desktop_mouse_click(self.context, x=x, y=y)
            return {"success": True, "text": text, "x": x, "y": y}

        raise WorkflowExecutionError(f"No OCR matches for: {text}")

    async def _execute_ui_click(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Click using UI automation with automation_id or name.

        Calls ui_click_element (sync tool) directly without await.
        """
        from code_puppy.tools.gui_cub.os_unified import ui_click_element

        # Support multiple parameter names
        automation_id = action.get("automation_id") or action.get("auto_id")
        name = action.get("name") or action.get("title")
        control_type = action.get("control_type") or action.get("type")
        fuzzy = action.get("fuzzy", True)

        if not (automation_id or name):
            raise WorkflowExecutionError(
                "ui_click requires 'automation_id' or 'name' parameter"
            )

        result = ui_click_element(
            self.context,
            auto_id=automation_id,
            title=name,
            control_type=control_type,
            fuzzy=fuzzy,
        )
        return result

    async def _execute_mouse_click(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Click at specific coordinates.

        Calls desktop_mouse_click (sync tool) directly without await.
        """
        from code_puppy.tools.gui_cub.mouse_control import desktop_mouse_click

        x = action.get("x")
        y = action.get("y")

        if x is None or y is None:
            raise WorkflowExecutionError("mouse_click requires 'x' and 'y' parameters")

        desktop_mouse_click(self.context, x=int(x), y=int(y))
        return {"success": True, "x": x, "y": y}

    async def _execute_screenshot(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Take a screenshot and automatically analyze it with OCR or VQA.

        **REFACTORED to use unified screenshot() and screenshot_analyze() functions.**

        **DEFAULT BEHAVIOR:** Automatically analyzes screenshot with OCR to extract text.
        This helps with debugging and verification by showing what's actually on screen.

        **SAVE TO FILE MODE:** Set save_to_file=true to skip analysis and only save image.
        Saved screenshots go to the current working directory, not temp.

        Supported parameters:
        - save_to_file: false (default) | true - Skip analysis, save to CWD
        - analyze_method: "ocr" (default) | "vqa" - How to analyze (if save_to_file=false)
        - question: Required if analyze_method="vqa"
        - save_path: Custom path for saved screenshots (relative to CWD)
        - use_active_window: true (default) | false
        - x: Optional left coordinate for region capture
        - y: Optional top coordinate for region capture
        - width: Optional width for region capture
        - height: Optional height for region capture
        - output_variable: Store analysis results in this variable

        Examples:
            # Default: Capture + OCR analysis (automatic debugging)
            - action: screenshot

            # Save screenshot to file in CWD (user-requested only)
            - action: screenshot
              save_to_file: true
              save_path: "debug_screenshot.png"

            # VQA analysis with question
            - action: screenshot
              analyze_method: vqa
              question: "Where is the Submit button?"
        """
        import os
        from code_puppy.tools.gui_cub.screen_capture import (
            screenshot,
            screenshot_analyze,
        )

        # Extract common parameters
        x = action.get("x")
        y = action.get("y")
        width = action.get("width")
        height = action.get("height")
        use_active_window = action.get("use_active_window", True)
        mode = "active_window" if use_active_window else "full_screen"

        # Check if user wants to save screenshot to file (no analysis)
        # Support both new name (save_to_file) and old name (pure_screenshot) for backward compatibility
        save_to_file = action.get("save_to_file", action.get("pure_screenshot", False))

        if save_to_file:
            # SAVE TO FILE MODE: Use unified screenshot() with custom save path
            save_path = action.get("save_path")
            if not save_path:
                # Generate filename in CWD
                import datetime

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                cwd = os.getcwd()
                save_path = os.path.join(cwd, f"screenshot_{timestamp}.png")
            else:
                # User specified custom path (relative to CWD)
                save_path = os.path.abspath(save_path)

            # Use unified screenshot() function
            screenshot_result = screenshot(
                x=x,
                y=y,
                width=width,
                height=height,
                mode=mode,
                save_path=save_path,
            )

            emit_info(f"📸 Screenshot saved to: {screenshot_result.screenshot_path}")

            return {
                "success": screenshot_result.success,
                "screenshot_path": screenshot_result.screenshot_path,
                "analysis_method": "none",
                "save_to_file": True,
            }

        # ANALYSIS MODE (default): Use unified screenshot_analyze()
        analyze_method = action.get("analyze_method", "ocr").lower()
        question = action.get("question") if analyze_method == "vqa" else None

        # Validate VQA requires question
        if analyze_method == "vqa" and not question:
            raise WorkflowExecutionError(
                "screenshot with analyze_method='vqa' requires 'question' parameter"
            )

        # Use unified screenshot_analyze() function
        result = await screenshot_analyze(
            question=question,
            x=x,
            y=y,
            width=width,
            height=height,
            mode=mode,
        )

        # Log analysis results
        if result.get("analysis_type") == "ocr":
            emit_info(
                f"📸 Screenshot analyzed with OCR: {result.get('word_count', 0)} words extracted"
            )
        elif result.get("analysis_type") == "vqa":
            emit_info(
                f"📸 Screenshot analyzed with VQA: {result.get('answer', '')[:100]}"
            )

        # Store in output variable if specified
        if "output_variable" in action:
            var_name = action["output_variable"]
            if result.get("analysis_type") == "ocr":
                self.outputs[var_name] = {
                    "text": result.get("full_text", ""),
                    "screenshot": result.get("screenshot_path"),
                }
            elif result.get("analysis_type") == "vqa":
                self.outputs[var_name] = {
                    "answer": result.get("answer", ""),
                    "confidence": result.get("confidence", 0.0),
                    "observations": result.get("observations", ""),
                    "screenshot": result.get("screenshot_path"),
                }

        return result

    async def _execute_extract_text(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Extract text from a screen region using OCR.

        Supports output_variable to store extracted text.
        """
        from code_puppy.tools.gui_cub.ocr_tools import desktop_extract_text

        # Get region parameters
        region = action.get("region", {})
        x = region.get("x")
        y = region.get("y")
        width = region.get("width")
        height = region.get("height")

        # Extract text
        result = desktop_extract_text(
            self.context,
            use_active_window=action.get("use_active_window", True),
            use_full_screen=action.get("use_full_screen", False),
            x=x,
            y=y,
            width=width,
            height=height,
        )

        # Store in outputs if output_variable specified
        if "output_variable" in action:
            var_name = action["output_variable"]
            extracted_text = result.get("full_text", "")
            self.outputs[var_name] = extracted_text

        return result

    async def _execute_manual_step(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Pause workflow for manual user intervention.

        User performs the action manually in the application (type password,
        solve CAPTCHA, make a decision, etc.) then clicks Continue to resume.
        """
        import pyautogui

        message = action.get("message") or action.get("instruction")

        if not message:
            message = "Please complete the manual action and click Continue..."

        emit_info(f"\n{'=' * 60}")
        emit_info("⏸️  MANUAL STEP REQUIRED")
        emit_info(f"{'=' * 60}")
        emit_info(f"📝 {message}")
        emit_info("")
        emit_info("🎯 Do the action in the application, then click Continue below.")
        emit_info(f"{'=' * 60}\n")

        # Show dialog and wait for user to click Continue
        pyautogui.confirm(message, buttons=["Continue"])

        emit_info("✅ Manual step completed, continuing workflow...\n")
        return {"success": True, "action": "confirmed"}

    async def _execute_verify(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Verify expected text appears on screen.

        Calls desktop_extract_text (sync tool) directly without await.
        """
        from code_puppy.tools.gui_cub.ocr_tools import desktop_extract_text

        expected_text = action.get("expected_text") or action.get("text")
        if not expected_text:
            raise WorkflowExecutionError("verify requires 'expected_text' parameter")

        result = desktop_extract_text(self.context, use_active_window=True)
        full_text = result.get("full_text", "")
        found = expected_text.lower() in full_text.lower()

        if not found:
            raise WorkflowExecutionError(
                f"Verification failed: '{expected_text}' not found on screen"
            )

        return {"success": True, "verified": expected_text}

    async def execute_workflow_file(
        self, workflow_name: str, parameters: Dict[str, Any] | None = None
    ) -> WorkflowExecutionResult:
        """Load and execute a workflow from file.

        Args:
            workflow_name: Name of workflow file
            parameters: Runtime parameters to pass

        Returns:
            WorkflowExecutionResult with structured data
        """
        # Find workflow file - check both locations
        possible_paths = [
            # New location (from workflows.py)
            Path.home()
            / ".code_puppy"
            / "agents"
            / "gui_cub"
            / "workflows"
            / workflow_name,
            Path.home()
            / ".code_puppy"
            / "agents"
            / "gui_cub"
            / "workflows"
            / f"{workflow_name}.yaml",
            Path.home()
            / ".code_puppy"
            / "agents"
            / "gui_cub"
            / "workflows"
            / f"{workflow_name}.yml",
            # Legacy location
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

        return await self.execute_workflow(workflow_data, parameters)

    async def execute_workflow(
        self, workflow: Dict[str, Any], parameters: Dict[str, Any] | None = None
    ) -> WorkflowExecutionResult:
        """Execute a workflow from parsed YAML data.

        Args:
            workflow: Parsed workflow YAML
            parameters: Runtime parameters to pass to workflow

        Returns:
            WorkflowExecutionResult with structured execution data
        """
        start_time = time.time()
        workflow_name = workflow.get("name", "unnamed")

        # Parse and validate parameters
        param_defs = parse_workflow_parameters(workflow)
        if parameters:
            try:
                validated_params = validate_workflow_parameters(param_defs, parameters)
                self.variables.update(validated_params)
            except (ValueError, TypeError) as e:
                self.errors.append(str(e))
                return WorkflowExecutionResult(
                    workflow=workflow_name,
                    status="failure",
                    execution_time=time.time() - start_time,
                    parameters_used=parameters or {},
                    outputs=self.outputs,
                    steps_executed=self.steps_executed,
                    steps_skipped=self.steps_skipped,
                    errors=self.errors,
                    screenshots=self.screenshots,
                )

        # Extract workflow variables (legacy {{var}} support)
        if "variables" in workflow:
            workflow_vars = workflow["variables"]
            # Interpolate variable defaults
            for var_name, var_value in workflow_vars.items():
                if var_name not in self.variables:  # Don't override passed-in variables
                    self.variables[var_name] = self.interpolate_variables(var_value)

        # Execute steps
        steps = workflow.get("steps", [])
        if not steps:
            self.errors.append("Workflow has no steps")
            return WorkflowExecutionResult(
                workflow=workflow_name,
                status="failure",
                execution_time=time.time() - start_time,
                parameters_used=parameters or {},
                outputs=self.outputs,
                steps_executed=self.steps_executed,
                steps_skipped=self.steps_skipped,
                errors=self.errors,
                screenshots=self.screenshots,
            )

        for i, step in enumerate(steps):
            # Check if step should be executed (conditional logic)
            if not self.should_execute_step(step):
                emit_info(
                    f"⏭️  Skipping step {i + 1}/{len(steps)}: {step.get('action', 'unknown')} "
                    f"(condition not met)"
                )
                self.steps_skipped += 1
                continue

            emit_info(
                f"▶️  Executing step {i + 1}/{len(steps)}: {step.get('action', 'unknown')}"
            )

            try:
                await self.execute_action(step, i + 1)
                self.steps_executed += 1
            except Exception as e:
                error_msg = f"Step {i + 1} failed: {str(e)}"
                self.errors.append(error_msg)
                emit_error(error_msg)

                # Decide if we should continue or stop
                if step.get("continue_on_error", False):
                    continue
                else:
                    # Stop execution on error
                    break

        # Determine final status
        status = "success" if not self.errors else "failure"
        if self.errors and self.steps_executed > 0:
            status = "partial"

        execution_time = time.time() - start_time

        return WorkflowExecutionResult(
            workflow=workflow_name,
            status=status,
            execution_time=execution_time,
            parameters_used=parameters or {},
            outputs=self.outputs,
            steps_executed=self.steps_executed,
            steps_skipped=self.steps_skipped,
            errors=self.errors,
            screenshots=self.screenshots,
        )


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
