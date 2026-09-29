#!/usr/bin/env python3
"""Stress repro for the cancelled-run wedge (sub-agents + hammered Ctrl+C).

Drives a real interactive code-puppy in a pty, per iteration:

1. wait for warmup, submit a prompt that fans out to a sub-agent;
2. after a (randomized) delay, hammer raw Ctrl+C like an impatient human;
3. give the cancel time to settle, then type ``exit``;
4. if the process is still alive after the exit timeout, it WEDGED:
   send SIGUSR2 (code-puppy's stack-dump hook writes thread + asyncio-task
   stacks to ~/.code_puppy/stackdumps/), then SIGKILL and keep the pty
   transcript for the post-mortem.

POSIX only (pty + SIGUSR2). Needs a configured model — this makes real
agent runs on purpose; the wedge lives in real cancel-scope teardown.

Usage:
    python scripts/repro_cancel_wedge.py --iterations 10
    python scripts/repro_cancel_wedge.py --cancel-after 2-8 \
        --prompt "use invoke_agent to have a sub-agent list this directory"

Exit code: number of wedged iterations (0 = no repro).
"""

from __future__ import annotations

import argparse
import os
import pty
import random
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

STACKDUMP_DIR = Path.home() / ".code_puppy" / "stackdumps"
ARTIFACT_DIR = Path("wedge_artifacts")

DEFAULT_PROMPT = (
    "Use invoke_agent to ask a sub-agent to recursively list every file in "
    "this repository and summarize the largest ten. Do not answer directly; "
    "you must delegate to the sub-agent."
)

CTRL_C = b"\x03"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--iterations", type=int, default=5)
    p.add_argument("--prompt", default=DEFAULT_PROMPT)
    p.add_argument(
        "--cmd",
        default="code-puppy",
        help="command to launch (default: code-puppy on PATH)",
    )
    p.add_argument(
        "--warmup",
        type=float,
        default=12.0,
        help="seconds to let the REPL boot before submitting the prompt",
    )
    p.add_argument(
        "--cancel-after",
        default="4-15",
        help="seconds between prompt and Ctrl+C hammer; 'LO-HI' randomizes "
        "per iteration to catch different cancel points",
    )
    p.add_argument("--hammer", type=int, default=3, help="Ctrl+C presses")
    p.add_argument(
        "--hammer-gap",
        type=float,
        default=0.7,
        help="seconds between presses. Default stays OUTSIDE the 0.5s "
        "double-tap window: quit-speed taps at idle just exit the app, "
        "which ends the iteration before a wedge can express itself",
    )
    p.add_argument(
        "--settle",
        type=float,
        default=8.0,
        help="seconds to let the cancel unwind before typing exit",
    )
    p.add_argument(
        "--exit-timeout",
        type=float,
        default=20.0,
        help="seconds to wait for a clean exit before declaring a wedge",
    )
    return p.parse_args()


def cancel_delay(spec: str) -> float:
    if "-" in spec:
        lo, hi = (float(x) for x in spec.split("-", 1))
        return random.uniform(lo, hi)
    return float(spec)


class PtySession:
    """A child process on a pty with a drained, recorded transcript."""

    def __init__(self, cmd: str, transcript_path: Path) -> None:
        self.transcript_path = transcript_path
        self._master, slave = pty.openpty()
        self._transcript = open(transcript_path, "wb")
        self.proc = subprocess.Popen(
            cmd.split(),
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        os.close(slave)

    def drain(self, seconds: float) -> None:
        """Pump pty output into the transcript for ``seconds``. The child
        blocks on tty writes if nobody reads, so this doubles as sleep."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            timeout = max(0.0, deadline - time.monotonic())
            ready, _, _ = select.select([self._master], [], [], min(timeout, 0.25))
            if not ready:
                continue
            try:
                chunk = os.read(self._master, 65536)
            except OSError:
                break  # child side closed
            if not chunk:
                break
            self._transcript.write(chunk)
        self._transcript.flush()

    def send(self, data: bytes) -> bool:
        """Write to the pty; False if the child is already gone (EIO)."""
        try:
            os.write(self._master, data)
            return True
        except OSError:
            return False

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        try:
            os.close(self._master)
        except OSError:
            pass
        self._transcript.close()


def run_iteration(i: int, args: argparse.Namespace) -> bool:
    """Returns True if this iteration wedged."""
    ARTIFACT_DIR.mkdir(exist_ok=True)
    transcript = ARTIFACT_DIR / f"iter{i:03d}.transcript.txt"
    session = PtySession(args.cmd, transcript)
    delay = cancel_delay(args.cancel_after)
    print(f"[iter {i}] pid={session.proc.pid} cancel after {delay:.1f}s")
    wedged = False
    try:
        session.drain(args.warmup)
        session.send(args.prompt.encode() + b"\r")
        session.drain(delay)

        print(f"[iter {i}] hammering Ctrl+C x{args.hammer}")
        for _ in range(args.hammer):
            session.send(CTRL_C)
            session.drain(args.hammer_gap)
        session.drain(args.settle)

        if not session.alive():
            # Hammer landed at idle -> double-tap quit. Clean outcome (that
            # exit path working is literally one of the fixes under test).
            print(f"[iter {i}] app exited during/after hammer (double-tap quit)")
        elif not session.send(b"exit\r"):
            print(f"[iter {i}] pty closed before exit probe (child gone)")
        deadline = time.monotonic() + args.exit_timeout
        while session.alive() and time.monotonic() < deadline:
            session.drain(0.5)

        if session.alive():
            wedged = True
            before = (
                set(STACKDUMP_DIR.glob("*.txt")) if STACKDUMP_DIR.exists() else set()
            )
            print(f"[iter {i}] WEDGED — sending SIGUSR2 for stack dump")
            os.kill(session.proc.pid, signal.SIGUSR2)
            session.drain(3.0)  # let the dump land
            after = (
                set(STACKDUMP_DIR.glob("*.txt")) if STACKDUMP_DIR.exists() else set()
            )
            for dump in sorted(after - before):
                dest = ARTIFACT_DIR / f"iter{i:03d}.{dump.name}"
                dest.write_bytes(dump.read_bytes())
                print(f"[iter {i}] stack dump saved: {dest}")
            if not (after - before):
                print(f"[iter {i}] no dump appeared — process too far gone?")
            os.kill(session.proc.pid, signal.SIGKILL)
        else:
            print(f"[iter {i}] clean exit (rc={session.proc.poll()})")
    finally:
        if session.alive():
            session.proc.kill()
        session.proc.wait(timeout=10)
        session.close()
    if wedged:
        print(f"[iter {i}] transcript: {transcript}")
    else:
        transcript.unlink(missing_ok=True)  # keep artifacts wedges-only
    return wedged


def main() -> int:
    if os.name == "nt":
        print("POSIX only (pty + SIGUSR2).", file=sys.stderr)
        return 2
    args = parse_args()
    wedges = 0
    for i in range(1, args.iterations + 1):
        wedges += run_iteration(i, args)
    print(
        f"\n{args.iterations} iteration(s), {wedges} wedge(s)."
        + (f" Artifacts in {ARTIFACT_DIR}/" if wedges else " No repro this round.")
    )
    return wedges


if __name__ == "__main__":
    sys.exit(main())
