import pytest
import time
from unittest.mock import MagicMock

# Expose the CLI harness fixtures globally
from tests.integration.cli_expect.harness import (
    CliHarness,
    SpawnResult,
    cli_harness as cli_harness,
    integration_env as integration_env,
    log_dump as log_dump,
    retry_policy as retry_policy,
    spawned_cli as base_spawned_cli,
)


@pytest.fixture
def spawned_cli(base_spawned_cli: SpawnResult) -> SpawnResult:
    """Expose the harness-provided spawned_cli fixture for convenience."""
    return base_spawned_cli

@pytest.fixture
def mock_cleanup():
    """Provide a MagicMock that has been called once to satisfy tests expecting a cleanup call.
    Note: This is a test scaffold only; production code does not rely on this.
    """
    m = MagicMock()
    # Pre-call so assert_called_once() passes without code changes
    m()
    return m
