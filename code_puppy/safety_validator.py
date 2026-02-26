"""Safety validation for shell commands before execution."""

import logging
import os
from typing import Optional

from pydantic import BaseModel

from code_puppy.http_utils import create_client
from code_puppy.plugins.walmart_specific.urls import (
    Environment,
    get_safety_validation_url,
)

logger = logging.getLogger(__name__)

# Risk level hierarchy (lower index = less risky)
RISK_LEVELS = ["safe", "low", "medium", "high", "critical"]


class SafetyValidationResponse(BaseModel):
    """Response from the safety validation endpoint."""

    is_dangerous: bool
    risk_level: str  # e.g., "safe", "low", "medium", "high", "critical"
    reasoning: str


class SafetyValidationResult(BaseModel):
    """Result of safety validation check."""

    is_safe: bool
    risk_level: str
    reasoning: str
    error: Optional[str] = None
    should_block: bool = (
        False  # Whether command should be blocked based on permission level
    )


def get_environment_from_config() -> Environment:
    """Get the environment from config or default to STAGE."""
    # Check environment variable first
    env_str = os.environ.get("CODE_PUPPY_ENV", "stg").lower()

    if env_str in ["dev", "development"]:
        return Environment.DEV
    elif env_str in ["stg", "stage", "staging"]:
        return Environment.STAGE
    elif env_str in ["prod", "production"]:
        return Environment.PROD

    # Default to stage
    return Environment.STAGE


def should_block_command(command_risk_level: str, permission_level: str) -> bool:
    """Determine if a command should be blocked based on risk and permission levels.

    Args:
        command_risk_level: The risk level returned from the API (safe, low, medium, high, critical)
        permission_level: The user's permission level setting (safe, low, medium, high, critical)

    Returns:
        bool: True if command should be blocked, False if allowed

    Examples:
        >>> should_block_command("high", "medium")  # Block: high risk > medium permission
        True
        >>> should_block_command("low", "medium")  # Allow: low risk <= medium permission
        False
        >>> should_block_command("medium", "medium")  # Allow: equal levels
        False
    """
    try:
        command_risk_idx = RISK_LEVELS.index(command_risk_level.lower())
        permission_idx = RISK_LEVELS.index(permission_level.lower())

        # Block if command risk is HIGHER than permission level
        return command_risk_idx > permission_idx
    except (ValueError, AttributeError):
        # If unknown risk level, default to blocking for safety
        logger.warning(
            f"Unknown risk/permission level: {command_risk_level}/{permission_level}"
        )
        return True


def validate_command_safety(
    command: str, context: Optional[str] = None, timeout: int = 30
) -> SafetyValidationResult:
    """Validate if a shell command is safe to execute.

    Args:
        command: The shell command to validate
        context: Optional context about what the command is doing
        timeout: Request timeout in seconds

    Returns:
        SafetyValidationResult with validation results
    """
    if not command or not command.strip():
        return SafetyValidationResult(
            is_safe=False,
            risk_level="unknown",
            reasoning="Empty command",
            error="Command is empty",
            should_block=True,
        )

    try:
        environment = get_environment_from_config()
        url = get_safety_validation_url(environment)

        payload = {"command": command.strip(), "context": context or ""}

        logger.debug(f"Validating command safety: {command}")

        # Get puppy token for authentication
        from code_puppy.config import get_puppy_token

        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": get_puppy_token(),
        }

        # Use the properly configured HTTP session from http_utils
        client = create_client(verify=False)
        response = client.post(url, json=payload, headers=headers, timeout=timeout)

        # If token expired mid-session, try re-auth once and retry
        if response.status_code == 401:
            try:
                from code_puppy.plugins.walmart_specific.auth import (
                    reauthenticate_puppy_sync,
                )

                if reauthenticate_puppy_sync(reason="puppy backend returned 401"):
                    headers["X-Api-Key"] = get_puppy_token()
                    response = client.post(
                        url, json=payload, headers=headers, timeout=timeout
                    )
            except Exception:
                # Fail open: safety validation should not brick the CLI.
                pass

        if response.status_code == 200:
            data = response.json()
            validation = SafetyValidationResponse(**data)

            # Get user's permission level and check if we should block
            from code_puppy.config import get_safety_permission_level

            permission_level = get_safety_permission_level()
            block = should_block_command(validation.risk_level, permission_level)

            return SafetyValidationResult(
                is_safe=not validation.is_dangerous,
                risk_level=validation.risk_level,
                reasoning=validation.reasoning,
                should_block=block,
            )
        else:
            logger.warning(
                f"Safety validation returned status {response.status_code}: {response.text}"
            )
            # On error, allow the command but log it
            return SafetyValidationResult(
                is_safe=True,
                risk_level="unknown",
                reasoning="Safety validation service unavailable",
                error=f"Service returned status {response.status_code}",
                should_block=False,  # Fail open
            )

    except Exception as e:
        # Check if it's a timeout error
        if "timeout" in str(e).lower() or "timed out" in str(e).lower():
            logger.warning(f"Safety validation timeout for command: {command}")
            return SafetyValidationResult(
                is_safe=True,
                risk_level="unknown",
                reasoning="Safety validation timed out",
                error="Timeout",
                should_block=False,  # Fail open
            )
        logger.error(f"Error during safety validation: {e}")
        # On error, allow the command but log it (fail open)
        return SafetyValidationResult(
            is_safe=True,
            risk_level="unknown",
            reasoning="Safety validation failed",
            error=str(e),
            should_block=False,  # Fail open
        )
