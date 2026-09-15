"""
Command execution engine for hooks.

Handles async command execution with timeout, variable substitution,
and comprehensive error handling.

Claude Code Hook Compatibility:
  - Input is passed via STDIN as JSON (primary method, Claude Code standard)
  - Input is also available via CLAUDE_TOOL_INPUT env var (legacy/convenience)
  - Exit code 0  => success, stdout shown in transcript
  - Exit code 1  => block the operation (stderr used as reason)
  - Exit code 2  => error feedback to Claude (stderr fed back as tool error)

Stdout JSON control payloads are also honored (exit code 0 + JSON verdict):
  - Claude Code official: {"decision": "block", "reason": ...} or
    {"hookSpecificOutput": {"permissionDecision": "deny", ...}}
  - Plugin dialect: {"result": "block", "reason": ...}
Control payloads are stripped from stdout so they never leak into model
context; hookSpecificOutput.additionalContext replaces stdout when present.
"""

import asyncio
import json
import logging
import os
import re
import shlex
import time
from typing import Any, Dict, List, Optional, Tuple

from .matcher import _extract_file_path
from .models import EventData, ExecutionResult, HookConfig

logger = logging.getLogger(__name__)


def _build_stdin_payload(event_data: EventData) -> bytes:
    """
    Build the JSON payload sent to hook scripts via stdin.

    Matches the Claude Code hook input format:
    {
        "session_id": "...",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": { ... },
        "cwd": "/path/to/project",
        "permission_mode": "default"
    }
    """

    def _make_serializable(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_make_serializable(v) for v in obj]
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        try:
            return str(obj)
        except Exception:
            return "<unserializable>"

    payload = {
        "session_id": event_data.context.get("session_id", "codepuppy-session"),
        "hook_event_name": event_data.event_type,
        "tool_name": event_data.tool_name,
        "tool_input": _make_serializable(event_data.tool_args),
        "cwd": os.getcwd(),
        "permission_mode": "default",
    }
    if "result" in event_data.context:
        payload["tool_result"] = _make_serializable(event_data.context["result"])
    if "duration_ms" in event_data.context:
        payload["tool_duration_ms"] = event_data.context["duration_ms"]

    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


# Keys that mark a JSON stdout object as a hook *control* payload rather than
# ordinary output. A hook legitimately printing {"foo": "bar"} is untouched.
_CONTROL_KEYS = frozenset(
    {"result", "decision", "reason", "hookSpecificOutput", "continue", "stopReason"}
)


def _interpret_control_payload(
    stdout: str,
    blocked: bool,
    error: Optional[str],
) -> Tuple[str, bool, Optional[str]]:
    """
    Interpret a stdout JSON control payload, if present.

    Honors both dialects (see module docstring). Returns possibly-updated
    (stdout, blocked, error). Plain text, non-control JSON, and exit-code
    semantics are untouched.
    """
    text = stdout.strip()
    if not text.startswith("{"):
        return stdout, blocked, error

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return stdout, blocked, error

    if not isinstance(payload, dict) or not (_CONTROL_KEYS & payload.keys()):
        return stdout, blocked, error

    hook_specific = payload.get("hookSpecificOutput")
    if not isinstance(hook_specific, dict):
        hook_specific = {}

    if (
        payload.get("result") == "block"
        or payload.get("decision") == "block"
        or hook_specific.get("permissionDecision") == "deny"
        or payload.get("continue") is False
    ):
        blocked = True
        reason = (
            payload.get("reason")
            or hook_specific.get("permissionDecisionReason")
            or payload.get("stopReason")
        )
        if reason:
            error = str(reason)

    # Strip the control payload from stdout so it never reaches model
    # context; additionalContext, when present, becomes the hook's output.
    additional_context = hook_specific.get("additionalContext")
    new_stdout = additional_context if isinstance(additional_context, str) else ""
    return new_stdout, blocked, error


