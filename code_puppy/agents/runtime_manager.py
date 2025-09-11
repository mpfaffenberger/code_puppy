"""
Runtime agent manager that ensures proper agent instance updates.

This module provides a wrapper around the agent singleton that ensures
all references to the agent are properly updated when it's reloaded.
"""

import asyncio
import signal
import sys
import uuid
from typing import Any, Optional

# ExceptionGroup is available in Python 3.11+
if sys.version_info >= (3, 11):
    from builtins import ExceptionGroup
else:
    # For Python 3.10 and below, we can define a simple fallback
    class ExceptionGroup(Exception):
        def __init__(self, message, exceptions):
            super().__init__(message)
            self.exceptions = exceptions


import mcp
from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from code_puppy.messaging.message_queue import emit_info


class RuntimeAgentManager:
    """
    Manages the runtime agent instance and ensures proper updates.

    This class acts as a proxy that always returns the current agent instance,
    ensuring that when the agent is reloaded, all code using this manager
    automatically gets the updated instance.
    """

    def __init__(self):
        """Initialize the runtime agent manager."""
        self._agent: Optional[Agent] = None
        self._last_model_name: Optional[str] = None

    def get_agent(self, force_reload: bool = False, message_group: str = "") -> Agent:
        """
        Get the current agent instance.

        This method always returns the most recent agent instance,
        automatically handling reloads when the model changes.

        Args:
            force_reload: If True, force a reload of the agent

        Returns:
            The current agent instance
        """
        from code_puppy.agent import get_code_generation_agent

        # Always get the current singleton - this ensures we have the latest
        current_agent = get_code_generation_agent(
            force_reload=force_reload, message_group=message_group
        )
        self._agent = current_agent

        return self._agent

    def reload_agent(self) -> Agent:
        """
        Force reload the agent.

        This is typically called after MCP servers are started/stopped.

        Returns:
            The newly loaded agent instance
        """
        message_group = uuid.uuid4()
        emit_info(
            "[bold cyan]Reloading agent with updated configuration...[/bold cyan]",
            message_group=message_group,
        )
        return self.get_agent(force_reload=True, message_group=message_group)

    async def run_with_mcp(
        self, prompt: str, usage_limits: Optional[UsageLimits] = None, **kwargs
    ) -> Any:
        """
        Run the agent with MCP servers and full cancellation support.

        This method ensures we're always using the current agent instance
        and handles Ctrl+C interruption properly by creating a cancellable task.

        Args:
            prompt: The user prompt to process
            usage_limits: Optional usage limits for the agent
            **kwargs: Additional arguments to pass to agent.run (e.g., message_history)

        Returns:
            The agent's response

        Raises:
            asyncio.CancelledError: When execution is cancelled by user
        """
        agent = self.get_agent()
        group_id = str(uuid.uuid4())

        # Function to run agent with MCP
        async def run_agent_task():
            try:
                async with agent:
                    return await agent.run(prompt, usage_limits=usage_limits, **kwargs)
            except* UsageLimitExceeded as ule:
                emit_info(f"Usage limit exceeded: {str(ule)}", group_id=group_id)
                emit_info(
                    "The agent has reached its usage limit. You can ask it to continue by saying 'please continue' or similar.",
                    group_id=group_id,
                )
            except* mcp.shared.exceptions.McpError as mcp_error:
                emit_info(f"MCP server error: {str(mcp_error)}", group_id=group_id)
                emit_info(f"{str(mcp_error)}", group_id=group_id)
                emit_info(
                    "Try disabling any malfunctioning MCP servers", group_id=group_id
                )
            except* asyncio.exceptions.CancelledError:
                emit_info("Cancelled")
            except* InterruptedError as ie:
                emit_info(f"Interrupted: {str(ie)}")
            except* Exception as other_error:
                # Filter out CancelledError and UsageLimitExceeded from the exception group - let it propagate
                remaining_exceptions = []

                def collect_non_cancelled_exceptions(exc):
                    if isinstance(exc, ExceptionGroup):
                        for sub_exc in exc.exceptions:
                            collect_non_cancelled_exceptions(sub_exc)
                    elif not isinstance(
                        exc, (asyncio.CancelledError, UsageLimitExceeded)
                    ):
                        remaining_exceptions.append(exc)
                        emit_info(f"Unexpected error: {str(exc)}", group_id=group_id)
                        emit_info(f"{str(exc.args)}", group_id=group_id)

                collect_non_cancelled_exceptions(other_error)

                # If there are CancelledError exceptions in the group, re-raise them
                cancelled_exceptions = []

                def collect_cancelled_exceptions(exc):
                    if isinstance(exc, ExceptionGroup):
                        for sub_exc in exc.exceptions:
                            collect_cancelled_exceptions(sub_exc)
                    elif isinstance(exc, asyncio.CancelledError):
                        cancelled_exceptions.append(exc)

                collect_cancelled_exceptions(other_error)

                if cancelled_exceptions:
                    # Re-raise the first CancelledError to propagate cancellation
                    raise cancelled_exceptions[0]

        # Create the task FIRST
        agent_task = asyncio.create_task(run_agent_task())

        # Import shell process killer
        from code_puppy.tools.command_runner import kill_all_running_shell_processes

        # Ensure the interrupt handler only acts once per task
        def keyboard_interrupt_handler(sig, frame):
            """Signal handler for Ctrl+C - replicating exact original logic"""

            # First, nuke any running shell processes triggered by tools
            try:
                killed = kill_all_running_shell_processes()
                if killed:
                    emit_info(f"Cancelled {killed} running shell process(es).")
                else:
                    # Only cancel the agent task if no shell processes were killed
                    if not agent_task.done():
                        agent_task.cancel()
            except Exception as e:
                emit_info(f"Shell kill error: {e}")
                # If shell kill failed, still try to cancel the agent task
                if not agent_task.done():
                    agent_task.cancel()
            # Don't call the original handler
            # This prevents the application from exiting

        try:
            # Save original handler and set our custom one AFTER task is created
            original_handler = signal.signal(signal.SIGINT, keyboard_interrupt_handler)

            # Wait for the task to complete or be cancelled
            result = await agent_task
            return result
        except asyncio.CancelledError:
            # Task was cancelled by our handler
            raise
        except KeyboardInterrupt:
            # Handle direct keyboard interrupt during await
            if not agent_task.done():
                agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass
            raise asyncio.CancelledError()
        finally:
            # Restore original signal handler
            if original_handler:
                signal.signal(signal.SIGINT, original_handler)

    async def run(
        self, prompt: str, usage_limits: Optional[UsageLimits] = None, **kwargs
    ) -> Any:
        """
        Run the agent without explicitly managing MCP servers.

        Args:
            prompt: The user prompt to process
            usage_limits: Optional usage limits for the agent
            **kwargs: Additional arguments to pass to agent.run (e.g., message_history)

        Returns:
            The agent's response
        """
        agent = self.get_agent()
        try:
            return await agent.run(prompt, usage_limits=usage_limits, **kwargs)
        except UsageLimitExceeded as ule:
            group_id = str(uuid.uuid4())
            emit_info(f"Usage limit exceeded: {str(ule)}", group_id=group_id)
            emit_info(
                "The agent has reached its usage limit. You can ask it to continue by saying 'please continue' or similar.",
                group_id=group_id,
            )
            # Return None or some default value to indicate the limit was reached
            return None

    def __getattr__(self, name: str) -> Any:
        """
        Proxy all other attribute access to the current agent.

        This allows the manager to be used as a drop-in replacement
        for direct agent access.

        Args:
            name: The attribute name to access

        Returns:
            The attribute from the current agent
        """
        agent = self.get_agent()
        return getattr(agent, name)


# Global singleton instance
_runtime_manager: Optional[RuntimeAgentManager] = None


def get_runtime_agent_manager() -> RuntimeAgentManager:
    """
    Get the global runtime agent manager instance.

    Returns:
        The singleton RuntimeAgentManager instance
    """
    global _runtime_manager
    if _runtime_manager is None:
        _runtime_manager = RuntimeAgentManager()
    return _runtime_manager
