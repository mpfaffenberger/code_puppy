"""Ralph Loop Controller - Manages the autonomous iteration loop.

This is the "outer loop" that spawns fresh agent instances per iteration,
just like the original ralph.sh bash script does.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from .state_manager import get_state_manager

logger = logging.getLogger(__name__)


class RalphLoopController:
    """Controls the Ralph autonomous loop.

    Each iteration:
    1. Checks if there's work to do
    2. Invokes the ralph-orchestrator agent with a FRESH session
    3. Waits for completion
    4. Checks if all stories are done or if we should continue
    """

    def __init__(self, max_iterations: int = 10):
        self.max_iterations = max_iterations
        self.current_iteration = 0
        self.is_complete = False
        self.is_running = False
        self._stop_requested = False

    def request_stop(self) -> None:
        """Request the loop to stop after current iteration."""
        self._stop_requested = True
        emit_warning("🛑 Stop requested - will halt after current iteration")

    async def run(
        self,
        invoke_func: Callable[[str, str, Optional[str]], Awaitable[dict]],
    ) -> dict:
        """Run the Ralph loop until completion or max iterations.

        Args:
            invoke_func: Async function to invoke an agent.
                        Signature: (agent_name, prompt, session_id) -> result_dict
                        The result_dict should have 'response' and 'error' keys.

        Returns:
            dict with 'success', 'iterations', 'message' keys
        """
        self.is_running = True
        self.is_complete = False
        self._stop_requested = False

        manager = get_state_manager()

        # Pre-flight checks
        if not manager.prd_exists():
            self.is_running = False
            return {
                "success": False,
                "iterations": 0,
                "message": "No prd.json found. Create one with /ralph prd first.",
            }

        if manager.all_stories_complete():
            self.is_running = False
            return {
                "success": True,
                "iterations": 0,
                "message": "All stories already complete!",
            }

        prd = manager.read_prd()
        emit_info("🐺 Starting Ralph Loop")
        emit_info(f"📋 Project: {prd.project if prd else 'Unknown'}")
        emit_info(f"📊 Progress: {prd.get_progress_summary() if prd else 'Unknown'}")
        emit_info(f"🔄 Max iterations: {self.max_iterations}")
        emit_info("─" * 50)

        try:
            for iteration in range(1, self.max_iterations + 1):
                self.current_iteration = iteration

                # Check for stop request
                if self._stop_requested:
                    emit_warning(f"🛑 Stopped at iteration {iteration}")
                    break

                # Check if already complete
                if manager.all_stories_complete():
                    self.is_complete = True
                    emit_success("🎉 All stories complete!")
                    break

                # Get current story for logging
                story = manager.get_next_story()
                if story is None:
                    self.is_complete = True
                    emit_success("🎉 All stories complete!")
                    break

                emit_info(f"\n{'=' * 60}")
                emit_info(f"🐺 RALPH ITERATION {iteration} of {self.max_iterations}")
                emit_info(f"📌 Working on: [{story.id}] {story.title}")
                emit_info(f"{'=' * 60}\n")

                # Build the prompt for this iteration
                iteration_prompt = self._build_iteration_prompt(story)

                # Invoke orchestrator with FRESH session (unique per iteration)
                session_id = f"ralph-iter-{iteration}"

                try:
                    result = await invoke_func(
                        "ralph-orchestrator",
                        iteration_prompt,
                        session_id,
                    )

                    response = result.get("response", "")
                    error = result.get("error")

                    if error:
                        emit_error(f"Iteration {iteration} error: {error}")
                        # Continue to next iteration despite error
                        continue

                    # Check for completion signal in response
                    if response and "<promise>COMPLETE</promise>" in response:
                        self.is_complete = True
                        emit_success("🎉 Ralph signaled COMPLETE - all stories done!")
                        break

                except asyncio.CancelledError:
                    emit_warning(f"🛑 Iteration {iteration} cancelled")
                    break
                except Exception as e:
                    emit_error(f"Iteration {iteration} failed: {e}")
                    logger.exception(f"Ralph iteration {iteration} failed")
                    # Continue to next iteration
                    continue

                # Brief pause between iterations
                await asyncio.sleep(1)

            else:
                # Loop completed without break (max iterations reached)
                emit_warning(f"⚠️ Reached max iterations ({self.max_iterations})")

        finally:
            self.is_running = False

        # Final status
        prd = manager.read_prd()
        final_progress = prd.get_progress_summary() if prd else "Unknown"

        return {
            "success": self.is_complete,
            "iterations": self.current_iteration,
            "message": f"Completed {self.current_iteration} iterations. {final_progress}",
            "all_complete": self.is_complete,
        }

    def _build_iteration_prompt(self, story) -> str:
        """Build the prompt for a single iteration."""
        # Find VERIFY criteria
        verify_criteria = [
            c for c in story.acceptance_criteria if c.startswith("VERIFY:")
        ]
        other_criteria = [
            c for c in story.acceptance_criteria if not c.startswith("VERIFY:")
        ]

        verify_section = ""
        if verify_criteria:
            verify_section = f"""
