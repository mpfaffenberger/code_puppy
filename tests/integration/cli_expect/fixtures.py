"""Shared fixtures and helpers for CLI integration tests."""

from __future__ import annotations

import os
import time
from typing import Generator

import pexpect
import pytest

from .harness import (
    CliHarness,
    SpawnResult,
    integration_env,
    log_dump,
    retry_policy,
    spawned_cli,
)

__all__ = [
    "CliHarness",
    "SpawnResult",
    "integration_env",
    "log_dump",
    "retry_policy",
    "spawned_cli",
    "live_cli",
    "satisfy_initial_prompts",
    "skip_autosave_picker",
]


@pytest.fixture
def live_cli(cli_harness: CliHarness) -> Generator[SpawnResult, None, None]:
    """Spawn the CLI using the caller's environment (for live network tests)."""
    env = os.environ.copy()
    env.setdefault("CODE_PUPPY_TEST_FAST", "1")
    result = cli_harness.spawn(args=["-i"], env=env)
    try:
        yield result
    finally:
        cli_harness.cleanup(result)


def satisfy_initial_prompts(result: SpawnResult, skip_autosave: bool = True) -> None:
    """Complete the puppy name and owner prompts if they appear; otherwise continue."""
    try:
        result.child.expect("What should we name the puppy?", timeout=3)
        result.sendline("IntegrationPup\r")
        result.child.expect("What's your name", timeout=3)
        result.sendline("HarnessTester\r")
    except pexpect.exceptions.TIMEOUT:
        # Config likely pre-provisioned; proceed
        pass

    skip_autosave_picker(result, skip=skip_autosave)


def skip_autosave_picker(result: SpawnResult, *, skip: bool = True) -> None:
    """Skip the autosave picker if it appears."""
    if not skip:
        return

    try:
        result.child.expect("1-5 to load, 6 for next", timeout=5)
        result.send("\r")
        time.sleep(0.3)
        result.send("\r")
    except pexpect.exceptions.TIMEOUT:
        pass
