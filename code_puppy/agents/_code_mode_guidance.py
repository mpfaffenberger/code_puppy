"""Model-facing instructions for working inside speculative CodeMode.

Attached as a capability so any agent running with the mode on receives
the same guidance. Deliberately not routed through i18n: translating a
system prompt changes model behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.tools import ToolDefinition

RUN_CODE_TOOL_NAME = "run_code"

CODE_MODE_GUIDANCE = """\
Code mode is on. Tools exposed directly in your tool list are native:
call them outside `run_code`, not as sandbox functions. These include
`create_file`, `replace_in_file`, `load_image_for_analysis`, screenshot-returning
Computer Use tools when registered, and plugin tools declaring native routing.
Every other tool is an async Python function inside `run_code`, a persistent
sandboxed Python REPL. Native routing does not bypass consent or permissions
and does not authorize speculative execution.

## Write programs, not single calls

Each `run_code` call is a full model round trip: slow, and it resends the
whole conversation. Tool calls INSIDE a snippet are nearly free. So plan the
work in a few steps and spend ONE `run_code` per step, with as many tool
calls inside it as the step needs (5, 10, 30 is normal):

- Batch: fetch everything a step needs in one snippet. Read every file you
  might need, not just the one you are sure of. A snippet wrapping a single
  tool call is almost always a wasted round trip.
- Chain: feed one call's result straight into the next (grep, then read the
  hits, then extract the lines that matter). Do not stop to eyeball an
  intermediate result that code can process.
- Loop: iterate over search hits or file lists and call tools per item, or
  fan out with `await asyncio.gather(...)` (positional awaitables only; no
  other task-creation APIs exist in the sandbox).
- Filter in code: inside the sandbox, tool results are full Python values
  (dicts and lists, not truncated). Slice, regex, count and compare them in
  Python and return only the compact facts you need. When code computes an
  answer (a count, a match), return the matched lines next to it so you can
  check the filter missed nothing; a too-narrow regex fails silently.
- Absorb errors: wrap calls that may fail in `try`/`except` and record the
  error, so one bad path does not cost a round trip.
- Never spend a `run_code` just to print a variable: state persists between
  snippets, so use what you already hold in the next real step.

Single-call snippets to stop writing, and what to write instead:

- `list_files` alone as an opener. Open with the listing PLUS a grep for
  every name or term in the task PLUS reads of the files those terms point
  at, all in one snippet.
- One ranged `read_file` to peek at a region. Read the whole file once, or
  every region you need, and slice the lines in Python.
- One `shell` running the tests. Run the tests AND re-read or grep the code
  you just changed in the same snippet, so a failure comes back with the
  context to fix it.

One snippet that locates, reads and summarizes:

    import asyncio
    hits = await grep(search_string=r"class \\w+\\(.*BaseHandler")
    files = sorted({m["file_path"] for m in hits["matches"] if m["file_path"]})
    srcs = await asyncio.gather(*[read_file(file_path=f) for f in files])
    raised = await grep(search_string=r"raise \\w+Error")
    {
        "subclasses": [m["line_content"].strip() for m in hits["matches"]],
        "sizes": {f: len(s["content"] or "") for f, s in zip(files, srcs)},
        "raise_sites": len(raised["matches"]),
    }

And one that tests and, on failure, pulls the failing source in the same call:

    import re
    r = await shell(command="python -m pytest -x -q", timeout=300)
    tail = (r["stdout"] or "")[-3000:]
    out = {"exit": r["exit_code"], "tail": tail}
    for f in sorted(set(re.findall(r"([\\w/]+\\.py):\\d+", tail)))[:3]:
        out[f] = ((await read_file(file_path=f))["content"] or "")[:4000]
    out

The snippet's final expression is its return value; prefer a compact dict
over printing large blobs. Oversized `run_code` output is spilled to a handle.

## Sandbox facts

- The workspace is mounted read-write (mount path at the end of these
  instructions): `pathlib.Path` with absolute paths under the mount can
  read, write, `iterdir` and stat project files directly. Relative paths
  do not resolve inside the sandbox.
- Snippets are type-checked before they run, against the result types in
  the function signatures below. Fields typed `str | None` (`content`,
  `file_path`, `stdout`, ...) must be narrowed first: `(r["content"] or "")`,
  or `if m["file_path"]` in a comprehension. Results also carry an `error`
  field: check it (or return it) instead of letting `or ""` hide a failure.
- NOT available: `Path.glob`, `Path.rglob`, `os.walk`, `sys.path`,
  `subprocess`, `importlib`, `ast` and third-party packages. Discover
  files with `list_files` / `grep`, run processes with the shell tool.
- Generator expressions evaluate to lists, so `next(x for x in ...)` raises
  TypeError: write `next(iter([x for x in ...]), None)` instead.
- Environment variables (isolated), in-memory scratch files, and the real
  clock (`time` module) work.
- There is NO network in the sandbox: anything remote goes through a
  function like `shell` (e.g. `curl`) or an agent.
- Use raw Python strings for regex patterns so backslashes are not invalid
  escapes.
- Multi-line shell input (heredocs, inline scripts): pass the whole command
  as ONE triple-quoted string, e.g.
  `await shell(command=\"\"\"python - <<'PY'` ... `PY\"\"\")`. A heredoc split
  across ordinary quoted lines is a SyntaxError.

## Speculation (a bonus, not a rule)

Read calls (`list_files`, `read_file`, `grep`) whose keyword arguments are
all literal start running while you are still writing the snippet, so put
the reads you already know you need first, one per line. Loops and computed
arguments are still fine: one extra round trip costs far more than
speculation can save.

Writes and shell commands never speculate, but eager execution can run them
as soon as their statement closes, before generation ends. Obtain required
approval BEFORE emitting a side-effectful statement; later code cannot undo
it. Read before you write, and verify after you change.
"""


# Appended to the harness-owned `run_code` description: the model rereads a
# tool's description at the moment it decides how to call it.
RUN_CODE_BATCHING_NOTE = """

Write a program, not a single call: every `run_code` call costs a full model
round trip, while tool calls inside one snippet are nearly free. Batch, chain
and loop over as many tool calls as the current step needs in ONE snippet,
filter their results in Python, and return only the compact facts."""


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

    def get_instructions(self) -> str:
        return CODE_MODE_GUIDANCE + mount_note(self.host_path, self.mount_path)

    async def prepare_tools(
        self, ctx: RunContext[object], tool_defs: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        return [
            replace(
                tool_def,
                description=(tool_def.description or "") + RUN_CODE_BATCHING_NOTE,
            )
            if tool_def.name == RUN_CODE_TOOL_NAME
            else tool_def
            for tool_def in tool_defs
        ]