async def execute_hook(
    hook: HookConfig,
    event_data: EventData,
    env_vars: Optional[Dict[str, str]] = None,
) -> ExecutionResult:
    """
    Execute a hook command with timeout and variable substitution.

    Input to the hook script:
      - stdin: JSON object (Claude Code compatible format)
      - env CLAUDE_TOOL_INPUT: JSON string of tool_args (legacy)
      - env CLAUDE_PROJECT_DIR: current working directory

    Exit code semantics:
      - 0: success (stdout shown in transcript)
      - 1: block operation (stderr becomes block reason)
      - 2: error feedback to Claude without blocking
    """
    if hook.type == "prompt":
        return ExecutionResult(
            blocked=False,
            hook_command=hook.command,
            stdout=hook.command,
            exit_code=0,
            duration_ms=0.0,
            hook_id=hook.id,
        )

    command = _substitute_variables(hook.command, event_data, env_vars or {})
    stdin_payload = _build_stdin_payload(event_data)
    start_time = time.perf_counter()

    try:
        env = _build_environment(event_data, env_vars)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_payload),
                timeout=hook.timeout / 1000.0,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass

            duration_ms = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                blocked=True,
                hook_command=command,
                stdout="",
                stderr=f"Command timed out after {hook.timeout}ms",
                exit_code=-1,
                duration_ms=duration_ms,
                error=f"Hook execution timed out after {hook.timeout}ms",
                hook_id=hook.id,
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""
        exit_code = proc.returncode or 0

        blocked = exit_code == 1
        error = stderr_str if exit_code != 0 and stderr_str else None
        stdout_str, blocked, error = _interpret_control_payload(
            stdout_str, blocked, error
        )

        return ExecutionResult(
            blocked=blocked,
            hook_command=command,
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=exit_code,
            duration_ms=duration_ms,
            error=error,
            hook_id=hook.id,
        )

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(f"Hook execution failed: {e}", exc_info=True)
        return ExecutionResult(
            blocked=False,
            hook_command=command,
            stdout="",
            stderr=str(e),
            exit_code=-1,
            duration_ms=duration_ms,
            error=f"Hook execution error: {e}",
            hook_id=hook.id,
        )


def _substitute_variables(
    command: str,
    event_data: EventData,
    env_vars: Dict[str, str],
) -> str:
    substitutions = {
        "CLAUDE_PROJECT_DIR": os.getcwd(),
        "tool_name": event_data.tool_name,
        "event_type": event_data.event_type,
        "file": _extract_file_path(event_data.tool_args) or "",
        "CLAUDE_TOOL_INPUT": json.dumps(event_data.tool_args),
    }
    if event_data.context:
        if "result" in event_data.context:
            substitutions["result"] = str(event_data.context["result"])
        if "duration_ms" in event_data.context:
            substitutions["duration_ms"] = str(event_data.context["duration_ms"])
    substitutions.update(env_vars)

    return _interpolate_placeholders(command, substitutions)


