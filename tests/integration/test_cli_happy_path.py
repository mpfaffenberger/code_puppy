"""Happy-path interactive CLI test covering core commands."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pexpect

from tests.integration.cli_expect.fixtures import (
    CliHarness,
    SpawnResult,
    satisfy_initial_prompts,
)


def _assert_contains(log_output: str, needle: str) -> None:
    assert needle in log_output, f"Expected '{needle}' in log output"


def test_cli_happy_path_interactive_flow(
    cli_harness: CliHarness,
    live_cli: SpawnResult,
) -> None:
    """Drive /help, /model, /set, a prompt, and verify autosave contents."""
    result = live_cli
    satisfy_initial_prompts(result)
    cli_harness.wait_for_ready(result)

    result.sendline("/help\r")
    result.child.expect(r"Commands Help", timeout=10)
    cli_harness.wait_for_ready(result)

    result.sendline("/model Cerebras-Qwen3-Coder-480b\r")
    result.child.expect(r"Active model set and loaded", timeout=10)
    cli_harness.wait_for_ready(result)

    result.sendline("/set owner_name FlowTester\r")
    result.child.expect(r"Set owner_name", timeout=10)
    cli_harness.wait_for_ready(result)

    prompt_text = "Explain the benefits of unit testing in Python"
    result.sendline(f"{prompt_text}\r")
    result.child.expect(r"Auto-saved session", timeout=120)
    cli_harness.wait_for_ready(result)
    time.sleep(10)

    log_output = result.read_log()
    _assert_contains(log_output, "FlowTester")
    assert "python" in log_output.lower() or "function" in log_output.lower()
    assert "unit testing" in log_output.lower()

    autosave_dir = Path(result.temp_home) / ".code_puppy" / "autosaves"
    meta_files: list[Path] = []
    for _ in range(20):
        meta_files = list(autosave_dir.glob("*_meta.json"))
        if meta_files:
            break
        time.sleep(0.5)
    assert meta_files, "Expected at least one autosave metadata file"

    most_recent_meta = max(meta_files, key=lambda path: path.stat().st_mtime)
    with most_recent_meta.open("r", encoding="utf-8") as meta_file:
        metadata = json.load(meta_file)
    assert metadata.get("auto_saved") is True
    assert metadata.get("message_count", 0) > 0

    result.sendline("/quit\r")
    result.child.expect(pexpect.EOF, timeout=20)
