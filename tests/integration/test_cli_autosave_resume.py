"""Integration tests for autosave resume and session rotation."""

from __future__ import annotations

import os
import re
import shutil
import sys
import time

import pexpect
import pytest

from tests.integration.cli_expect.fixtures import CliHarness, satisfy_initial_prompts

IS_WINDOWS = os.name == "nt" or sys.platform.startswith("win")

pytestmark = pytest.mark.skipif(
    IS_WINDOWS,
    reason="Interactive CLI pexpect tests have platform-specific issues on Windows",
)


def test_autosave_resume_roundtrip(
    integration_env: dict[str, str],
) -> None:
    """Create an autosave, restart in the same HOME, and load it via the picker."""
    harness = CliHarness(capture_output=True)
    first_run = harness.spawn(args=["-i"], env=integration_env)
    try:
        satisfy_initial_prompts(first_run, skip_autosave=True)
        harness.wait_for_ready(first_run)

        first_run.sendline("/model Cerebras-Qwen3-Coder-480b\r")
        first_run.child.expect(r"Active model set", timeout=30)
        harness.wait_for_ready(first_run)

        prompt_text = "hi"
        first_run.sendline(f"{prompt_text}\r")
        first_run.child.expect(r"Auto-saved session", timeout=180)
        harness.wait_for_ready(first_run)

        first_run.sendline("/quit\r")
        first_run.child.expect(pexpect.EOF, timeout=20)
        first_run.close_log()

        second_run = harness.spawn(
            args=["-i"],
            env=integration_env,
            existing_home=first_run.temp_home,
        )
        try:
            # Wait for the CLI to be ready
            harness.wait_for_ready(second_run)

            # Manually trigger autosave loading
            second_run.sendline("/autosave_load\r")
            second_run.child.expect("Autosave Sessions Available", timeout=20)
            second_run.child.expect(re.compile(r"Pick .*name/Enter:"), timeout=20)
            time.sleep(0.2)
            second_run.send("1")
            time.sleep(0.3)
            second_run.send("\r")
            time.sleep(0.3)
            second_run.child.expect("Autosave loaded", timeout=60)
            harness.wait_for_ready(second_run)

            second_run.sendline("/model Cerebras-Qwen3-Coder-480b\r")
            time.sleep(0.2)
            second_run.child.expect(r"Active model set", timeout=30)
            harness.wait_for_ready(second_run)

            log_output = second_run.read_log().lower()
            assert "autosave loaded" in log_output

            second_run.sendline("/quit\r")
            second_run.child.expect(pexpect.EOF, timeout=20)
        finally:
            harness.cleanup(second_run)
    finally:
        if os.getenv("CODE_PUPPY_KEEP_TEMP_HOME") not in {"1", "true", "TRUE", "True"}:
            shutil.rmtree(first_run.temp_home, ignore_errors=True)
