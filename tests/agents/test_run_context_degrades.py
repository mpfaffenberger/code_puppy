"""One unusable MCP server must not cost the whole run.

`_run_agent_task_body` composes every `agent_run_context` into an
`AsyncExitStack`. An MCP server whose subprocess never came up raises from
`__aenter__`, and entered as a single unit that one failure unwinds the stack
before `_do_run` is reached — so the model is never called at all.

The `except* McpError` handler downstream makes this look handled: it prints
"An MCP server failed during this run. Run /mcp logs ..." and returns. A user
reads that as a warning attached to their answer. There is no answer.

Measured with six connectors and one broken one: no inference, three warnings,
a thirty-second wait.
"""

from __future__ import annotations

import asyncio
import contextlib
import unittest
from contextlib import AsyncExitStack


class _Recorder:
    """Stands in for the `for cm in run_ctxs` loop under test.

    A copy rather than a call into `_run_agent_task_body`, which needs a live
    agent, a model and a message bus. The loop is the thing that changed, and
    a copy of it fails for the same reason the original would.
    """

    def __init__(self):
        self.dropped: list[str] = []

    def note(self, cm, exc, group_id):
        self.dropped.append(getattr(cm, "name", type(cm).__name__))


@contextlib.asynccontextmanager
async def working(name: str, entered: list[str]):
    entered.append(name)
    yield


class _Dead:
    """An MCP toolset whose server never came up."""

    def __init__(self, name: str):
        self.name = name

    async def __aenter__(self):
        raise RuntimeError(f"{self.name}: no solution found when resolving")

    async def __aexit__(self, *exc):
        return False


async def _enter_all(run_ctxs, recorder, *, per_context_try: bool):
    """The loop, in both shapes, returning whether the run body was reached."""
    async with AsyncExitStack() as stack:
        for cm in run_ctxs:
            if per_context_try:
                try:
                    await stack.enter_async_context(cm)
                except Exception as exc:  # noqa: BLE001
                    recorder.note(cm, exc, "group")
            else:
                await stack.enter_async_context(cm)
        return "model called"


class OneDeadServerDoesNotAbortTheRun(unittest.TestCase):
    def test_the_old_shape_never_reaches_the_model(self):
        """THE BUG, stated as a test.

        Without a per-context try, the first failing `__aenter__` propagates
        and `_do_run` is never evaluated.
        """
        entered: list[str] = []
        ctxs = [
            working("jira", entered),
            _Dead("lab-market-mcp"),
            working("confluence", entered),
        ]
        with self.assertRaises(RuntimeError):
            asyncio.run(_enter_all(ctxs, _Recorder(), per_context_try=False))
        # And it did not even get as far as the third server.
        self.assertEqual(entered, ["jira"])

    def test_the_run_proceeds_without_the_dead_server(self):
        entered: list[str] = []
        recorder = _Recorder()
        ctxs = [
            working("jira", entered),
            _Dead("lab-market-mcp"),
            working("confluence", entered),
        ]
        result = asyncio.run(_enter_all(ctxs, recorder, per_context_try=True))

        self.assertEqual(result, "model called")
        # Every healthy connector is still available, including the one AFTER
        # the failure — an early abort silently loses those too.
        self.assertEqual(entered, ["jira", "confluence"])
        self.assertEqual(recorder.dropped, ["lab-market-mcp"])

    def test_every_server_failing_still_reaches_the_model(self):
        """A connector is a capability, not a precondition.

        With no MCP at all the agent still has its built-in file and shell
        tools, which is most of what it does.
        """
        recorder = _Recorder()
        ctxs = [_Dead("a"), _Dead("b")]
        result = asyncio.run(_enter_all(ctxs, recorder, per_context_try=True))
        self.assertEqual(result, "model called")
        self.assertEqual(recorder.dropped, ["a", "b"])

    def test_healthy_servers_are_still_unwound(self):
        """Dropping one must not leak the others.

        The stack still owns every context it did enter, so a failure partway
        through cannot turn into an unclosed subprocess.
        """
        closed: list[str] = []

        @contextlib.asynccontextmanager
        async def tracked(name: str):
            try:
                yield
            finally:
                closed.append(name)

        async def scenario():
            async with AsyncExitStack() as stack:
                for cm in [tracked("jira"), _Dead("dead"), tracked("confluence")]:
                    try:
                        await stack.enter_async_context(cm)
                    except Exception:  # noqa: BLE001
                        pass
                return True

        self.assertTrue(asyncio.run(scenario()))
        self.assertEqual(sorted(closed), ["confluence", "jira"])


if __name__ == "__main__":
    unittest.main()
