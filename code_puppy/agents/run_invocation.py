"""Separate logical-prompt retries from physical model-call resources."""

import asyncio
from contextlib import AsyncExitStack

from code_puppy.callbacks import on_agent_exception


class ModelCall:
    """Run one physical attempt against a freshly resolved client.

    ``resolve`` returns the current client, which may have been replaced by
    recovery. ``contexts(client)`` creates fresh async context managers for
    that same client. Checkpoint state belongs outside this adapter: pass it
    to ``resumable_call`` once for each logical prompt, before applying retry.
    Neither the client nor its context managers are cached between attempts.
    """

    def __init__(self, resolve, contexts):
        self.resolve = resolve
        self.contexts = contexts

    async def run(self, prompt, **kwargs):
        current = self.resolve()
        async with AsyncExitStack() as stack:
            for context in self.contexts(current):
                await stack.enter_async_context(context)
            return await current.run(prompt, **kwargs)


async def run_with_exception_retry(call, *, agent):
    """Let exception callbacks request one retry of the same logical call.

    The callback may replace the model client; ``ModelCall`` resolves that
    replacement on the next attempt. Retry the existing callable, rather than
    constructing another checkpoint. Exceptions from the retry propagate and
    cancellation never enters exception recovery.
    """
    try:
        return await call()
    except Exception as exc:
        hook_results = await on_agent_exception(
            exc,
            agent=agent,
            agent_name=agent.name,
            model_name=agent.get_model_name(),
        )
        retry_req = next(
            (r for r in hook_results if isinstance(r, dict) and r.get("retry")),
            None,
        )
        if not retry_req:
            raise

        retry_delay = retry_req.get("delay", 0.0)
        if retry_delay:
            await asyncio.sleep(retry_delay)
        return await call()
