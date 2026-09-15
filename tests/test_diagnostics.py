"""SIGUSR2 stack-dump diagnostics (the wedged-cancellation conviction kit)."""

import asyncio
import io
import os
import signal
import sys

import pytest

from code_puppy import diagnostics


async def test_dump_stacks_includes_threads_and_tasks():
    async def parked():
        await asyncio.sleep(60)

    task = asyncio.create_task(parked(), name="wedge-suspect")
    await asyncio.sleep(0)  # let it park on the sleep

    buf = io.StringIO()
    diagnostics.dump_stacks(buf, loop=asyncio.get_running_loop())
    out = buf.getvalue()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "OS threads" in out
    assert "asyncio tasks" in out
    assert "wedge-suspect" in out  # the parked task's stack was captured
    assert "parked" in out  # ...down to its coroutine frame


async def test_dump_stacks_without_loop_says_so():
    buf = io.StringIO()
    diagnostics.dump_stacks(buf, loop=None)
    # No captured loop in a fresh test process -> honest section marker
    # (unless an earlier install captured one; accept either honest form).
    assert "asyncio tasks" in buf.getvalue()


async def test_write_stack_dump_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, "DUMP_DIR", tmp_path)
    path = diagnostics.write_stack_dump(loop=asyncio.get_running_loop())
    assert path is not None and path.exists()
    content = path.read_text()
    assert "code-puppy stack dump" in content
    assert f"pid {os.getpid()}" in content


async def test_write_stack_dump_never_raises(tmp_path, monkeypatch):
    # Unwritable dump dir: diagnostics must not hurt the patient.
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file, not dir")
    monkeypatch.setattr(diagnostics, "DUMP_DIR", blocker)
    assert diagnostics.write_stack_dump() is None


@pytest.mark.skipif(not hasattr(signal, "SIGUSR2"), reason="SIGUSR2 is POSIX-only")
async def test_sigusr2_end_to_end(tmp_path, monkeypatch):
    """Real signal in, dump file out — the exact field workflow."""
    monkeypatch.setattr(diagnostics, "DUMP_DIR", tmp_path)
    previous = signal.getsignal(signal.SIGUSR2)
    try:
        assert diagnostics.install_stack_dump_handler(asyncio.get_running_loop())
        os.kill(os.getpid(), signal.SIGUSR2)
        # Give the interpreter a beat to run the Python-level handler.
        for _ in range(50):
            await asyncio.sleep(0.01)
            if list(tmp_path.glob("stackdump-*.txt")):
                break
        dumps = list(tmp_path.glob("stackdump-*.txt"))
        assert dumps, "SIGUSR2 did not produce a dump file"
        assert "asyncio tasks" in dumps[0].read_text()
    finally:
        signal.signal(signal.SIGUSR2, previous)


def test_install_returns_false_without_sigusr2(monkeypatch):
    if sys.platform == "win32":
        assert diagnostics.install_stack_dump_handler() is False
        return
    # Simulate Windows: hide SIGUSR2 from the signal module.
    monkeypatch.delattr(signal, "SIGUSR2")
    assert diagnostics.install_stack_dump_handler() is False
