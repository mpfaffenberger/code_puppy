"""Speculative CodeMode capability wiring for agents that opt in.

Dogfoods speculative programmatic tool calling (sPTC) from
https://github.com/pydantic/pydantic-ai-harness/pull/699 (design notes in
pydantic-ai-notes#14, idea from https://alexzhang13.github.io/blog/2026/spec-ptc/).

This is deliberately not wired into every agent. An agent opts in by setting
``speculative_code_mode = True`` (see ``BaseAgent``), which asserts that its
entire tool surface is side-effect free -- the safety contract speculation
requires, since an early launch may run for a branch the snippet never takes.
For an opted-in agent, ALL of its tools fold into the single ``run_code``
sandbox (the model sees no native tools at all -- the RLM shape), and the
read-only file tools additionally speculate.

The Monty agent (``agent_monty.py``) is the resident example; everything else
keeps ordinary native tool calls, where models are strongest for single
actions.
"""

from __future__ import annotations

from typing import Any, List, Sequence

from pydantic_ai_harness.code_mode import CodeMode

from code_puppy.config import get_speculative_code_mode_enabled

# The read-only trio: pure with respect to the workspace, safe to re-run or discard.
SANDBOXED_READ_ONLY_TOOLS = ("list_files", "read_file", "grep")


def build_speculative_code_mode(
    agent: Any, agent_tools: Sequence[str]
) -> List[CodeMode[Any]]:
    """Build the speculative CodeMode capability for an opted-in agent, else ``[]``.

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
    return [CodeMode(tools="all", speculate=speculate)]
