"""Speculative CodeMode capability: read-only tools in a sandbox that runs ahead of decode.

Dogfoods speculative programmatic tool calling (sPTC) from
https://github.com/pydantic/pydantic-ai-harness/pull/699 (design notes in
pydantic-ai-notes#14, idea from https://alexzhang13.github.io/blog/2026/spec-ptc/).

Only the read-only file tools are folded into ``run_code``:

* they are side-effect free, which is the safety contract ``speculate`` requires
  (an early launch may run for a branch the snippet never takes, so repeating or
  discarding one must be harmless);
* they are the calls whose latency actually overlaps decode in practice -- the
  model writes ``grep(...)`` / ``read_file(...)`` chains with literal arguments
  it has already decided on, hundreds of tokens before the snippet completes.

Write tools, the shell, and sub-agent invocation stay native: models are trained
on direct tool calls for single actions, and none of them are safe to launch
speculatively anyway.
"""

from __future__ import annotations

from typing import Any, List, Sequence

from pydantic_ai_harness.code_mode import CodeMode

from code_puppy.config import get_speculative_code_mode_enabled

# The read-only trio: pure with respect to the workspace, safe to re-run or discard.
SANDBOXED_READ_ONLY_TOOLS = ("list_files", "read_file", "grep")


def build_speculative_code_mode(agent_tools: Sequence[str]) -> List[CodeMode[Any]]:
    """Build the speculative CodeMode capability, or ``[]`` when it doesn't apply.

    Returned as a list so the caller can splice it into ``capabilities=[...]``
    unconditionally. Only tools the agent actually declares are folded, and an
    agent with none of the read-only trio gets no ``run_code`` tool at all.
    """
    if not get_speculative_code_mode_enabled():
        return []
    sandboxed = [name for name in SANDBOXED_READ_ONLY_TOOLS if name in agent_tools]
    if not sandboxed:
        return []
    return [CodeMode(tools=sandboxed, speculate=sandboxed)]
