"""Pytest configuration for integration tests.

Integration tests require specific environment variables to be set to prevent
hanging issues with Rich's Live() display in pexpect PTY environments.
"""

import os
import sys

import pytest

# Required environment variables for integration tests
REQUIRED_ENV_VARS = {
    "CI": "Disables Rich Live() display in streaming handler",
    "CODE_PUPPY_TEST_FAST": "Puts CLI in fast/lean mode for testing",
}


def pytest_configure(config):
    """Check for required environment variables before running integration tests.

    This hook runs early in pytest startup and will abort the test run
    if the required environment variables are not set.
    """
    missing_vars = []

    for var, description in REQUIRED_ENV_VARS.items():
        value = os.environ.get(var, "").lower()
        if value not in ("1", "true", "yes"):
            missing_vars.append((var, description))

    if missing_vars:
        error_msg = [
            "",
            "=" * 70,
            "ERROR: Integration tests require specific environment variables!",
            "=" * 70,
            "",
            "The following environment variables must be set to '1' or 'true':",
            "",
        ]

        for var, description in missing_vars:
            error_msg.append(f"  • {var}")
            error_msg.append(f"    Purpose: {description}")
            error_msg.append("")

        error_msg.extend(
            [
                "To run integration tests, use:",
                "",
                "  CI=1 CODE_PUPPY_TEST_FAST=1 uv run pytest tests/integration/",
                "",
                "Or set these in your shell:",
                "",
                "  export CI=1",
                "  export CODE_PUPPY_TEST_FAST=1",
                "",
                "These variables prevent Rich's Live() display from hanging in",
                "pexpect PTY environments used by integration tests.",
                "=" * 70,
            ]
        )

        # Print error and exit
        print("\n".join(error_msg), file=sys.stderr)
        pytest.exit(
            "Missing required environment variables for integration tests", returncode=1
        )
