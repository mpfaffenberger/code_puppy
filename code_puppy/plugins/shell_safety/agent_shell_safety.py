"""Shell command safety assessment agent.

This agent provides rapid risk assessment of shell commands before execution.
It's designed to be ultra-lightweight with a concise prompt (<200 tokens) and
uses structured output for reliable parsing.
"""

import asyncio
from typing import TYPE_CHECKING, List

from code_puppy.agents.base_agent import BaseAgent

if TYPE_CHECKING:
    from code_puppy.tools.command_runner import ShellSafetyAssessment


class ShellSafetyAgent(BaseAgent):
    """Lightweight agent for assessing shell command safety risks.

    This agent evaluates shell commands for potential risks including:
    - File system destruction (rm -rf, dd, format, mkfs)
    - Database operations (DROP, TRUNCATE, unfiltered UPDATE/DELETE)
    - Privilege escalation (sudo, su, chmod 777)
    - Network operations (wget/curl to unknown hosts)
    - Data exfiltration patterns

    The agent returns structured output with a risk level and brief reasoning.
    """

    @property
    def name(self) -> str:
        """Agent name for internal use."""
        return "shell_safety_checker"

    @property
    def display_name(self) -> str:
        """User-facing display name."""
        return "Shell Safety Checker 🛡️"

    @property
    def description(self) -> str:
        """Agent description."""
        return "Lightweight agent that assesses shell command safety risks"

    def get_system_prompt(self) -> str:
        """Get the ultra-concise system prompt for shell safety assessment.

        This prompt is kept under 200 tokens for fast inference and low cost.
        """
        return """You are a shell command safety analyzer. Assess risk levels concisely.

**Risk Levels:**
- none: Completely safe (ls, pwd, echo, cat readonly files)
- low: Minimal risk (mkdir, touch, git status, read-only queries)
- medium: Moderate risk (file edits, package installs, service restarts)
- high: Significant risk (rm files, UPDATE/DELETE without WHERE, TRUNCATE, chmod dangerous permissions)
- critical: Severe/destructive (rm -rf, DROP TABLE/DATABASE, dd, format, mkfs, bq delete dataset, unfiltered mass deletes)

**Evaluate:**
- Scope (single file vs. entire system)
- Reversibility (can it be undone?)
- Data loss potential
- Privilege requirements
- Database destruction patterns

**Output:** Risk level + reasoning (max 1 sentence)."""

    def get_available_tools(self) -> List[str]:
        """This agent uses no tools - pure reasoning only."""
        return []

    async def assess_command(
        self, command: str, cwd: str | None = None
    ) -> "ShellSafetyAssessment":
        """Assess the safety risk of a shell command.

        Args:
            command: The shell command to assess
            cwd: Optional working directory context

        Returns:
            ShellSafetyAssessment with risk level and reasoning

        Note:
            On timeout or error, defaults to 'high' risk with error reasoning
            to fail safe. Optionally uses DBOS for durable execution tracking.
        """
        import uuid

        from pydantic_ai import Agent, UsageLimits

        from code_puppy.config import get_use_dbos
        from code_puppy.model_factory import ModelFactory
        from code_puppy.tools.command_runner import ShellSafetyAssessment

        try:
            # Build the assessment prompt
            prompt = f"Assess this shell command:\n\nCommand: {command}"
            if cwd:
                prompt += f"\nWorking directory: {cwd}"

            # Get the current model
            model_name = self.get_model_name()
            models_config = ModelFactory.load_config()

            if model_name not in models_config:
                # Fall back to high risk if model config fails
                return ShellSafetyAssessment(
                    risk="high",
                    reasoning="Model configuration unavailable - failing safe",
                )

            model = ModelFactory.get_model(model_name, models_config)

            # Handle claude-code models specially (like in agent_tools.py)
            instructions = self.get_system_prompt()
            if model_name.startswith("claude-code"):
                # For claude-code models, prepend system prompt to user prompt
                prompt = instructions + "\n\n" + prompt
                instructions = (
                    "You are Claude Code, Anthropic's official CLI for Claude."
                )

            # Build model settings with temperature if configured AND model supports it
            from pydantic_ai.settings import ModelSettings

            from code_puppy.config import get_temperature, model_supports_setting

            model_settings_dict = {}
            configured_temperature = get_temperature()
            if configured_temperature is not None and model_supports_setting(
                model_name, "temperature"
            ):
                model_settings_dict["temperature"] = configured_temperature

            model_settings = (
                ModelSettings(**model_settings_dict) if model_settings_dict else None
            )

            temp_agent = Agent(
                model=model,
                system_prompt=instructions,
                retries=1,
                output_type=ShellSafetyAssessment,
                model_settings=model_settings,
            )

            # Generate unique agent name and workflow ID for DBOS (if enabled)
            agent_name = f"shell-safety-{uuid.uuid4().hex[:8]}"
            workflow_id = f"shell-safety-{uuid.uuid4().hex[:8]}"

            # Wrap with DBOS if enabled (same pattern as agent_tools.py)
            if get_use_dbos():
                from pydantic_ai.durable_exec.dbos import DBOSAgent

                dbos_agent = DBOSAgent(temp_agent, name=agent_name)
                temp_agent = dbos_agent

            # Run the agent as a cancellable task
            # Import the shared task registry for cancellation support
            from code_puppy.tools.agent_tools import _active_subagent_tasks

            if get_use_dbos():
                from dbos import DBOS, SetWorkflowID

                with SetWorkflowID(workflow_id):
                    task = asyncio.create_task(
                        temp_agent.run(
                            prompt,
                            usage_limits=UsageLimits(request_limit=1),
                        )
                    )
                    _active_subagent_tasks.add(task)
            else:
                task = asyncio.create_task(
                    temp_agent.run(
                        prompt,
                        usage_limits=UsageLimits(request_limit=1),
                    )
                )
                _active_subagent_tasks.add(task)

            try:
                result = await task
            finally:
                _active_subagent_tasks.discard(task)
                if task.cancelled():
                    if get_use_dbos():
                        DBOS.cancel_workflow(workflow_id)

            # Return the structured output
            # The result.output should be a ShellSafetyAssessment due to the generic type
            output = result.output

            # If it's a string, try to parse it as JSON into ShellSafetyAssessment
            if isinstance(output, str):
                import json

                try:
                    data = json.loads(output)
                    return ShellSafetyAssessment(**data)
                except Exception:
                    # If parsing fails, fail safe
                    return ShellSafetyAssessment(
                        risk="high",
                        reasoning=f"Could not parse assessment output: {output[:100]}",
                    )

            return output

        except Exception as e:
            return ShellSafetyAssessment(
                risk="high",
                reasoning=f"Safety assessment failed: {str(e)[:200]} - failing safe",
            )
