"""
Retry handler for dangerouslyDisableSandbox functionality.

When a sandboxed command fails, this module handles retrying it
without sandboxing after getting user approval.
"""

import logging

logger = logging.getLogger(__name__)


class SandboxRetryHandler:
    """Handles retry logic for failed sandboxed commands."""

    def __init__(self, config):
        """
        Initialize retry handler.

        Args:
            config: SandboxConfig instance
        """
        self.config = config

    def should_retry_unsandboxed(self, command: str, exit_code: int) -> bool:
        """
        Determine if a failed command should be retried unsandboxed.

        Args:
            command: The command that failed
            exit_code: The exit code from the failed command

        Returns:
            True if retry is allowed and failure looks sandbox-related
        """
        # Only retry if unsandboxed commands are allowed
        if not self.config.allow_unsandboxed_commands:
            logger.debug("Unsandboxed retry disabled by configuration")
            return False

        # Check if this is likely a sandbox-related failure
        # Common sandbox failure codes:
        # - 1: General error (could be sandbox-related)
        # - 126: Permission denied
        # - 127: Command not found (could be sandboxing blocking path)
        # - 139: Segmentation fault (can happen with sandbox misconfig)
        sandbox_related_codes = {1, 126, 127, 139}

        if exit_code in sandbox_related_codes:
            logger.info(
                f"Command failed with exit code {exit_code}, "
                f"which may be sandbox-related"
            )
            return True

        return False

    async def request_unsandboxed_retry(
        self,
        command: str,
        approval_callback=None,
    ) -> bool:
        """
        Request user approval to retry command without sandboxing.

        Args:
            command: The command to retry
            approval_callback: Optional async callback to ask user

        Returns:
            True if user approves retry
        """
        if approval_callback:
            try:
                approved = await approval_callback(command)
                if approved:
                    logger.info(f"User approved unsandboxed retry for: {command}")
                else:
                    logger.info(f"User rejected unsandboxed retry for: {command}")
                return approved
            except Exception as e:
                logger.error(f"Error in approval callback: {e}")
                return False

        # No callback provided, default to deny
        logger.warning("No approval callback provided, denying unsandboxed retry")
        return False


def create_retry_approval_callback(console):
    """
    Create an approval callback for unsandboxed retry using the console.

    Args:
        console: Console object for displaying prompts

    Returns:
        Async callback function
    """

    async def approval_callback(command: str) -> bool:
        """Prompt user for unsandboxed retry approval."""
        try:
            import asyncio

            from code_puppy.messaging.queue_console import QueueConsole

            if isinstance(console, QueueConsole):
                prompt_text = (
                    f"\n[bold red]⚠️  Sandbox Failure Detected[/bold red]\n\n"
                    f"The command failed when running in the sandbox:\n"
                    f"[yellow]{command}[/yellow]\n\n"
                    f"This may be due to sandbox restrictions. "
                    f"Retry without sandboxing?\n\n"
                    f"[dim red]WARNING: Running unsandboxed removes filesystem "
                    f"and network protections.[/dim red]\n\n"
                    f"Retry unsandboxed? (y/n): "
                )

                response = await asyncio.to_thread(
                    input,
                    prompt_text,
                )

                return response.lower().strip() in ("y", "yes")

        except Exception as e:
            logger.error(f"Error in retry approval callback: {e}")
            return False

        return False

    return approval_callback
