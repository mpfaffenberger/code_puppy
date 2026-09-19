#!/usr/bin/env python3
"""Measure uv run code-puppy through a usable prompt in an isolated PTY.

No model request is submitted. HOME/XDG are temporary; real credentials and
project plugins are not used. --profile captures main-thread cProfile data
until the REPL starts awaiting input (profiling adds overhead).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import sys

import pexpect

HOOK = """
import os, sys, threading, time
profile = None
if os.environ.get("STARTUP_PROFILE"):
    import cProfile
    profile = cProfile.Profile()
    profile.enable()

def install():
    while True:
        module = sys.modules.get("code_puppy.messaging.run_ui")
        original = getattr(module, "wait_for_idle_submission", None)
        if original is not None:
            break
        time.sleep(0.001)
    async def measured():
        if profile is not None:
            profile.disable()
            profile.dump_stats(os.environ["STARTUP_PROFILE"])
        os.write(1, b"STARTUP_INPUT_READY")
        return await original()
    module.wait_for_idle_submission = measured
threading.Thread(target=install, daemon=True).start()
"""


def measure(profile: str | None) -> dict:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="puppy-startup-") as tmp:
        home = Path(tmp)
        config = home / ".code_puppy"
        config.mkdir()
        (config / "puppy.cfg").write_text(
            "[puppy]\npuppy_name = Biscuit\nowner_name = Benchmark\n"
            "auto_save_session = false\nenable_logfire = false\n"
        )
        (home / "sitecustomize.py").write_text(HOOK)
        env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
        env.update(
            HOME=tmp,
            PYTHONPATH=str(home) + os.pathsep + str(root),
            TERM="xterm-256color",
            COLORTERM="truecolor",
            UV_PROJECT=str(root),
            PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring",
        )
        env.pop("UV_PYTHON", None)
        env["UV_PYTHON_INSTALL_DIR"] = str(Path.home() / ".local/share/uv/python")
        env["UV_CACHE_DIR"] = str(Path.home() / ".cache" / "uv")
        if profile:
            env["STARTUP_PROFILE"] = str(Path(profile).resolve())
        start = time.perf_counter()
        child = pexpect.spawn(
            "uv",
            ["run", "code-puppy"],
            cwd=tmp,
            env=env,
            encoding="utf-8",
            timeout=90,
            dimensions=(40, 120),
        )
        try:
            child.expect_exact("STARTUP_INPUT_READY")
            if os.environ.get("STARTUP_DEBUG"):
                print(repr(child.before[:1800]), file=sys.stderr)
            ready = time.perf_counter() - start
            # Readiness is not just a painted banner: verify key processing.
            child.send("z")
            child.expect_exact("z")
            typed = time.perf_counter() - start
            child.send("\x15\x04")  # clear probe, EOF; never submit a model prompt
            child.expect(pexpect.EOF, timeout=15)
            return {"ready_seconds": round(ready, 4), "typed_seconds": round(typed, 4)}
        except (pexpect.TIMEOUT, pexpect.EOF):
            raise RuntimeError(f"Startup failed: {child.before[-4000:]}") from None
        finally:
            child.close(force=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="Write cProfile data to this file")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    for _ in range(args.runs):
        print(json.dumps(measure(args.profile)), flush=True)
