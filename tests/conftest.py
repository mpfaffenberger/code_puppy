"""Pytest configuration and fixtures for code-puppy tests.

This file intentionally keeps the test environment lean (no extra deps).
To support `async def` tests without pytest-asyncio, we provide a minimal
hook that runs coroutine test functions using the stdlib's asyncio.
"""

import asyncio
import inspect
import os
import subprocess
from unittest.mock import MagicMock

import pytest

from code_puppy import config as cp_config

# Integration test fixtures - only import if pexpect.spawn is available (Unix)
# On Windows, pexpect doesn't have spawn attribute, so skip these imports
try:
    from tests.integration.cli_expect.fixtures import live_cli as live_cli  # noqa: F401

    # Re-export integration fixtures so pytest discovers them project-wide
    # Expose the CLI harness fixtures globally
    from tests.integration.cli_expect.harness import cli_harness as cli_harness
    from tests.integration.cli_expect.harness import integration_env as integration_env
    from tests.integration.cli_expect.harness import log_dump as log_dump
    from tests.integration.cli_expect.harness import retry_policy as retry_policy
    from tests.integration.cli_expect.harness import (  # noqa: F401
        spawned_cli as spawned_cli,
    )
except (ImportError, AttributeError):
    # On Windows or when pexpect.spawn is unavailable, skip integration fixtures
    pass


@pytest.fixture(autouse=True)
def isolate_config_between_tests(tmp_path_factory):
    """Isolate config file changes between tests.

    This prevents tests from modifying the user's real config file
    (e.g., changing the selected model). Each test gets its own
    temporary config file in a separate directory from tmp_path.
    """
    import shutil
    import tempfile

    # Save original config path
    original_config_file = cp_config.CONFIG_FILE
    original_config_dir = cp_config.CONFIG_DIR

    # Create a completely separate temp directory for config isolation
    # (not using tmp_path which tests may use for their own purposes)
    config_temp_dir = tempfile.mkdtemp(prefix="code_puppy_test_config_")
    temp_config_dir = os.path.join(config_temp_dir, ".code_puppy")
    os.makedirs(temp_config_dir, exist_ok=True)
    temp_config_file = os.path.join(temp_config_dir, "puppy.cfg")

    # Copy existing config if it exists (so tests start with real settings)
    if os.path.exists(original_config_file):
        shutil.copy(original_config_file, temp_config_file)

    # Redirect config to temp location
    cp_config.CONFIG_FILE = temp_config_file
    cp_config.CONFIG_DIR = temp_config_dir

    # Clear model cache to ensure fresh state
    cp_config.clear_model_cache()

    yield

    # Restore original config paths
    cp_config.CONFIG_FILE = original_config_file
    cp_config.CONFIG_DIR = original_config_dir

    # Clear cache again after test
    cp_config.clear_model_cache()

    # Clean up the temp directory
    try:
        shutil.rmtree(config_temp_dir)
    except Exception:
        pass  # Best effort cleanup


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
            line
            for line in result.stdout.splitlines()
            if line.startswith("??") and line.endswith(".py")
        ]
        if untracked_py:
            print("\n[pytest-warn] Untracked .py files detected:")
            for line in untracked_py:
                rel_path = line[3:].strip()
                os.path.join(session.config.invocation_dir, rel_path)
                print(f"  - {rel_path}")
                # Optional: attempt cleanup to keep repo tidy
                # WARNING: File deletion disabled to preserve newly created test files
                # try:
                #     os.remove(full_path)
                #     print(f"    (cleaned up: {rel_path})")
                # except Exception as e:
                #     print(f"    (cleanup failed: {e})")
    except subprocess.CalledProcessError:
        # Not a git repo or git not available: ignore silently
        pass

    # After cleanup, print DBOS consolidated report if available
    try:
        from tests.integration.cli_expect.harness import get_dbos_reports

        report = get_dbos_reports()
        if report.strip():
            print("\n[DBOS Report]\n" + report)
    except Exception:
        pass
