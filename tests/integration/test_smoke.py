"""Extremely basic pexpect smoke test – no harness, just raw subprocess."""

import time

import pexpect
import pytest

from tests.integration.cli_expect.pexpect_compat import (
    HAS_WINDOWS_BACKEND,
    IS_WINDOWS,
    spawn_process,
)

if IS_WINDOWS and not HAS_WINDOWS_BACKEND:  # pragma: no cover - Windows-only guard
    pytest.skip(
        "pexpect Windows backend missing; install pywinpty or compatible provider",
        allow_module_level=True,
    )


def test_version_smoke() -> None:
    child = spawn_process("code-puppy --version", encoding="utf-8")
    child.expect(pexpect.EOF, timeout=10)
    output = child.before
    assert output.strip()  # just ensure we got something
    print("\n[SMOKE] version output:", output)


def test_help_smoke() -> None:
    child = spawn_process("code-puppy --help", encoding="utf-8")
    child.expect("--version", timeout=10)
    child.expect(pexpect.EOF, timeout=10)
    output = child.before
    assert "show version and exit" in output.lower()
    print("\n[SMOKE] help output seen")


def test_interactive_smoke() -> None:
    child = spawn_process("code-puppy -i", encoding="utf-8")
    child.expect("Interactive Mode", timeout=10)
    child.expect("1-5 to load, 6 for next", timeout=10)
    child.send("\r")
    time.sleep(0.3)
    child.send("\r")
    time.sleep(0.3)
    child.expect("Enter your coding task", timeout=10)
    print("\n[SMOKE] CLI entered interactive mode")
    time.sleep(5)
    child.send("/quit\r")
    time.sleep(0.3)
    child.expect(pexpect.EOF, timeout=10)
    print("\n[SMOKE] CLI exited cleanly")
