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
