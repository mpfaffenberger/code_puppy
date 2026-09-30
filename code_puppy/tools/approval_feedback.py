"""Keep blocking feedback input off the loop without abandoning stdin."""

import asyncio
from collections.abc import Callable


async def read_feedback(prompt: Callable[[], str]) -> str:
    """Read feedback in a worker, retaining ownership through cancellation.

    A blocking terminal read cannot be interrupted by cancelling its asyncio
    waiter. Defer cancellation until the user submits or closes the input;
    callers must retain their stdin suspension and approval lock throughout.
    """
    reader = asyncio.create_task(asyncio.to_thread(prompt))
    try:
        return await asyncio.shield(reader)
    except asyncio.CancelledError:
        # Further cancel requests must not release stdin while it is still
        # being read. Retrieve the result/exception before propagating cancel.
        while not reader.done():
            try:
                await asyncio.shield(reader)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not reader.cancelled():
            reader.exception()
        raise
