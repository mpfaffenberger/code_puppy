"""Integration tests for session rotation functionality."""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

import pexpect

from tests.integration.cli_expect.fixtures import CliHarness, satisfy_initial_prompts


def test_session_rotation(
    integration_env: dict[str, str],
) -> None:
    """Test that session IDs properly rotate when starting new sessions."""
    harness = CliHarness(capture_output=True)

    # Start first session
    first_run = harness.spawn(args=["-i"], env=integration_env)
    try:
        satisfy_initial_prompts(first_run, skip_autosave=True)
        harness.wait_for_ready(first_run)

        # Set model
        first_run.sendline("/model Cerebras-GLM-4.6\r")
        first_run.child.expect(r"Active model set", timeout=60)
        harness.wait_for_ready(first_run)

        # Send a prompt to create autosave
        prompt_text_1 = "Hello, this is session 1"
        first_run.sendline(f"{prompt_text_1}\r")
        first_run.child.expect(r"Auto\-saved session", timeout=240)  # Increased timeout
        harness.wait_for_ready(first_run)

        # End first session
        first_run.sendline("/quit\r")
        first_run.child.expect(pexpect.EOF, timeout=30)
        first_run.close_log()

        # Start second session with existing home
        second_run = harness.spawn(
            args=["-i"], env=integration_env, existing_home=first_run.temp_home
        )
        try:
            # Wait for the CLI to be ready
            harness.wait_for_ready(second_run)

            # Manually trigger autosave loading to see the picker
            second_run.sendline("/autosave_load\r")
            second_run.child.expect("Autosave Sessions Available", timeout=30)
            second_run.child.expect(re.compile(r"Pick .*name/Enter:"), timeout=30)

            # Create a new session instead of loading the existing one
            time.sleep(0.5)
            second_run.sendline("\r")  # Just send newline to create new session
            time.sleep(1.0)  # Increased sleep time

            # Verify we get a new session prompt (look for the specific text that indicates a new session)
            second_run.child.expect("Enter your coding task", timeout=60)

            # Verify we now have two session directories
            autosave_dir = Path(second_run.temp_home) / ".code_puppy" / "autosaves"
            session_dirs = list(autosave_dir.glob("*"))
            assert len(session_dirs) == 2, (
                f"Should have exactly two autosave sessions, found {len(session_dirs)}"
            )

            second_run.sendline("/quit\r")
            second_run.child.expect(pexpect.EOF, timeout=30)
        finally:
            harness.cleanup(second_run)
    finally:
        if os.getenv("CODE_PUPPY_KEEP_TEMP_HOME") not in {"1", "true", "TRUE", "True"}:
            shutil.rmtree(first_run.temp_home, ignore_errors=True)
