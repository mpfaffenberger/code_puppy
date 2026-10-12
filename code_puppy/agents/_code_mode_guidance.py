"""Model-facing instructions for working inside speculative CodeMode.

Attached as a capability so any agent running with the mode on receives
the same guidance. Deliberately not routed through i18n: translating a
system prompt changes model behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic_ai.capabilities import AbstractCapability

RUN_CODE_TOOL_NAME = "run_code"

CODE_MODE_GUIDANCE = """\
Code mode is on. Tools in your tool list are native: call them directly, not
inside `run_code`. These include `create_file`, `replace_in_file`,
`load_image_for_analysis`, screenshot-returning Computer Use tools when
registered, and plugin tools declaring native routing. Every other tool is an
async function inside `run_code`. Native routing does not bypass consent or
permissions and does not authorize speculative execution.

## Write programs, not single calls

Each `run_code` call is a model round trip that resends the conversation; tool
calls inside a snippet are nearly free. Spend ONE `run_code` per step of the
work, with every tool call that step needs:

- Batch: open with the listing PLUS a grep for every term in the task PLUS reads
  of the files they point at. Read whole files once and slice in Python rather
  than peeking at ranges. Run tests AND re-read the code you changed together.
- Chain and loop: feed results into the next call; fan out with
  `await asyncio.gather(...)` after `import asyncio` (modules are never
  preloaded; positional awaitables only).
- Filter in code: results are full Python values. Return compact facts, plus
  the matched lines behind any count so a too-narrow regex cannot hide misses.
- Absorb errors with `try`/`except` so one bad path does not cost a round trip.

    import asyncio
    hits = await grep(search_string=r"class \\w+\\(.*BaseHandler")
    files = sorted({f for m in hits["matches"] if (f := m["file_path"])})
    srcs = await asyncio.gather(*[read_file(file_path=f) for f in files])
    {f: (s["content"] or "")[:2000] for f, s in zip(files, srcs)}

## Sandbox facts

- The workspace is mounted read-write at the path given at the end of these
  instructions; `pathlib` needs absolute paths under it (relative paths do not
  resolve). NOT available: `Path.glob`/`rglob`, `os.walk`, `sys.path`,
  `subprocess`, `importlib`, `ast`, third-party packages, network. Use
  `list_files`/`grep`, and the shell function for processes and `curl`.
- Snippets are type-checked. Narrow `str | None` result fields by binding them
  once: `if (f := m["file_path"])` then use `f`, or `(r["content"] or "")`.
  Filtering on `m.get("x")` but using `m["x"]` does not narrow. Check the
  `error` field rather than letting `or ""` hide a failure.
- Generator expressions are lists: `next(x for x in ...)` raises; use
  `next(iter([...]), None)`. Use raw strings for regexes. Pass multi-line shell
  input (heredocs) as ONE triple-quoted string.
- Reads whose arguments are all literals start running while you write
  (speculation); loops and computed arguments are still fine. Writes and shell commands can run as soon
  as their statement closes: obtain approval BEFORE emitting them.
"""


def mount_note(host_path: str, mount_path: str) -> str:
    """Where the workspace lives in the sandbox, spelled out for the model."""
    if mount_path == host_path:
        return f"\nWorkspace mount: `{mount_path}` (same as the host path).\n"
    return (
        f"\nWorkspace mount: `{mount_path}` is the host directory `{host_path}`.\n"
        "Tool functions (`read_file`, `grep`, shell, ...) take host paths;\n"
        "`pathlib` inside the sandbox takes mount paths.\n"
    )


@dataclass
class CodeModeGuidance(AbstractCapability[Any]):
    """Teach the model the fast-path snippet shape when the mode is on."""

    host_path: str
    mount_path: str

    def get_instructions(self) -> list[str | Callable[[], str]]:
        # The guidance is a static instruction part and the workspace path a dynamic one:
        # pydantic-ai puts the Anthropic cache breakpoint after the last static part, so
        # the guidance stays cached across sessions and directories (every new worktree
        # or sub-agent would otherwise re-write it to the cache at a premium).
        return [CODE_MODE_GUIDANCE, self._mount_note]

    def _mount_note(self) -> str:
        return mount_note(self.host_path, self.mount_path)
