"""Pytest configuration for integration tests.

Integration tests require specific environment variables to be set to prevent
hanging issues with Rich's Live() display in pexpect PTY environments.
"""

import os

import pytest

# Required environment variables for integration tests
REQUIRED_ENV_VARS = {
    "CI": "Disables Rich Live() display in streaming handler",
    "CODE_PUPPY_TEST_FAST": "Puts CLI in fast/lean mode for testing",
}


def _check_integration_env_vars() -> tuple[bool, list[tuple[str, str]]]:
    """Check if required environment variables are set.

    Returns:
        Tuple of (all_set, missing_vars) where missing_vars is a list of
        (var_name, description) tuples.
    """
    missing_vars = []
    for var, description in REQUIRED_ENV_VARS.items():
        value = os.environ.get(var, "").lower()
        if value not in ("1", "true", "yes"):
            missing_vars.append((var, description))
    return len(missing_vars) == 0, missing_vars


def _format_skip_reason(missing_vars: list[tuple[str, str]]) -> str:
    """Format a skip reason message for missing env vars."""
    var_list = ", ".join(var for var, _ in missing_vars)
    return (
        f"Integration tests require env vars: {var_list}. "
        f"Run with: CI=1 CODE_PUPPY_TEST_FAST=1 uv run pytest tests/integration/"
    )


# Check once at module load time
_ENV_VARS_OK, _MISSING_VARS = _check_integration_env_vars()
_SKIP_REASON = _format_skip_reason(_MISSING_VARS) if _MISSING_VARS else ""


@pytest.fixture(autouse=True, scope="function")
def _require_integration_env_vars():
    """Skip integration tests if required environment variables are not set.

    This fixture runs automatically for every test in the integration directory.
    It gracefully skips tests instead of bombing the entire test suite.
    """
    if not _ENV_VARS_OK:
        pytest.skip(_SKIP_REASON)
