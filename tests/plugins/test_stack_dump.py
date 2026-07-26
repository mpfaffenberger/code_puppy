"""Tests for the stack_dump plugin (SIGUSR1 → all-thread stack dump)."""

import os
import signal
import time

import pytest

from code_puppy.plugins.stack_dump import register_callbacks as sd


@pytest.fixture(autouse=True)
def _reset_plugin_state(tmp_path, monkeypatch):
    """Point the log dir at a tmpdir and disarm after each test."""
    import faulthandler

    import code_puppy.error_logging as el

    monkeypatch.setattr(el, "LOGS_DIR", str(tmp_path))
    yield
    if hasattr(signal, "SIGUSR1"):
        try:
            faulthandler.unregister(signal.SIGUSR1)
        except Exception:
            pass
    if sd._dump_file is not None:
        try:
            sd._dump_file.close()
        except Exception:
            pass
        sd._dump_file = None


posix_only = pytest.mark.skipif(
    not hasattr(signal, "SIGUSR1"), reason="SIGUSR1 is POSIX-only"
)


@posix_only
def test_startup_arms_handler_and_writes_breadcrumb(tmp_path):
    sd._on_startup()
    path = tmp_path / "stacks.log"
    assert path.exists()
    content = path.read_text()
    assert f"pid={os.getpid()}" in content
    assert "kill -USR1" in content


@posix_only
def test_startup_is_idempotent(tmp_path):
    sd._on_startup()
    sd._on_startup()  # second call must not re-open / re-write
    content = (tmp_path / "stacks.log").read_text()
    assert content.count("stack_dump armed") == 1


@posix_only
def test_sigusr1_dumps_all_thread_stacks(tmp_path):
    """The whole point: a real SIGUSR1 produces real stack traces."""
    sd._on_startup()
    os.kill(os.getpid(), signal.SIGUSR1)
    # faulthandler writes from the C handler; give the fd a beat.
    deadline = time.time() + 2.0
    path = tmp_path / "stacks.log"
    while time.time() < deadline:
        if "Current thread" in path.read_text():
            break
        time.sleep(0.05)
    content = path.read_text()
    assert "Current thread" in content  # faulthandler's dump header
    assert "test_sigusr1_dumps_all_thread_stacks" in content  # our frame


@posix_only
def test_arm_failure_is_swallowed(monkeypatch):
    """A broken logs dir must never crash startup (fail gracefully)."""

    def boom():
        raise OSError("disk full of dog hair")

    monkeypatch.setattr("code_puppy.error_logging._ensure_logs_dir", boom, raising=True)
    sd._on_startup()  # must not raise
    assert sd._dump_file is None
