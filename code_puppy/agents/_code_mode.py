"""Speculative CodeMode capability wiring, switched by one config flag.

Uses speculative programmatic tool calling from pydantic-ai-harness 0.33.0.

When ``enable_speculative_code_mode`` is on, every agent (main and sub-agent)
has its whole tool surface, MCP servers and plugin tools included, folded
into ``run_code`` except the ``NATIVE_TOOLS`` below, which remain native.
Only the read-only trio below speculates. That allowlist is
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
from pathlib import PureWindowsPath
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
# Python 3.12+ raises these as SyntaxWarning ("... is an invalid escape
# sequence"); 3.11 uses DeprecationWarning ("invalid escape sequence '...'").
for _invalid_escape_category in (SyntaxWarning, DeprecationWarning):
    warnings.filterwarnings(
        "ignore",
        message=r".*invalid escape sequence.*",
        category=_invalid_escape_category,
        module=r"^<unknown>$",
    )

# MCP servers routinely ship tools without an output schema (Blender's
# screenshot tools, for one); the sandbox signature just degrades to
# ``-> Any``. Nothing the user can act on, so keep it off the terminal. The
# harness's name-collision warning is actionable and stays visible.
warnings.filterwarnings(
    "ignore",
    message=r"CodeMode: tool .* has no return schema",
    category=UserWarning,
)

# The read-only trio: pure with respect to the workspace, safe to re-run or discard.
# Speculated even before an agent is bound (see DeclaredSpeculation).
SANDBOXED_READ_ONLY_TOOLS = ("list_files", "read_file", "grep")

# Tools opt into early launch themselves, core and plugin alike:
#     @agent.tool(metadata={"speculatable": True})
SPECULATABLE_METADATA_KEY = "speculatable"


class DeclaredSpeculation(Sequence[str]):
    """CodeMode's speculation allowlist, resolved from the agent's own tools.

    CodeMode is constructed before tools are registered, and plugin tools
    (``register_agent_tools``) never appear in ``get_available_tools()``, so no
    name list known at construction can cover them. CodeMode freezes
    ``frozenset(speculate)`` at each run start (``for_run``); resolving then
    sees every registered tool that declares ``speculatable: True``.

    Until :meth:`bind` it yields only the declared read-only trio, so an
    unbound instance behaves exactly as the old fixed list did.
    """

    def __init__(self, fallback: Sequence[str]) -> None:
        self._fallback = tuple(fallback)
        self._agent: Any = None

    def bind(self, agent: Any) -> None:
        self._agent = agent

    def _names(self) -> tuple[str, ...]:
        names = dict.fromkeys(self._fallback)
        for toolset in getattr(self._agent, "toolsets", None) or ():
            for name, tool in (getattr(toolset, "tools", None) or {}).items():
                metadata = getattr(tool, "metadata", None) or {}
                # Literal True only: a truthy stand-in is not a declaration.
                if metadata.get(SPECULATABLE_METADATA_KEY) is True:
                    names[name] = None
        return tuple(names)

    def __getitem__(self, index):  # type: ignore[override]
        return self._names()[index]

    def __len__(self) -> int:
        return len(self._names())

    def __iter__(self):
        return iter(self._names())

    def __repr__(self) -> str:
        return f"DeclaredSpeculation({list(self)!r})"


def bind_declared_speculation(pydantic_agent: Any) -> None:
    """Point this agent's CodeMode allowlist at the agent's registered tools.

    Call after ``register_tools_for_agent``. No-op when speculative mode is
    off (no CodeMode) or the allowlist is not a :class:`DeclaredSpeculation`.
    """

    def leaves(capability: Any):
        children = getattr(capability, "capabilities", None)
        if children is None:
            yield capability
            return
        for child in children:
            yield from leaves(child)

    for capability in leaves(getattr(pydantic_agent, "root_capability", None)):
        speculate = getattr(capability, "speculate", None)
        if isinstance(capability, CodeMode) and isinstance(
            speculate, DeclaredSpeculation
        ):
            speculate.bind(pydantic_agent)


# Never folded into run_code. File writes stay native so edits render as diffs;
# load_image_for_analysis stays native because its multimodal ToolReturn must
# reach the model as real image content, which a sandbox value cannot carry.
NATIVE_TOOLS = frozenset({"create_file", "replace_in_file", "load_image_for_analysis"})


def _sandbox_tool(ctx: RunContext[object], tool_def: ToolDefinition) -> bool:
    """Fold every tool into ``run_code`` except the ``NATIVE_TOOLS``."""
    return tool_def.name not in NATIVE_TOOLS


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


def sandbox_mount_path(host_path: str) -> str:
    """Where ``host_path`` appears inside the sandbox.

    Monty's virtual filesystem is POSIX-only and rejects ``C:\\...`` outright,
    so Windows paths get the Git Bash spelling every model already knows:
    ``C:\\Users\\x`` -> ``/c/Users/x``, ``\\\\srv\\share\\x`` -> ``/srv/share/x``.
    POSIX paths pass through untouched.
    """
    if host_path.startswith("/"):
        return host_path
    posix = PureWindowsPath(host_path).as_posix()
    drive, colon, rest = posix.partition(":/")
    if colon:
        return f"/{drive.lower()}/{rest}".rstrip("/")
    return "/" + posix.lstrip("/")


def build_speculative_code_mode(agent_tools: Sequence[str]) -> List[Any]:
    """Build the speculative CodeMode capabilities when the flag is on, else ``[]``.

    Returned as a list so the caller can splice it into ``capabilities=[...]``
    unconditionally. ``NATIVE_TOOLS`` stay native; all other tools fold into
    ``run_code``. Only tools that declare ``speculatable: True`` are launched
    early; call :func:`bind_declared_speculation` once tools are registered.
    A tool without the declaration is sandboxed but never launched early.
    """
    if not get_speculative_code_mode_enabled():
        return []
    speculate = DeclaredSpeculation(
        [name for name in SANDBOXED_READ_ONLY_TOOLS if name in agent_tools]
    )
    workspace = os.getcwd()
    mount_path = sandbox_mount_path(workspace)
    return [
        CodeMode(
            tools=_sandbox_tool,
            speculate=speculate,
            # Composed tiers: eager runs each streamed statement in the live REPL as it
            # closes (a blocking shell command starts mid-generation), while speculation
            # launches the read-only calls beyond the execution frontier and the eager
            # feeds claim them.
            eager=True,
            # The workspace under its real path on POSIX, so absolute paths
            # need no translation; Windows needs a POSIX spelling, which
            # CodeModeGuidance spells out for the model.
            mount=MountDir(
                virtual_path=mount_path, host_path=workspace, mode="read-write"
            ),
            # Isolated env + in-memory scratch files + host clock.
            os_access=OSAccess(),
        ),
        SilenceToolOutput(),
        EagerTiming(),
        StreamedToolNameNormalizer(),
        CodeModeGuidance(host_path=workspace, mount_path=mount_path),
    ]
