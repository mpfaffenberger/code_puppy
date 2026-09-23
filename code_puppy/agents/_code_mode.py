"""Speculative CodeMode capability wiring, switched by one config flag.

Uses speculative programmatic tool calling from pydantic-ai-harness 0.33.0.

When ``enable_speculative_code_mode`` is on, every agent (main and sub-agent)
has its whole tool surface, MCP servers and plugin tools included, folded
into ``run_code`` except ``create_file`` and ``replace_in_file``, which
remain native. Only the read-only trio below speculates. That allowlist is
the safety contract: an early launch may run for a branch the snippet never
takes, so it is reserved for calls that are harmless to re-run or discard;
everything else waits for real execution.

The sandbox is not fully sealed either: the workspace mounts read-write so
snippets can drive real project files through ``pathlib`` directly, and an
`OSAccess` handler provides isolated environment variables, the host clock,
and in-memory scratch files. Network stays tool-shaped: there is no socket in
the sandbox, so anything remote goes through a wrapped tool, which is also
the FFI story -- any host Python function CodeMode wraps becomes an async
function inside the snippet.

With the flag off, agents keep ordinary native tool calls, where models are
strongest for single actions. ``Ctrl+X Ctrl+S`` flips the flag and rebuilds
the current agent.
"""

from __future__ import annotations

import os
import warnings
from typing import Any, List, Sequence

import pydantic_ai
from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.tools import ToolDefinition
from pydantic_monty import MountDir, OSAccess

from pydantic_ai_harness.code_mode import CodeMode

from code_puppy.agents._code_mode_guidance import CodeModeGuidance
from code_puppy.agents._wire_tool_names import StreamedToolNameNormalizer
from code_puppy.capabilities.eager_timing import EagerTiming
from code_puppy.config import get_speculative_code_mode_enabled

# Code Puppy owns terminal output, including when observability is disabled.
pydantic_ai.BANNER_ENABLED = False

# Streaming AST probes repeatedly warn about the same generated string literal.
warnings.filterwarnings(
    "ignore",
    message=r".*is an invalid escape sequence.*",
    category=SyntaxWarning,
    module=r"^<unknown>$",
)

# The read-only trio: pure with respect to the workspace, safe to re-run or discard.
SANDBOXED_READ_ONLY_TOOLS = ("list_files", "read_file", "grep")


def _sandbox_tool(ctx: RunContext[object], tool_def: ToolDefinition) -> bool:
    """Keep file creation and replacement available as native tools."""
    return tool_def.name not in {"create_file", "replace_in_file"}


class SilenceToolOutput(AbstractCapability[Any]):
    """Suppress TOOL_OUTPUT bus messages for the duration of the run.

    Most tools in a speculative CodeMode run execute within `run_code`:
    its UI rendering (file dumps, grep boxes, shell lines) would repeat what
    the snippet already filters and returns. The pinned speculation row and the
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


def build_speculative_code_mode(agent_tools: Sequence[str]) -> List[Any]:
    """Build the speculative CodeMode capabilities when the flag is on, else ``[]``.

    Returned as a list so the caller can splice it into ``capabilities=[...]``
    unconditionally. Creation and replacement stay native; all other tools fold
    into ``run_code``. ``speculate`` stays restricted to the read-only trio the
    agent actually declares, so a tool added to an agent later is sandboxed but
    never launched early without showing up here first.
    """
    if not get_speculative_code_mode_enabled():
        return []
    speculate = [name for name in SANDBOXED_READ_ONLY_TOOLS if name in agent_tools]
    workspace = os.getcwd()
    return [
        CodeMode(
            tools=_sandbox_tool,
            speculate=speculate,
            # Composed tiers: eager runs each streamed statement in the live REPL as it
            # closes (a blocking shell command starts mid-generation), while speculation
            # launches the read-only calls beyond the execution frontier and the eager
            # feeds claim them.
            eager=True,
            # The workspace under its real path, so absolute paths in
            # prompts and snippets need no translation.
            mount=MountDir(
                virtual_path=workspace, host_path=workspace, mode="read-write"
            ),
            # Isolated env + in-memory scratch files + host clock.
            os_access=OSAccess(),
        ),
        SilenceToolOutput(),
        EagerTiming(),
        StreamedToolNameNormalizer(),
        CodeModeGuidance(),
    ]
