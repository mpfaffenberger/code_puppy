"""Keep ``run_code`` from spending its retry budget on failures a retry cannot fix.

The sandbox has no ``subprocess``, no ``os.system``/``os.popen`` and no
``socket``: importing or calling them fails the same way on every attempt. The
harness reports each runtime error as a ``ModelRetry``, so a model that
resends the snippet exhausts ``run_code``'s retries and the whole run dies with
``UnexpectedModelBehavior``. :class:`RunCodeRedirect` wraps CodeMode's toolset
and

* appends a redirect to a missing-module retry, naming the tool that can do the
  job (the shell tool for processes and ``curl``), and
* answers a *repeated* failure -- the same missing module, or the same snippet
  failing with the same error -- with ``ToolFailed``: the model sees a final
  result, and the retry budget is not charged.

Redirects are capped per run, so a model that ignores them still runs out of
retries instead of looping until the usage limits stop it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, CapabilityOrdering
from pydantic_ai.exceptions import ModelRetry, ToolFailed
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool, WrapperToolset
from pydantic_ai_harness.code_mode import CodeMode

from code_puppy.agents._code_mode_guidance import RUN_CODE_TOOL_NAME

SHELL_TOOL_NAME = "agent_run_shell_command"

# Repeated failures answered with ``ToolFailed`` per run. ``ToolFailed`` is not
# charged to the retry budget, so the cap is what keeps the loop bounded.
MAX_REDIRECTS = 2

_PROCESS_MODULES = frozenset({"subprocess", "multiprocessing", "pty"})
_PROCESS_OS_FUNCTION = re.compile(
    r"system|popen|startfile|kill|fork\w*|spawn\w*|exec\w*"
)
_NETWORK_MODULES = frozenset(
    {
        "aiohttp",
        "ftplib",
        "http",
        "httpx",
        "requests",
        "smtplib",
        "socket",
        "ssl",
        "urllib",
        "urllib3",
        "websockets",
    }
)
_MISSING_MODULE = re.compile(r"ModuleNotFoundError: No module named '([\w.]+)'")
_MISSING_OS_ATTRIBUTE = re.compile(
    r"AttributeError: module 'os' has no attribute '(\w+)'"
)
# Monty numbers each feed (``<python-input-3>``), so tracebacks of the same code differ.
_FEED_NAME = re.compile(r"<python-input-\d+>")

_REPEAT_NOTE = (
    "This is the same failure as an earlier `run_code` call in this run, so it "
    "was not retried. Change the approach instead of resending the code."
)


def missing_name(message: str) -> str | None:
    """The module or ``os.<function>`` a sandbox error reports missing, else ``None``."""
    if module := _MISSING_MODULE.search(message):
        return module.group(1).split(".")[0]
    if function := _MISSING_OS_ATTRIBUTE.search(message):
        return f"os.{function.group(1)}"
    return None


def redirect_hint(name: str, shell_tool: str | None) -> str:
    """Tell the model that ``name`` will never exist and what to use instead."""
    is_process = name in _PROCESS_MODULES or (
        name.startswith("os.") and _PROCESS_OS_FUNCTION.fullmatch(name[3:]) is not None
    )
    if shell_tool is None:
        how = (
            "This agent has no shell tool: do the work with the tools you have, "
            "or tell the user which command to run."
        )
    elif is_process:
        how = f'Run the command with `await {shell_tool}(command="...")` instead.'
    elif name in _NETWORK_MODULES:
        how = (
            f'There is no network: use `curl` via `await {shell_tool}(command="...")`.'
        )
    else:
        how = (
            "Use the tool functions (`read_file`, `grep`, `list_files`) or "
            f'`await {shell_tool}(command="...")` instead.'
        )
    return (
        f"`{name}` does not exist in the `run_code` sandbox, so this code fails "
        f"the same way every time. {how} Do not resend the same code."
    )


@dataclass
class _Failures:
    """``run_code`` failures seen this run, shared by every step's toolset copy."""

    seen: set[tuple[str, str]] = field(default_factory=set)
    redirects: int = 0

    def answer(self, code: str, message: str, shell_tool: str | None) -> Exception:
        """The exception to raise for a failed ``run_code`` call."""
        name = missing_name(message)
        # A missing module fails whatever else the snippet does; any other error
        # only repeats deterministically for the same code.
        key = (
            ("missing", name)
            if name
            else (" ".join(code.split()), _FEED_NAME.sub("<feed>", message))
        )
        if name is not None:
            message = f"{message}\n\n{redirect_hint(name, shell_tool)}"
        if key in self.seen and self.redirects < MAX_REDIRECTS:
            self.redirects += 1
            return ToolFailed(f"{message}\n\n{_REPEAT_NOTE}")
        self.seen.add(key)
        return ModelRetry(message)


@dataclass
class _RunCodeRedirectToolset(WrapperToolset[Any]):
    shell_tool: str | None = None
    # A field, not ``init=False`` state: ``for_run_step`` copies this toolset
    # with ``replace``, and every copy must share the run's failure record.
    failures: _Failures = field(default_factory=_Failures)

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        try:
            return await super().call_tool(name, tool_args, ctx, tool)
        except ModelRetry as error:
            if name != RUN_CODE_TOOL_NAME:
                raise
            code = tool_args.get("code")
            raise self.failures.answer(
                code if isinstance(code, str) else "", error.message, self.shell_tool
            ) from error


@dataclass
class RunCodeRedirect(AbstractCapability[Any]):
    """Redirect ``run_code`` failures a retry cannot fix (see module docstring)."""

    shell_tool: str | None = None

    def get_ordering(self) -> CapabilityOrdering:
        # Outside CodeMode, so its ``run_code`` retries pass through this wrapper.
        # CodeMode pins itself outermost; ``wraps`` alone would form a cycle.
        return CapabilityOrdering(position="outermost", wraps=[CodeMode])

    def get_wrapper_toolset(
        self, toolset: AbstractToolset[Any]
    ) -> AbstractToolset[Any]:
        # Called per run, so each run starts with an empty failure record.
        return _RunCodeRedirectToolset(wrapped=toolset, shell_tool=self.shell_tool)
