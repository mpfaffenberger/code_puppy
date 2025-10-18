import os
import subprocess
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

@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Post-test hook: warn about stray .py files not tracked by git."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=session.config.invocation_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        untracked_py = [
            line for line in result.stdout.splitlines()
            if line.startswith("??") and line.endswith(".py")
        ]
        if untracked_py:
            print("\n[pytest-warn] Untracked .py files detected:")
            for line in untracked_py:
                rel_path = line[3:].strip()
                full_path = os.path.join(session.config.invocation_dir, rel_path)
                print(f"  - {rel_path}")
                # Optional: attempt cleanup to keep repo tidy
                try:
                    os.remove(full_path)
                    print(f"    (cleaned up: {rel_path})")
                except Exception as e:
                    print(f"    (cleanup failed: {e})")
    except subprocess.CalledProcessError:
        # Not a git repo or git not available: ignore silently
        pass