_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def _interpolate_placeholders(template: str, values: Dict[str, str]) -> str:
    """Splice ``$var``/``${var}`` values into ``template`` as literal text.

    The shell must never re-interpret a substituted value: each splice is
    made safe in the quoting context the template itself established
    (tracked by scanning only the template's literal segments), and
    substituted values are not re-scanned, so a value containing ``$`` or
    quote characters cannot inject further placeholders, close the author's
    quotes, or run commands in the hook's own shell. Unknown ``$``
    sequences pass through for the shell to expand as the hook author wrote
    them.

    A template that itself invokes a nested interpreter — ``sh -c
    '...${file}...'`` — hands the value to that interpreter as code; no
    quoting at this level can prevent that. Hooks that need untrusted
    values inside evaluation should read them from the provided environment
    (``CLAUDE_FILE_PATH`` et al.) or stdin JSON instead of interpolation.
    """
    if os.name == "nt":
        # Hooks run via cmd /c, where only " groups arguments; POSIX
        # single-quoting is literal text.
        pieces: List[str] = []
        position = 0
        in_quotes = False
        for match in _PLACEHOLDER_RE.finditer(template):
            literal = template[position : match.start()]
            pieces.append(literal)
            in_quotes = _cmd_quote_state(literal, in_quotes)
            position = match.end()

            name = match.group(1) or match.group(2)
            if name not in values:
                pieces.append(match.group(0))
                continue
            value = str(values[name])
            if in_quotes:
                # Already inside the author's double quotes: emit only the
                # inner-quote-escaped value. Adding another "..." here would
                # give a metacharacter even quote parity and re-arm cmd.exe.
                pieces.append(value.replace('"', '""'))
            else:
                pieces.append(_cmd_quote(value))
        pieces.append(template[position:])
        return "".join(pieces)

    pieces = []
    position = 0
    # Stack of shell contexts, each [closer, quote]. The base command sits at
    # the bottom; a $( or backtick pushes a nested command-substitution
    # context (see _scan_quote_stack).
    stack: List[List[Optional[str]]] = [[None, None]]
    for match in _PLACEHOLDER_RE.finditer(template):
        literal = template[position : match.start()]
        pieces.append(literal)
        _scan_quote_stack(literal, stack)
        position = match.end()

        name = match.group(1) or match.group(2)
        if name not in values:
            pieces.append(match.group(0))
            continue
        value = str(values[name])
        quote = stack[-1][1]
        if quote is None:
            piece = shlex.quote(value)
        elif quote == "'":
            # Inside the author's single quotes only a single quote is
            # special: splice each one as close-quote + escaped quote +
            # reopen (''' idiom) so the value stays literal text.
            piece = value.replace("'", "'\\''")
        else:
            piece = _double_quote_escape(value)
        # A raw backtick closes an enclosing `...` command substitution even
        # from inside quotes -- the shell scans for the closer before quote
        # removal, and shlex.quote never escapes it. Escape for every open
        # backtick layer so the value cannot terminate the substitution.
        if any(frame[0] == "`" for frame in stack):
            piece = piece.replace("\\", "\\\\").replace("`", "\\`")
        pieces.append(piece)
    pieces.append(template[position:])
    return "".join(pieces)


def _cmd_quote_state(text: str, in_quotes: bool) -> bool:
    """Track whether a cmd.exe double-quoted string is open across a literal.

    Only ``"`` groups arguments for cmd.exe, so it alone toggles the state.
    """
    for char in text:
        if char == '"':
            in_quotes = not in_quotes
    return in_quotes


# A ``#`` starts a comment only at a word boundary in an unquoted context;
# after an ordinary word character it is a literal ``#``. These are the chars
# that leave the shell expecting a fresh word.
_COMMENT_BOUNDARY = frozenset({" ", "\t", "\n", ";", "&", "|", "(", ")", "<", ">"})


def _scan_quote_stack(text: str, stack: List[List[Optional[str]]]) -> None:
    """Advance the shell context stack across a literal template segment.

    Each frame is ``[closer, quote]``: ``quote`` is the frame's active quote
    (``None``, ``'``, or ``"``) and ``closer`` is the char that ends the frame
    (``)`` for ``$(``, a backtick for ``` `...` ```, or ``None`` for the base
    command). A ``$(`` or backtick opens a command substitution — a fresh
    command context where the value is re-parsed — so it pushes a frame whose
    quote is ``None``. An interpolated value there is therefore quoted as
    unquoted (``shlex.quote``) even though an outer ``"`` is still open, which
    keeps the value an inert argument instead of a live command.
    """
    i = 0
    prev: Optional[str] = None
    while i < len(text):
        char = text[i]
        top = stack[-1]
        quote = top[1]
        if quote is None:
            if char == top[0]:  # matching closer ends this substitution frame
                stack.pop()
            elif char == "#" and (prev is None or prev in _COMMENT_BOUNDARY):
                # A comment runs to end of line; its body -- quote chars
                # included -- is inert, so skip it without disturbing the
                # tracked quote state (an apostrophe in a comment must not flip
                # the scanner into single-quote mode and mis-quote a later
                # placeholder).
                while i < len(text) and text[i] != "\n":
                    i += 1
                prev = "\n"
                continue
            elif char in ("'", '"'):
                top[1] = char
            elif char == "\\":
                i += 1  # escaped character cannot open a quote or substitution
            elif char == "$" and i + 1 < len(text) and text[i + 1] == "(":
                stack.append([")", None])
                i += 1
            elif char == "`":
                stack.append(["`", None])
        elif quote == "'":
            if char == "'":
                top[1] = None
        else:  # inside double quotes: $( and backtick still open substitutions
            if char == "\\":
                i += 1
            elif char == '"':
                top[1] = None
            elif char == "$" and i + 1 < len(text) and text[i + 1] == "(":
                stack.append([")", None])
                i += 1
            elif char == "`":
                stack.append(["`", None])
        prev = char
        i += 1