## MANDATORY VERIFICATION COMMANDS
You MUST run these commands and they MUST succeed before marking complete:
{chr(10).join(f"  {c}" for c in verify_criteria)}

If ANY verification fails, fix the code and re-run until it passes!
"""

        return f"""Execute ONE iteration of the Ralph loop.

## Current Story
- **ID:** {story.id}
- **Title:** {story.title}
- **Description:** {story.description}

## Acceptance Criteria (implement ALL of these):
{chr(10).join(f"  - {c}" for c in other_criteria)}
{verify_section}
## Requires UI Verification: {story.has_ui_verification()}
{"If yes, invoke qa-kitten to verify UI changes work correctly." if story.has_ui_verification() else ""}

## Your Task

1. Call `ralph_read_patterns()` to get context from previous iterations
2. Implement this ONE story completely
3. **RUN ALL VERIFY COMMANDS** - they must pass!
4. If checks pass, commit with: `git commit -m "feat: {story.id} - {story.title}"`
5. Call `ralph_mark_story_complete("{story.id}", "Verified: <what you tested>")`
6. Call `ralph_log_progress(...)` with what you learned
7. Call `ralph_check_all_complete()` to see if we're done

If ALL stories are complete, output: <promise>COMPLETE</promise>

⚠️ DO NOT mark complete until verification passes! Actually run the VERIFY commands!
"""


# Global controller instance
_controller: Optional[RalphLoopController] = None


def get_loop_controller(max_iterations: int = 10) -> RalphLoopController:
    """Get or create the loop controller."""
    global _controller
    if _controller is None or not _controller.is_running:
        _controller = RalphLoopController(max_iterations)
    return _controller


async def run_ralph_loop(
    max_iterations: int = 10,
    invoke_func: Optional[Callable] = None,
) -> dict:
    """Convenience function to run the Ralph loop.

    Args:
        max_iterations: Maximum number of iterations
        invoke_func: Function to invoke agents. If None, uses default.

    Returns:
        Result dict from the controller
    """
    if invoke_func is None:
        # Use the default agent invocation mechanism
        invoke_func = _default_invoke_agent

    controller = get_loop_controller(max_iterations)
    return await controller.run(invoke_func)


async def _default_invoke_agent(
    agent_name: str,
    prompt: str,
    session_id: Optional[str] = None,
) -> dict:
    """Default agent invocation using code_puppy's agent system."""
    try:
        from code_puppy.agents import get_current_agent, load_agent, set_current_agent

        # Save current agent to restore later
        original_agent = get_current_agent()

        try:
            # Load the target agent
            target_agent = load_agent(agent_name)
            if target_agent is None:
                return {"response": None, "error": f"Agent '{agent_name}' not found"}

            # Run the agent with the prompt
            # Note: This creates a fresh run with no message history
            result = await target_agent.run_with_mcp(prompt)

            # Extract response text
            response_text = ""
            if result is not None:
                if hasattr(result, "data"):
                    response_text = str(result.data) if result.data else ""
                else:
                    response_text = str(result)

            return {"response": response_text, "error": None}

        finally:
            # Restore original agent
            if original_agent:
                set_current_agent(original_agent.name)

    except Exception as e:
        logger.exception(f"Failed to invoke agent {agent_name}")
        return {"response": None, "error": str(e)}
