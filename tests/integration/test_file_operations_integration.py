"""Integration test for file operation tools using conversational prompts.

This test drives the CLI through natural language prompts that should trigger
the file operation tools (list_files, read_file, edit_file, delete_file). It
verifies that the agent correctly chooses the right tools and that filesystem
changes match expectations.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from tests.integration.cli_expect.fixtures import (
    CliHarness,
    SpawnResult,
    satisfy_initial_prompts,
)

# Skip in CI environment due to flakiness with real LLM calls
pytestmark = pytest.mark.skipif(
    os.getenv("CI") == "true",
    reason="Integration test with real LLM calls is too flaky for CI environment",
)


def _assert_file_exists(test_dir: Path, relative_path: str) -> Path:
    """Assert a file exists relative to test_dir and return its full path."""
    full_path = test_dir / relative_path
    assert full_path.exists(), f"Expected file {relative_path} to exist at {full_path}"
    assert full_path.is_file(), f"Expected {relative_path} to be a file"
    return full_path


def _assert_file_not_exists(test_dir: Path, relative_path: str) -> None:
    """Assert a file does not exist relative to test_dir."""
    full_path = test_dir / relative_path
    assert not full_path.exists(), (
        f"Expected file {relative_path} to not exist at {full_path}"
    )


def _assert_file_contains(test_dir: Path, relative_path: str, content: str) -> None:
    """Assert a file contains specific content."""
    full_path = _assert_file_exists(test_dir, relative_path)
    file_content = full_path.read_text(encoding="utf-8")
    assert content in file_content, (
        f"Expected '{content}' in {relative_path}, but got: {file_content}"
    )


def test_file_operations_integration(
    cli_harness: CliHarness,
    live_cli: SpawnResult,
) -> None:
    """Test file operation tools through conversational prompts.

    This test drives the agent to use file tools by asking natural language
    questions that should trigger list_files, read_file, edit_file, and delete_file.
    """
    result = live_cli

    # Set up initial test files in a temporary directory
    test_dir = Path(tempfile.mkdtemp(prefix="test_files_"))
    (test_dir / "simple.txt").write_text("Simple test file.", encoding="utf-8")
    (test_dir / "hello.py").write_text("print('Hello from hello.py')", encoding="utf-8")
    (test_dir / "project").mkdir()
    (test_dir / "project" / "README.md").write_text(
        "# Test Project\n\nThis is a test project.", encoding="utf-8"
    )

    # Get to the interactive prompt
    satisfy_initial_prompts(result)
    cli_harness.wait_for_ready(result)

    # 1. Test list_files - ask to see what's in our test directory
    list_prompt = f"Use list_files to show me all files in {test_dir}"
    result.sendline(f"{list_prompt}\r")

    # Wait for auto-save to indicate completion
    result.child.expect(r"Auto-saved session", timeout=120)
    cli_harness.wait_for_ready(result)
    time.sleep(5)

    # Check that the agent used list_files and mentioned our test files
    log_output = result.read_log()
    assert "simple.txt" in log_output or "hello.py" in log_output, (
        f"Agent should have listed the test files. Log: {log_output}"
    )

    # 2. Test read_file - ask to read a specific file
    read_prompt = f"Use read_file to read the contents of {test_dir}/hello.py and tell me what it does"
    result.sendline(f"{read_prompt}\r")

    # Wait for auto-save to indicate completion
    result.child.expect(r"Auto-saved session", timeout=120)
    cli_harness.wait_for_ready(result)
    time.sleep(5)

    # Check that the agent read the file and described it
    log_output = result.read_log()
    assert "Hello from hello.py" in log_output, (
        f"Agent should have read hello.py content. Log: {log_output}"
    )

    # 3. Test edit_file - ask to modify a file
    edit_prompt = f"Use edit_file to add a new line to {test_dir}/simple.txt that says 'Updated by Code Puppy!'"
    result.sendline(f"{edit_prompt}\r")

    # Wait for auto-save to indicate completion
    result.child.expect(r"Auto-saved session", timeout=120)
    cli_harness.wait_for_ready(result)
    time.sleep(5)

    # Check that the file was actually modified
    _assert_file_contains(test_dir, "simple.txt", "Updated by Code Puppy!")

    # 4. Test another edit - modify the Python file
    py_edit_prompt = f"Use edit_file to add a function called greet to {test_dir}/hello.py that prints 'Welcome!'"
    result.sendline(f"{py_edit_prompt}\r")

    # Wait for auto-save to indicate completion
    result.child.expect(r"Auto-saved session", timeout=120)
    cli_harness.wait_for_ready(result)
    time.sleep(5)

    # Check that Python file was modified
    _assert_file_contains(test_dir, "hello.py", "def greet")
    _assert_file_contains(test_dir, "hello.py", "Welcome!")

    # 5. Test read_file on a different file - read the project README
    readme_read_prompt = (
        f"Use read_file to read {test_dir}/project/README.md and summarize it"
    )
    result.sendline(f"{readme_read_prompt}\r")

    # Wait for auto-save to indicate completion
    result.child.expect(r"Auto-saved session", timeout=120)
    cli_harness.wait_for_ready(result)
    time.sleep(5)

    # Check that the agent read the README
    log_output = result.read_log()
    assert "Test Project" in log_output, (
        f"Agent should have read the README. Log: {log_output}"
    )

    # 6. Test delete_file - ask to delete a file
    delete_prompt = f"Use delete_file to remove the {test_dir}/simple.txt file"
    result.sendline(f"{delete_prompt}\r")

    # Wait for auto-save to indicate completion
    result.child.expect(r"Auto-saved session", timeout=120)
    cli_harness.wait_for_ready(result)
    time.sleep(5)

    # Check that the file was actually deleted
    _assert_file_not_exists(test_dir, "simple.txt")

    # 7. Final verification - list files again to confirm changes
    final_list_prompt = f"Use list_files to show the contents of {test_dir}"
    result.sendline(f"{final_list_prompt}\r")

    # Wait for auto-save to indicate completion
    result.child.expect(r"Auto-saved session", timeout=120)
    cli_harness.wait_for_ready(result)
    time.sleep(5)

    # Verify the final state
    _assert_file_exists(test_dir, "hello.py")
    _assert_file_exists(test_dir, "project/README.md")
    _assert_file_not_exists(test_dir, "simple.txt")

    # Verify final file contents
    _assert_file_contains(test_dir, "hello.py", "def greet")
    _assert_file_contains(test_dir, "hello.py", "Welcome!")

    # Check that simple.txt is not mentioned in the final listing
    final_log = result.read_log()
    assert "simple.txt" not in final_log or "deleted" in final_log, (
        f"simple.txt should not appear in final listing unless deleted. Log: {final_log}"
    )

    # Cleanup test directory
    shutil.rmtree(test_dir, ignore_errors=True)

    # Clean exit
    result.sendline("/quit\r")
    try:
        result.child.expect("EOF", timeout=10)
    except Exception:
        pass
