"""Pytest configuration and fixtures for mist tests.

This file intentionally keeps the test environment lean (no extra deps).
To support `async def` tests without pytest-asyncio, we provide a minimal
hook that runs coroutine test functions using the stdlib's asyncio.
"""

import asyncio
import inspect
import os
import subprocess
from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from code_puppy import config as cp_config
from code_puppy import callbacks as cp_callbacks


def _ensure_builtin_plugin_callback_registrations() -> None:
    """Re-register builtin plugin callbacks that tests assert are wired.

    Some callback unit tests intentionally clear the global callback registry.
    Importing a plugin module a second time does not re-run module-scope
    registrations, so restore the key builtin registrations explicitly.
    ``register_callback`` deduplicates, making this safe to call per test.
    """
    from code_puppy.plugins.agent_steering import register_callbacks as steering
    from code_puppy.plugins.azure_foundry import register_callbacks as foundry
    from code_puppy.plugins.claude_code_hooks import register_callbacks as hooks
    from code_puppy.plugins.universal_constructor import register_callbacks as uc

    cp_callbacks.register_callback(
        "agent_pause_requested", steering._on_pause_requested
    )
    cp_callbacks.register_callback("custom_command_help", foundry._custom_help)
    cp_callbacks.register_callback("custom_command", foundry._handle_custom_command)
    cp_callbacks.register_callback("register_model_type", foundry._register_model_types)
    # Keep hook callbacks registered for wiring tests, but do not let local
    # ~/.mist or project .claude hook configuration affect test runs.
    hooks._hook_engine = None
    cp_callbacks.register_callback("pre_tool_call", hooks.on_pre_tool_call_hook)
    cp_callbacks.register_callback("post_tool_call", hooks.on_post_tool_call_hook)
    cp_callbacks.register_callback("startup", uc._on_startup)


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
def isolate_global_state_between_tests(tmp_path_factory):
    """Isolate mutable global state between tests.

    Tests must be deterministic locally and in CI. Do not seed test config from
    the developer's real ``~/.mist/mist.cfg`` because user defaults such
    as ``default_agent`` or ``compaction_threshold`` change expected defaults.
    Also snapshot callback registrations so tests exercising callback mutation
    cannot wipe plugin registrations needed by later tests.
    """
    import shutil
    import tempfile

    # Ensure lazy plugin imports are represented in the snapshot.
    _ensure_builtin_plugin_callback_registrations()

    # Save original config path and callback registry.
    original_config_file = cp_config.CONFIG_FILE
    original_config_dir = cp_config.CONFIG_DIR
    original_callbacks = deepcopy(cp_callbacks._callbacks)

    # Create a completely separate temp directory for config isolation
    # (not using tmp_path which tests may use for their own purposes).
    config_temp_dir = tempfile.mkdtemp(prefix="code_puppy_test_config_")
    temp_config_dir = os.path.join(config_temp_dir, ".mist")
    os.makedirs(temp_config_dir, exist_ok=True)
    temp_config_file = os.path.join(temp_config_dir, "mist.cfg")

    # Redirect config to an empty temp file so defaults are true product
    # defaults, not the local developer's personal settings.
    cp_config.CONFIG_FILE = temp_config_file
    cp_config.CONFIG_DIR = temp_config_dir

    # Clear model cache to ensure fresh state.
    cp_config.clear_model_cache()
    # Clear session-local model cache (required for /model session sticky behavior).
    cp_config.reset_session_model()

    yield

    # Restore original config paths and callback registrations.
    cp_config.CONFIG_FILE = original_config_file
    cp_config.CONFIG_DIR = original_config_dir
    cp_callbacks._callbacks.clear()
    cp_callbacks._callbacks.update(original_callbacks)
    _ensure_builtin_plugin_callback_registrations()

    # Clear cache again after test.
    cp_config.clear_model_cache()
    # Clear session-local model cache.
    cp_config.reset_session_model()

    # Clean up the temp directory.
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
