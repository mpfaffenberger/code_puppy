"""Tests for the interactive-mode SIGINT guard (Ctrl+C double-tap fix).

Ctrl+C in Code Puppy is a *cancel* gesture, never a *quit* gesture. A fast
Ctrl+C double-tap used to exit the whole process: the second tap landed in
the unwind window after the first cancel, hit Python's default SIGINT
handler, raised KeyboardInterrupt, and bubbled to main_entry. The session
guard installed by interactive_mode swallows SIGINT in those gaps.

IMPORTANT: the behavioural tests run in *subprocesses*. Delivering a real
SIGINT to the pytest process itself is a flaky landmine -- a slightly-late
signal can be raised inside an unrelated later test and corrupt the whole
run. Isolating each scenario in its own interpreter keeps signals from ever
escaping into the test runner.
"""

import signal
import subprocess
import sys
import textwrap

from code_puppy.cli_runner import _interactive_sigint_guard


def test_guard_returns_none_and_does_not_raise():
    # The guard must be a benign no-op: never raise, never exit.
    assert _interactive_sigint_guard(signal.SIGINT, None) is None


def _run_signal_subprocess(handler_setup: str) -> subprocess.CompletedProcess:
    """Run a child interpreter that installs a SIGINT handler and signals itself.

    ``handler_setup`` is Python source that installs the desired SIGINT
    handler. The child then raises SIGINT and prints SURVIVED if it lived.
    """
    script = textwrap.dedent(
        """
        import os, signal, time, sys
        {handler_setup}
        os.kill(os.getpid(), signal.SIGINT)
        time.sleep(0.1)
        print("SURVIVED")
        """
    ).format(handler_setup=handler_setup)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_guard_swallows_real_sigint_signal():
    """With the guard installed, a delivered SIGINT must NOT kill the process."""
    proc = _run_signal_subprocess(
        "from code_puppy.cli_runner import _interactive_sigint_guard\n"
        "signal.signal(signal.SIGINT, _interactive_sigint_guard)"
    )
    assert proc.returncode == 0, f"guard let the process die: {proc.stderr}"
    assert "SURVIVED" in proc.stdout


def test_default_handler_would_kill_without_guard():
    """Control: under the default handler the same SIGINT kills the process.

    Proves the guard is what fixes the crash, not some unrelated quirk.
    """
    proc = _run_signal_subprocess(
        "signal.signal(signal.SIGINT, signal.default_int_handler)"
    )
    assert proc.returncode != 0, "sanity: default handler should have raised"
    assert "SURVIVED" not in proc.stdout
    assert "KeyboardInterrupt" in proc.stderr