def _double_quote_escape(value: str) -> str:
    """Escape a value for splicing inside an open double-quoted string."""
    for char, escaped in (("\\", "\\\\"), ('"', '\\"'), ("$", "\\$"), ("`", "\\`")):
        value = value.replace(char, escaped)
    return value


def _cmd_quote(value: str) -> str:
    """Quote a value for cmd.exe.

    Double quotes group and make ``& | < > ( ) ^`` inert; inner quotes are
    doubled. ``%`` cannot be escaped outside batch files, so a value naming
    an existing ``%VAR%`` still expands — text substitution only, never
    command execution, since expansion cannot introduce a closing quote.
    """
    return '"' + value.replace('"', '""') + '"'


def _build_environment(
    event_data: EventData,
    env_vars: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    # Hooks are user-authored config, not model-authored commands, so they
    # inherit the full environment, provider credentials included. A hook may
    # legitimately call an LLM (``claude -p '...'``, ``llm -m ...``, an
    # OpenAI-SDK script) and needs ANTHROPIC_API_KEY/OPENAI_API_KEY to
    # authenticate. The credential scrub stays on the model's own
    # run_shell_command (command_runner._child_process_env).
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = os.getcwd()
    env["CLAUDE_TOOL_INPUT"] = json.dumps(event_data.tool_args)
    env["CLAUDE_TOOL_NAME"] = event_data.tool_name
    env["CLAUDE_HOOK_EVENT"] = event_data.event_type
    env["CLAUDE_CODE_HOOK"] = "1"

    file_path = _extract_file_path(event_data.tool_args)
    if file_path:
        env["CLAUDE_FILE_PATH"] = file_path

    if env_vars:
        env.update(env_vars)
    return env


async def execute_hooks_parallel(
    hooks: List[HookConfig],
    event_data: EventData,
    env_vars: Optional[Dict[str, str]] = None,
) -> List[ExecutionResult]:
    if not hooks:
        return []
    tasks = [execute_hook(hook, event_data, env_vars) for hook in hooks]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            final_results.append(
                ExecutionResult(
                    blocked=False,
                    hook_command=hooks[i].command,
                    stdout="",
                    stderr=str(result),
                    exit_code=-1,
                    duration_ms=0.0,
                    error=f"Hook execution failed: {result}",
                    hook_id=hooks[i].id,
                )
            )
        else:
            final_results.append(result)
    return final_results


async def execute_hooks_sequential(
    hooks: List[HookConfig],
    event_data: EventData,
    env_vars: Optional[Dict[str, str]] = None,
    stop_on_block: bool = True,
) -> List[ExecutionResult]:
    results = []
    for hook in hooks:
        result = await execute_hook(hook, event_data, env_vars)
        results.append(result)
        if stop_on_block and result.blocked:
            logger.debug(f"Hook blocked operation, stopping: {hook.command}")
            break
    return results


def get_blocking_result(results: List[ExecutionResult]) -> Optional[ExecutionResult]:
    for result in results:
        if result.blocked:
            return result
    return None


def get_failed_results(results: List[ExecutionResult]) -> List[ExecutionResult]:
    return [result for result in results if not result.success]


def format_execution_summary(results: List[ExecutionResult]) -> str:
    if not results:
        return "No hooks executed"
    total = len(results)
    successful = sum(1 for r in results if r.success)
    blocked = sum(1 for r in results if r.blocked)
    total_duration = sum(r.duration_ms for r in results)
    summary = [
        f"Executed {total} hook(s)",
        f"Successful: {successful}",
        f"Blocked: {blocked}",
        f"Total duration: {total_duration:.2f}ms",
    ]
    if blocked > 0:
        blocking_hooks = [r for r in results if r.blocked]
        summary.append("\nBlocking hooks:")
        for result in blocking_hooks:
            summary.append(f"  - {result.hook_command}")
            if result.error:
                summary.append(f"    Error: {result.error}")
    return "\n".join(summary)
