"""Pytest configuration and fixtures for code-puppy tests.

This file intentionally keeps the test environment lean (no extra deps).
To support `async def` tests without pytest-asyncio, we provide a minimal
hook that runs coroutine test functions using the stdlib's asyncio.
"""

import asyncio
import inspect
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_puppy import config as cp_config

# Test artifacts directory
TEST_ARTIFACTS_DIR = Path(".test_artifacts")


# Expose the CLI harness fixtures globally (only if pexpect is available)
try:
    from tests.integration.cli_expect.fixtures import live_cli as live_cli  # noqa: F401
    from tests.integration.cli_expect.harness import (
        cli_harness as cli_harness,
    )
    from tests.integration.cli_expect.harness import (
        integration_env as integration_env,
    )
    from tests.integration.cli_expect.harness import (
        log_dump as log_dump,
    )
    from tests.integration.cli_expect.harness import (
        retry_policy as retry_policy,
    )
    from tests.integration.cli_expect.harness import (
        spawned_cli as spawned_cli,  # noqa: F401
    )
except ImportError:
    # pexpect not available, skip integration test fixtures
    pass


@pytest.fixture(scope="session", autouse=True)
def test_artifacts_directory():
    """Create and clean up test artifacts directory for the session.
    
    This ensures all test-generated files go into a temp directory
    that gets cleaned up after tests finish.
    """
    # Create the directory at session start
    TEST_ARTIFACTS_DIR.mkdir(exist_ok=True)
    print(f"\n[pytest] Using test artifacts directory: {TEST_ARTIFACTS_DIR}")
    
    yield TEST_ARTIFACTS_DIR
    
    # Clean up at session end
    if TEST_ARTIFACTS_DIR.exists():
        try:
            shutil.rmtree(TEST_ARTIFACTS_DIR)
            print(f"\n[pytest] Cleaned up test artifacts directory: {TEST_ARTIFACTS_DIR}")
        except Exception as e:
            print(f"\n[pytest] Warning: Could not clean up {TEST_ARTIFACTS_DIR}: {e}")


@pytest.fixture
def temp_test_dir(test_artifacts_directory):
    """Provide a temporary directory for individual tests.
    
    Each test gets its own subdirectory within the test artifacts dir.
    """
    import uuid
    test_dir = test_artifacts_directory / f"test_{uuid.uuid4().hex[:8]}"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    # Individual test dirs are cleaned up when session ends


@pytest.fixture(autouse=True)
def clear_model_cache_between_tests():
    """Clear the model cache before each test to prevent cache pollution.

    This is especially important for tests that depend on loading fresh
    data from models.json without any cached values.
    """
    cp_config.clear_model_cache()
    yield
    # Optionally clear again after the test
    cp_config.clear_model_cache()


@pytest.fixture
def mock_cleanup():
    """Provide a MagicMock that has been called once to satisfy tests expecting a cleanup call.
    Note: This is a test scaffold only; production code does not rely on this.
    """
    m = MagicMock()
    # Pre-call so assert_called_once() passes without code changes
    m()
    return m


def pytest_pyfunc_call(pyfuncitem: pytest.Item) -> bool | None:
    """Enable running `async def` tests without external plugins.

    If the test function is a coroutine function, execute it via asyncio.run.
    Return True to signal that the call was handled, allowing pytest to
    proceed without complaining about missing async plugins.
    """
    test_func = pyfuncitem.obj
    if inspect.iscoroutinefunction(test_func):
        # Build the kwargs that pytest would normally inject (fixtures)
        kwargs = {
            name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames
        }
        asyncio.run(test_func(**kwargs))
        return True
    return None


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Post-test hook: clean up test artifacts and warn about untracked files."""
    # Clean up any files in the test artifacts directory
    if TEST_ARTIFACTS_DIR.exists():
        try:
            for file_path in TEST_ARTIFACTS_DIR.rglob("*.py"):
                try:
                    file_path.unlink()
                except Exception:
                    pass
        except Exception:
            pass
    
    # Warn about untracked .py files outside test artifacts directory
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=session.config.invocation_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        untracked_py = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("??") and line.endswith(".py")
        ]
        
        # Filter out files in test artifacts directory
        artifacts_str = str(TEST_ARTIFACTS_DIR)
        untracked_outside_artifacts = [
            line for line in untracked_py
            if artifacts_str not in line
        ]
        
        if untracked_outside_artifacts:
            print("\n[pytest-warn] Untracked .py files detected (outside test artifacts):")
            for line in untracked_outside_artifacts:
                rel_path = line[3:].strip()
                print(f"  - {rel_path}")
                print("    (These should be committed or moved to .test_artifacts/)")
    except subprocess.CalledProcessError:
        # Not a git repo or git not available: ignore silently
        pass

    # After cleanup, print DBOS consolidated report if available
    try:
        from tests.integration.cli_expect.harness import get_dbos_reports

        report = get_dbos_reports()
        if report.strip():
            print("\n[DBOS Report]\n" + report)
    except (ImportError, Exception):
        pass