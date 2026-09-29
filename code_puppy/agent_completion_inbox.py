"""Loop-local completion delivery, independent of user steering queues.

Completions belong to an agent object, not whichever agent is selected later.
The runtime and idle prompt share this inbox, so only one consumer can claim
each message. Text is model-facing data and must not resolve attachments.
"""

import asyncio
from collections import deque
from weakref import WeakKeyDictionary

_inboxes = WeakKeyDictionary()


class _Inbox:
    def __init__(self):
        self.messages = deque()
        self.ready = asyncio.Event()


def _inbox(agent):
    if agent not in _inboxes:
        _inboxes[agent] = _Inbox()
    return _inboxes[agent]


def deliver_completion(agent, text: str) -> None:
    """Deliver on the owning event loop; never execute completion text."""
    inbox = _inbox(agent)
    inbox.messages.append(text)
    inbox.ready.set()


def pop_completion(agent) -> str | None:
    inbox = _inbox(agent)
    if not inbox.messages:
        return None
    text = inbox.messages.popleft()
    if not inbox.messages:
        inbox.ready.clear()
    return text


async def wait_for_completion_or_input(agent, input_queue):
    """Wait without consuming input speculatively or losing simultaneous input.

    A queue getter may already have claimed user input when completion arrives.
    Prefer that input if both are ready; the completion stays in the inbox.
    """
    inbox = _inbox(agent)
    input_task = asyncio.create_task(input_queue.get())
    ready_task = asyncio.create_task(inbox.ready.wait())
    try:
        await asyncio.wait(
            (input_task, ready_task), return_when=asyncio.FIRST_COMPLETED
        )
        if input_task.done():
            return input_task.result()
        if inbox.messages:
            # Only a trusted wake-up prompt traverses CLI command/attachment
            # handling. The actual output is claimed by the history processor.
            return (
                "A background sub-agent has completed. Process its completion report."
            )
        return await input_task
    finally:
        for task in (input_task, ready_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(input_task, ready_task, return_exceptions=True)
