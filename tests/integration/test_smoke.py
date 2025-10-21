"""Extremely basic pexpect smoke test – no harness, just raw subprocess."""

import time

import pexpect


def test_version_smoke() -> None:
    child = pexpect.spawn("code-puppy --version", encoding="utf-8")
    child.expect(pexpect.EOF, timeout=10)
    output = child.before
    assert output.strip()  # just ensure we got something
    print("\n[SMOKE] version output:", output)


def test_help_smoke() -> None:
    child = pexpect.spawn("code-puppy --help", encoding="utf-8")
    child.expect("--version", timeout=10)
    child.expect(pexpect.EOF, timeout=10)
    output = child.before
    assert "show version and exit" in output.lower()
    print("\n[SMOKE] help output seen")


def test_interactive_smoke() -> None:
    child = pexpect.spawn("code-puppy -i", encoding="utf-8")

    # Handle initial prompts that might appear in CI
    try:
        child.expect("What should we name the puppy?", timeout=5)
        child.sendline("IntegrationPup\r")
        child.expect("What's your name", timeout=5)
        child.sendline("HarnessTester\r")
    except pexpect.exceptions.TIMEOUT:
        # Config likely pre-provisioned; proceed
        pass

    # Skip autosave picker if it appears
    try:
        child.expect("1-5 to load, 6 for next", timeout=5)
        child.send("\r")
        time.sleep(0.3)
        child.send("\r")
    except pexpect.exceptions.TIMEOUT:
        pass

    # Look for either "Interactive Mode" or the prompt indicator
    try:
        child.expect("Interactive Mode", timeout=10)
    except pexpect.exceptions.TIMEOUT:
        # If no "Interactive Mode" text, look for the prompt
        child.expect(">>> ", timeout=10)
    child.expect("Enter your coding task", timeout=10)
    print("\n[SMOKE] CLI entered interactive mode")
    time.sleep(5)
    child.send("/quit\r")
    time.sleep(0.3)
    child.expect(pexpect.EOF, timeout=10)
    print("\n[SMOKE] CLI exited cleanly")
