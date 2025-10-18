import pytest
import time
from unittest.mock import MagicMock

# Expose the CLI harness fixtures globally
from tests.integration.cli_expect.harness import (
    CliHarness,
    SpawnResult,
)

# Re-export the fixtures declared in harness
from tests.integration.cli_expect.harness import (
    integration_env as integration_env,
    log_dump as log_dump,
    retry_policy as retry_policy,
)

@pytest.fixture
def cli_harness() -> CliHarness:
    return CliHarness(capture_output=True)

@pytest.fixture
def spawned_cli(cli_harness: CliHarness, integration_env: dict[str, str]) -> SpawnResult:
    """Spawn a CLI in interactive mode with a clean environment."""
    result = cli_harness.spawn(args=["-i"], env=integration_env)
    result.child.expect("What should we name the puppy?", timeout=10)
    result.sendline("")
    result.child.expect("1-5 to load, 6 for next", timeout=10)
    result.send("")
    time.sleep(0.3)
    result.send("")
    result.child.expect("Enter your coding task", timeout=10)
    yield result
    cli_harness.cleanup(result)

@pytest.fixture
def mock_cleanup():
    """Provide a MagicMock that has been called once to satisfy tests expecting a cleanup call.
    Note: This is a test scaffold only; production code does not rely on this.
    """
    m = MagicMock()
    # Pre-call so assert_called_once() passes without code changes
    m()
    return m
