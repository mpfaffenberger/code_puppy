"""Cancellation must not abandon a terminal reader."""

import asyncio
import threading
from contextlib import contextmanager

import pytest

from code_puppy.tools.approval_feedback import read_feedback


@pytest.mark.parametrize("raises", [False, True])
async def test_cancellation_waits_for_reader_before_releasing_ownership(raises):
    started = threading.Event()
    finish = threading.Event()
    released = False

    @contextmanager
    def stdin_owner():
        nonlocal released
        try:
            yield
        finally:
            released = True

    def prompt():
        started.set()
        assert finish.wait(timeout=5)
        if raises:
            raise EOFError
        return "feedback"

    async def request():
        with stdin_owner():
            return await read_feedback(prompt)

    task = asyncio.create_task(request())
    try:
        assert await asyncio.to_thread(started.wait, 5)
        for _ in range(2):
            task.cancel()
            await asyncio.sleep(0.01)
            assert not released
            assert not task.done()
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)
    assert released


async def test_feedback_and_errors_pass_through():
    assert await read_feedback(lambda: "feedback") == "feedback"

    def closed_input():
        raise EOFError

    with pytest.raises(EOFError):
        await read_feedback(closed_input)
