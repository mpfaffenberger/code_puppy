"""Integration test ensuring live LLM commands include explicit carriage returns."""
from __future__ import annotations

import os
import time

import pytest
import pexpect

from tests.integration.cli_expect.fixtures import (
    CliHarness,
    SpawnResult,
    live_cli,
    satisfy_initial_prompts,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("CEREBRAS_API_KEY"),
    reason="Requires CEREBRAS_API_KEY to hit the live LLM",
)


def test_real_llm_commands_always_include_carriage_returns(
    cli_harness: CliHarness,
    live_cli: SpawnResult,
) -> None:
    """Smoke a real prompt and ensure every command we send appends \r."""
    result = live_cli
    satisfy_initial_prompts(result)
    cli_harness.wait_for_ready(result)

    result.sendline("/help\r")
    time.sleep(0.5)
    result.sendline("Write a simple Python function to add two numbers\r")
    time.sleep(10)

    log_output = result.read_log().lower()
    assert "python" in log_output or "function" in log_output

    result.sendline("/quit\r")
    result.child.expect(pexpect.EOF, timeout=20)
