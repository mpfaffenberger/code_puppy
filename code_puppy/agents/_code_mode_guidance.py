"""Model-facing instructions for working inside speculative CodeMode.

Attached as a capability so any agent running with the mode on receives
the same guidance. Deliberately not routed through i18n: translating a
system prompt changes model behavior.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.capabilities import AbstractCapability

CODE_MODE_GUIDANCE = """\
Speculative execution is on. Use `create_file` and `replace_in_file` as
native tools, outside `run_code`; they are not available as functions inside
the sandbox. Every other tool is an async function inside `run_code`, a
persistent sandboxed Python REPL. Call `run_code` with a Python snippet to
use them; do not attempt to call those functions as native tools.

The sandbox also has direct capabilities, no function call needed:

- The workspace is mounted read-write at its real absolute path: use
  `pathlib.Path` to read, write, glob, and stat project files directly.
- Environment variables (isolated), in-memory scratch files, and the real
  clock (`time` module) work.
- There is NO network in the sandbox: anything remote goes through a
  function like `shell` (e.g. `curl`) or an agent.

Use raw Python strings for regex patterns so backslashes are not invalid escapes.

How to work. The runtime watches your code AS YOU WRITE IT and starts
eligible calls before the snippet is finished, so the SHAPE of your code
determines how fast it runs:

1. Emit small, flat statements, one per line. A read call (`list_files`,
   `read_file`, `grep`) starts executing the moment its line is complete,
   when its call has all-literal keyword arguments:

       hits = await grep(search_string="SpeculationState")
       src = await read_file(file_path="code_puppy/agents/_code_mode.py")

   Each such line runs while you are still writing the lines below it.
   Computing arguments forfeits that speculative head start. Literal
   calls can also be detected inside expressions or across multiple lines.
2. Go BIG in one `run_code` call. Do not split work across many small
   snippets: every extra round trip to the model wastes the runway that
   makes early execution pay. 60-100 lines with ten, twenty, thirty tool
   calls in a single snippet is not just fine, it is the fast path --
   every additional literal read line is another call already running
   while you write the lines below it, and the longer the snippet, the
   more of that work finishes before execution even starts.
3. Front-load the reads: open every snippet with the literal read lines,
   one per line, then process the results with plain Python below them.
   Cast a wide net up front -- read the files you MIGHT need, not just
   the one you are sure of; an unused result costs nothing you were not
   already spending on generation.
4. Never introduce a variable just to pass it: `q = "x"` followed by
   `grep(search_string=q)` runs cold; `grep(search_string="x")` runs
   early. Repeat the literal even if it feels less DRY -- here, DRY
   loses to speed.
5. Writes and shell commands never speculate, but eager execution can
   execute them as soon as their statements close, before generation ends.
   Obtain required approval BEFORE emitting a side-effectful statement;
   later code cannot undo it. Run independent calls concurrently with
   `await asyncio.gather(...)` (positional awaitables only; no other
   task-creation APIs exist in the sandbox).
6. Keep mutable state small and local: assign results to short fresh
   names, keep processing blocks brief, and never rebind a name a
   pending call's line already used. `print(...)` what matters and make
   the snippet's final expression the value you want returned.
7. State persists between snippets within a run -- variables and
   functions carry over. Do not re-fetch what you already hold. Prefer
   the read functions over `pathlib` for discovery (they start early);
   use `pathlib` for surgical follow-ups on paths you already hold.
8. Read before you write, and verify after you change: re-read the file
   or run the tests in a follow-up snippet.
"""


class CodeModeGuidance(AbstractCapability[Any]):
    """Teach the model the fast-path snippet shape when the mode is on."""

    def get_instructions(self) -> str:
        return CODE_MODE_GUIDANCE
