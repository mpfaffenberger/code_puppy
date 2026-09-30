"""Exercise guard feedback with real terminal input, not a mocked Prompt."""

import os
import sys

import pexpect
import pytest


@pytest.mark.parametrize(
    "guard,command",
    [
        ("destructive_command_guard", "git reset --hard"),
        ("force_push_guard", "git push --force origin main"),
    ],
)
def test_guard_feedback_terminal(guard, command):
    script = f"""
import asyncio
from code_puppy_core_plugins.{guard}.register_callbacks import _prompt_user_approval
from code_puppy_core_plugins.{guard}.detector import {"detect_force_push" if guard == "force_push_guard" else "detect_destructive_command"} as detect
from code_puppy.messaging.run_ui import start_persistent_ui, stop_persistent_ui

async def main():
    start_persistent_ui()
    try:
        async def heartbeat():
            while True:
                await asyncio.sleep(0.2)
                print("LOOP_ALIVE", flush=True)

        task = asyncio.create_task(heartbeat())
        result = await _prompt_user_approval({command!r}, detect({command!r}))
        task.cancel()
        print("GUARD_RESULT", repr(result), flush=True)
    finally:
        stop_persistent_ui()

asyncio.run(main())
"""
    child = pexpect.spawn(
        sys.executable,
        ["-c", script],
        encoding="utf-8",
        timeout=15,
        env={**os.environ, "TERM": "xterm-256color", "NO_COLOR": "1"},
        dimensions=(40, 120),
    )
    try:
        child.expect("Reject with feedback")
        child.send("\x1b[B\x1b[B\r")
        child.expect("\u27a4")
        # Discard earlier heartbeats: one must arrive while feedback is waiting.
        child.expect("LOOP_ALIVE", timeout=2)
        child.sendline("Keep the existing history instead")
        child.expect("GUARD_RESULT")
        child.expect(pexpect.EOF)
        assert "'blocked': True" in child.before
        assert "Keep the existing history instead" in child.before
        child.close()
        assert child.exitstatus == 0
    finally:
        child.close(force=True)
