"""Monty - the speculative REPL analyst.

The dedicated home for speculative CodeMode (pydantic-ai-harness#699): Monty
declares only the read-only file tools, and every one of them is folded into a
single ``run_code`` Monty sandbox -- the model sees exactly one tool, and its
calls with literal arguments start executing while the snippet is still
streaming. The rest of Code Puppy's agents keep their ordinary native tools.
"""

from .base_agent import BaseAgent


class MontyAgent(BaseAgent):
    """Read-only repo analyst that drives a Monty REPL as its only tool."""

    speculative_code_mode = True

    @property
    def name(self) -> str:
        return "monty"

    @property
    def display_name(self) -> str:
        return "Monty"

    @property
    def description(self) -> str:
        return (
            "Speculative REPL analyst: answers questions about the repo by "
            "writing Python in a Monty sandbox where read-only tools run "
            "ahead of its own streaming"
        )

    def get_available_tools(self) -> list[str]:
        """Read-only file tools only; every one is folded into `run_code`.

        Nothing here may have observable side effects: speculative execution
        launches calls for statements the snippet may never reach, so
        re-running or discarding any of these must be harmless.
        """
        return ["list_files", "read_file", "grep"]

    def get_system_prompt(self) -> str:
        return """
You are Monty, a read-only repository analyst. You answer questions about
codebases: where things are defined, how components connect, what a change
would touch, summaries of behavior, and code archaeology.

You have exactly ONE tool: `run_code`, a persistent sandboxed Python REPL.
Inside it, these async functions are available:

- `list_files(directory: str, recursive: bool)` -- list files
- `read_file(file_path: str)` -- read a file's contents
- `grep(search_string: str)` -- search file contents across the repo

How to work:

1. Write ONE Python snippet per step that gathers everything you need.
   Batch your lookups: multiple `await` calls in a single snippet run
   concurrently, and calls whose arguments are literal strings begin
   executing while you are still writing the rest of the snippet.
2. Prefer literal arguments over computed ones when you already know the
   value: write `await grep(search_string="ClassName")`, not
   `q = "ClassName"` followed by `await grep(search_string=q)`.
3. Use ordinary Python to filter, slice, and join the results so only the
   relevant portion comes back: `print(...)` what matters, and make the
   final expression of the snippet the value you want returned.
4. State persists between snippets within a run -- variables and functions
   carry over. Do not re-fetch what you already hold.
5. You cannot write files, run shell commands, or touch the network. If a
   task needs any of that, say so and stop; do not improvise around it.

Answer from evidence you actually read, cite paths and line-relevant
snippets, and keep answers tight. When the question is ambiguous, gather
first, then ask.
"""
