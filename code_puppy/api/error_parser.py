"""Error parsing utilities for API errors.

Provides human-readable error messages and actionable guidance for common API errors.
"""

import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


def parse_api_error(error: Exception) -> Dict[str, Any]:
    """Parse API errors into user-friendly messages with actionable guidance.

    Debugging: this function logs the chosen classification at DEBUG level
    to help trace WS error propagation to the UI.

    Args:
        error: The exception that was raised

    Returns:
        Dictionary with:
        - error_type: Category of error (quota_exceeded, rate_limit, auth_error, network_error, unknown)
        - user_message: Human-readable message for the user
        - technical_details: Technical error information
        - action_required: Specific action the user should take (optional)
        - original_error: String representation of the original error
    """
    error_str = str(error)
    error_type_name = type(error).__name__

    logger.debug(
        "parse_api_error: incoming type=%s msg=%r",
        error_type_name,
        error_str[:400],
    )

    # Check for quota exceeded errors (HTTP 429 or explicit quota messages)
    if _is_quota_exceeded_error(error_str):
        parsed = {
            "error_type": "quota_exceeded",
            "user_message": "Your API quota has been exceeded for the current model. Please switch to a different model and click continue to retry your request.",
            "technical_details": _extract_quota_details(error_str),
            "action_required": "switch_model",
            "original_error": error_str,
        }
        logger.debug("parse_api_error: classified as %s", parsed["error_type"])
        return parsed

    # Check for rate limit errors
    if _is_rate_limit_error(error_str):
        parsed = {
            "error_type": "rate_limit",
            "user_message": "You're making requests too quickly. Please wait a moment and try again, or switch to a different model.",
            "technical_details": error_str,
            "action_required": "wait_or_switch_model",
            "original_error": error_str,
        }
        logger.debug("parse_api_error: classified as %s", parsed["error_type"])
        return parsed

    # Check for authentication/permission errors
    if _is_auth_error(error_str):
        return {
            "error_type": "auth_error",
            "user_message": "Authentication failed. Please check your credentials or API key configuration.",
            "technical_details": error_str,
            "action_required": "check_credentials",
            "original_error": error_str,
        }

    # Check for network/timeout errors
    if _is_network_error(error_str, error_type_name):
        return {
            "error_type": "network_error",
            "user_message": "Network connection failed. Please check your internet connection and try again.",
            "technical_details": error_str,
            "action_required": "retry",
            "original_error": error_str,
        }

    # Check for model not found errors
    if _is_model_not_found_error(error_str):
        return {
            "error_type": "model_not_found",
            "user_message": "The requested model is not available. Please switch to a different model.",
            "technical_details": error_str,
            "action_required": "switch_model",
            "original_error": error_str,
        }

    # Check for Claude extended thinking temperature errors
    if _is_claude_temperature_thinking_error(error_str):
        parsed = {
            "error_type": "claude_temperature_error",
            "user_message": "Claude's extended thinking mode requires temperature to be set to 1.0. Please adjust your model settings or disable extended thinking.",
            "technical_details": error_str,
            "action_required": "adjust_temperature",
            "original_error": error_str,
        }
        logger.debug("parse_api_error: classified as %s", parsed["error_type"])
        return parsed

    # Generic error fallback
    parsed = {
        "error_type": "unknown",
        "user_message": f"An unexpected error occurred: {error_str}",
        "technical_details": error_str,
        "action_required": None,
        "original_error": error_str,
    }
    logger.debug("parse_api_error: classified as %s", parsed["error_type"])
    return parsed


def _is_quota_exceeded_error(error_str: str) -> bool:
    """Check if error is a quota exceeded error."""
    quota_patterns = [
        r"quota\s+exceeded",
        r"HTTP\s+429",
        r"aiplatform\.googleapis\.com/online_prediction_requests_per_base_model",
        r"resource_exhausted",
        r"too\s+many\s+requests.*quota",
    ]

    for pattern in quota_patterns:
        if re.search(pattern, error_str, re.IGNORECASE):
            return True
    return False


def _is_rate_limit_error(error_str: str) -> bool:
    """Check if error is a rate limit error."""
    rate_limit_patterns = [
        r"rate\s+limit",
        r"too\s+many\s+requests",
        r"throttle",
        r"requests.*per.*second",
        r"requests.*per.*minute",
    ]

    for pattern in rate_limit_patterns:
        if re.search(pattern, error_str, re.IGNORECASE):
            # Don't double-match quota errors
            if not _is_quota_exceeded_error(error_str):
                return True
    return False


def _is_auth_error(error_str: str) -> bool:
    """Check if error is an authentication error."""
    auth_patterns = [
        r"authentication\s+failed",
        r"unauthorized",
        r"HTTP\s+401",
        r"HTTP\s+403",
        r"permission\s+denied",
        r"invalid.*api.*key",
        r"invalid.*credentials",
        r"access\s+denied",
    ]

    for pattern in auth_patterns:
        if re.search(pattern, error_str, re.IGNORECASE):
            return True
    return False


def _is_network_error(error_str: str, error_type_name: str) -> bool:
    """Check if error is a network/connectivity error."""
    # Check error type names
    network_error_types = [
        "TimeoutError",
        "ConnectionError",
        "ConnectTimeout",
        "ReadTimeout",
        "HTTPError",
    ]

    if any(err_type in error_type_name for err_type in network_error_types):
        return True

    # Check error message patterns
    network_patterns = [
        r"timeout",
        r"connection\s+refused",
        r"connection\s+reset",
        r"connection\s+failed",
        r"network\s+error",
        r"unable\s+to\s+connect",
        r"host\s+unreachable",
    ]

    for pattern in network_patterns:
        if re.search(pattern, error_str, re.IGNORECASE):
            return True
    return False


def _is_model_not_found_error(error_str: str) -> bool:
    """Check if error is a model not found error."""
    # Use simple patterns that match anywhere in the string
    if re.search(r"model.*not\s+found", error_str, re.IGNORECASE):
        return True
    if re.search(r"invalid\s+model", error_str, re.IGNORECASE):
        return True
    if re.search(r"unknown\s+model", error_str, re.IGNORECASE):
        return True
    if re.search(r"model.*does\s+not\s+exist", error_str, re.IGNORECASE):
        return True
    if re.search(r"HTTP\s+404.*model", error_str, re.IGNORECASE):
        return True

    return False


def _is_claude_temperature_thinking_error(error_str: str) -> bool:
    """Check if error is Claude's temperature/thinking configuration error."""
    return (
        "temperature" in error_str.lower()
        and "thinking" in error_str.lower()
        and ("may only be set to 1" in error_str or "must be 1" in error_str)
    )


def _extract_quota_details(error_str: str) -> str:
    """Extract specific quota details from error message."""
    # Try to extract the specific quota metric if present
    match = re.search(r"quota\s+exceeded\s+for\s+([\w\./]+)", error_str, re.IGNORECASE)
    if match:
        return f"Quota exceeded for: {match.group(1)}"

    # Try to extract model name if present
    match = re.search(r"base\s+model[:\s]+([\w\-]+)", error_str, re.IGNORECASE)
    if match:
        return f"Quota exceeded for base model: {match.group(1)}"

    return error_str
