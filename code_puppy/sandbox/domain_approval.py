"""
Domain approval flow for network isolation.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class DomainApprovalHandler:
    """Handles user approval for network domain access."""

    def __init__(self, approval_callback=None):
        """
        Initialize the domain approval handler.

        Args:
            approval_callback: Optional async function that prompts user for approval
                             Should accept (domain: str) -> bool
        """
        self.approval_callback = approval_callback
        self._pending_approvals = {}

    async def request_approval(self, domain: str) -> bool:
        """
        Request user approval for a domain.

        Args:
            domain: The domain to request approval for

        Returns:
            True if approved, False otherwise
        """
        # Check if there's already a pending approval for this domain
        if domain in self._pending_approvals:
            return await self._pending_approvals[domain]

        # Create a future for this approval request
        future = asyncio.Future()
        self._pending_approvals[domain] = future

        try:
            # Use the callback if provided
            if self.approval_callback:
                approved = await self.approval_callback(domain)
            else:
                # Default to denying if no callback
                approved = False

            future.set_result(approved)
            return approved

        except Exception as e:
            logger.error(f"Error requesting domain approval: {e}")
            future.set_result(False)
            return False

        finally:
            # Clean up
            self._pending_approvals.pop(domain, None)


def create_cli_approval_callback(console):
    """
    Create an approval callback that uses the CLI console for prompts.

    Args:
        console: The console object to use for prompts

    Returns:
        Async callback function
    """

    async def approval_callback(domain: str) -> bool:
        """Prompt user for domain approval via CLI."""
        try:
            from code_puppy.messaging.queue_console import QueueConsole

            if isinstance(console, QueueConsole):
                # Use the queue console for prompts
                prompt_text = (
                    f"\n[bold yellow]Network Access Request[/bold yellow]\n\n"
                    f"A sandboxed command wants to access: [bold]{domain}[/bold]\n\n"
                    f"Allow this domain? (y/n): "
                )

                # This is a simplified version - in reality we'd need to integrate
                # with the existing prompt system
                response = await asyncio.to_thread(
                    input,
                    prompt_text,
                )

                return response.lower().strip() in ("y", "yes")

        except Exception as e:
            logger.error(f"Error in domain approval callback: {e}")
            return False

        return False

    return approval_callback
