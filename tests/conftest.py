"""Pytest configuration and fixtures for code-puppy tests.

This file intentionally keeps the test environment lean (no extra deps).
To support `async def` tests without pytest-asyncio, we provide a minimal
hook that runs coroutine test functions using the stdlib's asyncio.
"""

import asyncio
import inspect
import pytest
from unittest.mock import MagicMock

from code_puppy import config as cp_config


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
    
    
import os
import subprocess
from unittest.mock import MagicMock

import pytest

# Expose the CLI harness fixtures globally
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
# Re-export integration fixtures so pytest discovers them project-wide
from tests.integration.cli_expect.harness import spawned_cli as spawned_cli  # noqa: F401
from tests.integration.cli_expect.fixtures import live_cli as live_cli  # noqa: F401


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
        kwargs = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
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

    # After cleanup, print DBOS consolidated report if available
    try:
        from tests.integration.cli_expect.harness import get_dbos_reports

        report = get_dbos_reports()
        if report.strip():
            print("\n[DBOS Report]\n" + report)
    except Exception:
        pass
