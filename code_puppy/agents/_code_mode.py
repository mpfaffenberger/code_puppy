"""Speculative CodeMode capability wiring for agents that opt in.

Dogfoods speculative programmatic tool calling (sPTC) from
https://github.com/pydantic/pydantic-ai-harness/pull/699 (design notes in
pydantic-ai-notes#14, idea from https://alexzhang13.github.io/blog/2026/spec-ptc/).

This is deliberately not wired into every agent. An agent opts in by setting
``speculative_code_mode = True`` (see ``BaseAgent``). For an opted-in agent,
ALL of its tools fold into the single ``run_code`` sandbox (the model sees no
native tools at all -- the RLM shape), but only the read-only trio below
speculates. That allowlist is the safety contract: an early launch may run
for a branch the snippet never takes, so it is reserved for calls that are
harmless to re-run or discard; everything else waits for real execution.

The sandbox is not fully sealed either: the workspace mounts read-write so
snippets can drive real project files through ``pathlib`` directly, and an
`OSAccess` handler provides isolated environment variables, the host clock,
and in-memory scratch files. Network stays tool-shaped: there is no socket in
the sandbox, so anything remote goes through a wrapped tool, which is also
the FFI story -- any host Python function CodeMode wraps becomes an async
function inside the snippet.

The Monty agent (``agent_monty.py``) is the resident example; everything else
keeps ordinary native tool calls, where models are strongest for single
actions.
"""

from __future__ import annotations

import os
from typing import Any, List, Sequence

from pydantic_ai.capabilities import AbstractCapability
from pydantic_monty import MountDir, OSAccess

from pydantic_ai_harness.code_mode import CodeMode

from code_puppy.config import get_speculative_code_mode_enabled

# The read-only trio: pure with respect to the workspace, safe to re-run or discard.
SANDBOXED_READ_ONLY_TOOLS = ("list_files", "read_file", "grep")


class SilenceToolOutput(AbstractCapability[Any]):
    """Suppress TOOL_OUTPUT bus messages for the duration of the run.

    Inside a speculative CodeMode run every tool executes within `run_code`:
    its UI rendering (file dumps, grep boxes, shell lines) would repeat what
    the snippet already filters and returns. The speculation panel and the
    model's own narration are the UX. Warnings and errors still pass -- the
    bus-level filter is category- and level-aware.
    """

    async def wrap_run(self, ctx: Any, *, handler: Any) -> Any:
        from code_puppy.messaging import get_message_bus

        bus = get_message_bus()
        bus.push_tool_output_quiet()
        try:
            return await handler()
        finally:
            bus.pop_tool_output_quiet()


def build_speculative_code_mode(agent: Any, agent_tools: Sequence[str]) -> List[Any]:
    """Build the speculative CodeMode capabilities for an opted-in agent, else ``[]``.

    Returned as a list so the caller can splice it into ``capabilities=[...]``
    unconditionally. ``tools='all'`` folds the agent's whole tool surface into
    ``run_code``; ``speculate`` stays restricted to the read-only trio the
    agent actually declares, so a tool added to an opted-in agent later is
    sandboxed but never launched early without showing up here first.
    """
    # Identity check, not truthiness: the opt-in is an explicit class-level
    # `True`, and duck-typed agent stand-ins (tests, plugins) with permissive
    # `__getattr__` must not opt in by accident.
    if getattr(agent, "speculative_code_mode", False) is not True:
        return []
    if not get_speculative_code_mode_enabled():
        return []
    speculate = [name for name in SANDBOXED_READ_ONLY_TOOLS if name in agent_tools]
    workspace = os.getcwd()
    return [
        CodeMode(
            tools="all",
            speculate=speculate,
            # The workspace under its real path, so absolute paths in
            # prompts and snippets need no translation.
            mount=MountDir(
                virtual_path=workspace, host_path=workspace, mode="read-write"
            ),
            # Isolated env + in-memory scratch files + host clock.
            os_access=OSAccess(),
        ),
        SilenceToolOutput(),
    ]
