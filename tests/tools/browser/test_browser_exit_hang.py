"""Regression: the interpreter must exit promptly after a browser was left open.

The atexit hook used to await Playwright objects from a new event loop after
``asyncio.run`` had closed the owning loop, which hung the process.
"""

import os
import subprocess
import sys
import textwrap
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="uses pgrep to detect leaked browser processes"
)

_SCRIPT = textwrap.dedent(
    """
    import asyncio, sys
    from code_puppy.tools.browser import browser_manager as bm

    async def _no_install():
        raise RuntimeError("Chromium is not installed")

    bm._install_chromium = _no_install

    async def main():
        manager = bm.get_browser_manager(sys.argv[1])
        try:
            await manager.async_initialize()
            await manager.new_page("data:text/html,<h1>hi</h1>")
        except Exception as exc:
            print("INIT_FAILED", exc, flush=True)
            return 0
        print("OPENED", manager.profile_dir, flush=True)
        return 0

    sys.exit(asyncio.run(main()))
    """
)


def _wait_for_status_line(stream, timeout: float) -> str:
    found: list[str] = []
    done = threading.Event()

    def _read() -> None:
        # Keep draining so the child never blocks on a full pipe.
        for line in stream:
            if not found and line.startswith(("OPENED", "INIT_FAILED")):
                found.append(line)
                done.set()
        done.set()

    threading.Thread(target=_read, daemon=True).start()
    done.wait(timeout)
    return found[0] if found else ""


def _leftover_processes(profile_dir: str) -> str:
    # Chrome exits on its own shortly after the driver pipe closes.
    deadline = time.monotonic() + 10
    while True:
        out = subprocess.run(
            ["pgrep", "-fl", profile_dir], capture_output=True, text=True
        ).stdout.strip()
        if not out or time.monotonic() > deadline:
            return out
        time.sleep(0.5)


def test_process_exits_when_browser_left_open(tmp_path):
    env = {**os.environ, "XDG_CACHE_HOME": str(tmp_path), "BROWSER_HEADLESS": "true"}
    stderr_path = tmp_path / "stderr.log"
    with open(stderr_path, "w") as stderr_file:
        proc = subprocess.Popen(
            [sys.executable, "-c", _SCRIPT, f"exit-hang-{os.getpid()}"],
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            env=env,
        )
    try:
        status = _wait_for_status_line(proc.stdout, timeout=60)
        if not status.startswith("OPENED"):
            pytest.skip(f"no launchable browser: {status.strip() or 'timed out'}")
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pytest.fail("interpreter hung at exit after the browser was opened")
    finally:
        if proc.poll() is None:
            proc.kill()
            subprocess.run(["pkill", "-f", str(tmp_path)])

    assert proc.returncode == 0, stderr_path.read_text()
    assert _leftover_processes(status.split("OPENED", 1)[1].strip()) == ""
