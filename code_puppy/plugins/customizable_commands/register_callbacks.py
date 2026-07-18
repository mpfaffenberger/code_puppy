import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_error, emit_info, emit_shell_line, emit_warning

# Reuse the skills plugin's lightweight (dependency-free) frontmatter parser
# instead of rolling our own -- one source of truth for YAML frontmatter.
from code_puppy.plugins.agent_skills.metadata import (
    FRONTMATTER_PATTERN,
    parse_yaml_frontmatter,
)

# Global cache for loaded commands
_custom_commands: Dict[str, str] = {}
_command_descriptions: Dict[str, str] = {}
# Commands whose frontmatter declares `exec: <shell command>` are executed
# directly instead of being forwarded to the agent. The value is the raw
# shell command string (run with shell=True so ``~`` / pipes / env vars work).
_command_exec_directives: Dict[str, str] = {}
_commands_loaded: bool = False  # Sentinel to track if commands have been loaded

# Soft cap so a runaway script can't wedge the prompt forever.
_EXEC_TIMEOUT_SECONDS = 30

# Directories to scan for commands (in priority order - later directories override earlier)
# The global commands dir reuses CONFIG_DIR (the canonical ~/.code_puppy resolver,
# XDG-aware) so it stays in lockstep with the rest of code-puppy's file layout.
_GLOBAL_COMMANDS_DIR = os.path.join(CONFIG_DIR, "commands")
_COMMAND_DIRECTORIES = [
    _GLOBAL_COMMANDS_DIR,  # Global commands (all projects)
    ".claude/commands",
    ".github/prompts",
    ".agents/commands",
]

# `exec:` directives run arbitrary shell, so we only honor them from the global,
# user-owned config dir. Project-relative dirs (``.claude/commands``,
# ``.github/prompts``, ``.agents/commands``) live inside whatever repo you
# happen to be standing in -- a cloned hostile repo could otherwise drop an
# ``exec:`` command that runs the moment you invoke it, bypassing the plugin
# trust ceremony entirely. Bodies from those dirs still load as normal
# (agent-forwarded) commands; only the exec fast-path is gated.
_TRUSTED_EXEC_DIRECTORIES = frozenset({_GLOBAL_COMMANDS_DIR})


def _is_trusted_exec_dir(dir_path: Path) -> bool:
    """True if ``exec:`` directives from ``dir_path`` are allowed to run.

    Compares the *resolved* path against the trusted set so symlinks / ``..``
    tricks can't smuggle a project dir past the gate. Fails closed on any
    resolution error.
    """
    try:
        resolved = dir_path.resolve()
    except OSError:
        return False
    for trusted in _TRUSTED_EXEC_DIRECTORIES:
        try:
            if resolved == Path(trusted).expanduser().resolve():
                return True
        except OSError:
            continue
    return False


class MarkdownCommandResult:
    """Special marker for markdown command results that should be processed as input."""

    def __init__(self, content: str):
        self.content = content

    def __str__(self) -> str:
        return self.content

    def __repr__(self) -> str:
        return f"MarkdownCommandResult({len(self.content)} chars)"


# Namespace directories beginning with these prefixes are skipped entirely
# (docs, build artefacts, private helpers) so they don't leak as commands.
_SKIP_DIR_PREFIXES = ("_", ".")


def _is_in_skipped_namespace(md_file: Path, root: Path) -> bool:
    """True if any parent directory beneath ``root`` is "hidden".

    Files under directories like ``_docs/``, ``__pycache__/`` or ``.git/`` are
    excluded so they never register as slash commands. Only the namespace
    (parent) parts are checked -- a leaf file named ``_foo.md`` is still loaded.
    """
    namespace_parts = md_file.relative_to(root).parts[:-1]
    return any(part.startswith(_SKIP_DIR_PREFIXES) for part in namespace_parts)


# Wibey authors commands with a double-slash prefix (//flux/new), but code-puppy
# slash-commands use a single slash (/flux/new). Collapse a leading "//" that
# begins a line (optionally indented) at LOAD time so the source .md files stay
# untouched. Anchoring to line start leaves real URLs -- including
# whitespace-preceded protocol-relative ones like ``fetch //cdn.example.com`` --
# completely alone; only a ``//command`` at the start of a line is rewritten.
_DOUBLE_SLASH_PREFIX_RE = re.compile(r"(?m)^(\s*)//(?=[\w-])")


def _normalize_command_prefixes(text: str) -> str:
    """Rewrite wibey-style ``//cmd`` command references to ``/cmd``.

    Only a ``//command`` at the start of a line (optionally indented) is
    normalized; inline / whitespace-preceded ``//host`` sequences (e.g.
    protocol-relative URLs) are left untouched. Applied in-memory to command
    bodies and descriptions; the original markdown files are never modified.
    """
    return _DOUBLE_SLASH_PREFIX_RE.sub(r"\1/", text)


def _derive_description(meta: dict, body: str, base_name: str) -> str:
    """Pick a human-readable description for the /help + completion picker.

    Priority:
        1. The ``description:`` field from YAML frontmatter (used verbatim).
        2. The first non-empty, non-heading line of the body (truncated).
        3. A title-cased version of the command name.
    """
    desc = meta.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc.strip()

    for line in body.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:50] + ("..." if len(stripped) > 50 else "")

    return base_name.replace("_", " ").replace("-", " ").title()


def _command_name_from_path(md_file: Path, root: Path) -> str:
    """Derive a (possibly namespaced) command name from a markdown file path.

    The name mirrors the directory structure beneath ``root``, joined with
    ``/``. Examples (root = ``~/.code_puppy/commands``)::

        hello-world.md      -> "hello-world"
        flux/new.md         -> "flux/new"
        flux/sub/thing.md   -> "flux/sub/thing"

    The ``.prompt.md`` double-suffix (used by ``.github/prompts``) is stripped
    the same way the legacy flat loader did.
    """
    rel = md_file.relative_to(root)
    if md_file.name.endswith(".prompt.md"):
        leaf = md_file.name[: -len(".prompt.md")]
    else:
        leaf = md_file.stem
    # Join any parent directories (the namespace) with the leaf command name.
    parts = [*rel.parts[:-1], leaf]
    return "/".join(parts)


def _load_markdown_commands() -> None:
    """Load markdown command files from the configured directories.

    Recursively scans for *.md files in the configured directories and loads
    them as custom commands. Subdirectories become namespaces, so
    ``flux/new.md`` is invoked as ``/flux/new``. Later directories override
    earlier ones with the same command name (project commands override global).
    """
    global _custom_commands, _command_descriptions, _commands_loaded

    _custom_commands.clear()
    _command_descriptions.clear()
    _command_exec_directives.clear()
    _commands_loaded = True  # Mark as loaded even if directories are empty

    # Process directories in order - later directories override earlier ones
    for directory in _COMMAND_DIRECTORIES:
        dir_path = Path(directory).expanduser()
        if not dir_path.exists():
            continue

        # `exec:` only runs from user-owned trusted dirs (see module docstring
        # on _TRUSTED_EXEC_DIRECTORIES). Compute once per directory.
        exec_allowed = _is_trusted_exec_dir(dir_path)

        # Look for markdown files (recursively, so subdirs become namespaces)
        pattern = "*.md" if directory != ".github/prompts" else "*.prompt.md"
        # Sort within directory for consistent ordering
        md_files = sorted(dir_path.rglob(pattern))

        for md_file in md_files:
            try:
                # Skip files under hidden/underscore namespaces (_docs, .git, ...)
                if _is_in_skipped_namespace(md_file, dir_path):
                    continue

                # Command name mirrors the path beneath dir_path (flux/new.md
                # -> "flux/new"); top-level files stay un-namespaced.
                base_name = _command_name_from_path(md_file, dir_path)

                # Read raw content, then separate frontmatter from the body.
                # NB: do NOT strip `raw` before parsing -- FRONTMATTER_PATTERN
                # requires a trailing newline after the closing `---`, so a
                # body-less (exec-only) command file would otherwise fail to
                # parse: its exec: directive would be silently dropped and the
                # raw YAML leaked to the model as the command body.
                raw = md_file.read_text(encoding="utf-8")
                if not raw.strip():
                    continue

                # The name/description frontmatter is metadata for the command
                # system -- strip it so the agent receives clean instructions
                # (otherwise the model treats the YAML block as context noise).
                meta = parse_yaml_frontmatter(raw)
                body = FRONTMATTER_PATTERN.sub("", raw, count=1).strip()
                exec_directive = meta.get("exec")
                has_exec = isinstance(exec_directive, str) and bool(
                    exec_directive.strip()
                )
                # Skip only when there's genuinely nothing to register: no body
                # AND no exec directive. An exec-only command (frontmatter only)
                # is legitimate and must still load.
                if not body and not has_exec:
                    continue

                # Normalize wibey //cmd -> /cmd in the body the agent receives.
                body = _normalize_command_prefixes(body)

                description = _normalize_command_prefixes(
                    _derive_description(meta, body, base_name)
                )

                # Later directories override earlier ones (project > global)
                _custom_commands[base_name] = body
                _command_descriptions[base_name] = description

                # Optional: `exec: <shell command>` runs a script instead of
                # forwarding the body to the agent. Used for things like
                # /flux/status that render their own colored output. Only
                # honored from trusted (user-owned) dirs -- an exec directive
                # from a project-relative dir is downgraded to a normal command.
                if has_exec:
                    if exec_allowed:
                        _command_exec_directives[base_name] = exec_directive.strip()
                    else:
                        emit_warning(
                            f"Ignoring exec: directive on /{base_name} from "
                            f"untrusted dir '{directory}' (only "
                            f"{_GLOBAL_COMMANDS_DIR} may run exec)."
                        )
                        # Downgrade to a normal agent-forwarded command; make
                        # sure no earlier trusted exec lingers under this name.
                        _command_exec_directives.pop(base_name, None)
                else:
                    # Later dirs without exec should clear an earlier one for
                    # the same name (override semantics for the exec hook too).
                    _command_exec_directives.pop(base_name, None)

            except Exception as e:
                emit_error(f"Failed to load command from {md_file}: {e}")


_EXEC_TOKEN_RE = re.compile(
    r"\{(python|scripts|commands|script|command)(?::([^}]+))?\}"
)


def _shell_quote(value: str) -> str:
    """Quote a single argument for the shell ``subprocess`` will spawn.

    ``_run_exec_directive`` uses ``shell=True``; the shell differs by OS, and so
    does its quoting. ``shlex.quote`` is POSIX-only (it emits single-quotes that
    ``cmd.exe`` does not understand), so on Windows we defer to
    ``subprocess.list2cmdline`` which produces cmd-compatible quoting.
    """
    if os.name == "nt":
        return subprocess.list2cmdline([value])
    return shlex.quote(value)


def _expand_exec_tokens(directive: str) -> str:
    """Substitute exec tokens ({python}/{script:...}/...) in a directive.

    Command files reference these tokens so they never hard-code an interpreter,
    a shell-expansion (~), or an OS-specific path -- all three of which break on
    Windows and ignore code-puppy's XDG-configured CONFIG_DIR:

        {python}          -> sys.executable (the venv interpreter running us)
        {scripts}         -> <CONFIG_DIR>/scripts          (absolute)
        {commands}        -> <CONFIG_DIR>/commands         (absolute)
        {script:foo.py}   -> <CONFIG_DIR>/scripts/foo.py   (absolute)
        {command:a/b.md}  -> <CONFIG_DIR>/commands/a/b.md  (absolute)

    Each expansion is quoted for the current platform's shell so paths with
    spaces survive. CONFIG_DIR is read fresh on each call so an env override is
    honored. Unknown-shaped tokens are left untouched.
    """

    def _replace(match):
        kind, arg = match.group(1), match.group(2)
        if kind == "python":
            return _shell_quote(sys.executable or "python3")
        if kind == "scripts":
            return _shell_quote(os.path.join(CONFIG_DIR, "scripts"))
        if kind == "commands":
            return _shell_quote(os.path.join(CONFIG_DIR, "commands"))
        if kind == "script":
            rel = (arg or "").strip()
            return _shell_quote(os.path.join(CONFIG_DIR, "scripts", *rel.split("/")))
        if kind == "command":
            rel = (arg or "").strip()
            return _shell_quote(os.path.join(CONFIG_DIR, "commands", *rel.split("/")))
        return match.group(0)

    return _EXEC_TOKEN_RE.sub(_replace, directive)


def _run_exec_directive(directive: str, name: str, args: str = "") -> None:
    """Run an ``exec:`` directive and stream its output via the message bus.

    Uses ``shell=True`` so directives can use ``~``, env vars, and pipes. This
    is only reachable for commands loaded from a trusted (user-owned) dir --
    the loader refuses to register exec directives from project-relative dirs
    (see :data:`_TRUSTED_EXEC_DIRECTORIES`), so a hostile repo can't smuggle
    one in.
    Sets ``FORCE_COLOR=1`` so scripts emit ANSI even though stdout is a pipe;
    :func:`emit_shell_line` then renders the ANSI via Rich's ``Text.from_ansi``.

    Any extra tokens the user typed after the command (e.g. ``/flux/status todo``)
    are shell-quoted and appended to the directive so dangerous shell chars in
    user input can't escape into the command line.

    ``{python}`` / ``{script:...}`` / ``{command:...}`` tokens in the directive
    are expanded first (see :func:`_expand_exec_tokens`) so command files stay
    interpreter-, path-, and OS-agnostic.
    """
    directive = _expand_exec_tokens(directive)
    full_cmd = directive
    if args:
        try:
            tokens = shlex.split(args)
        except ValueError:
            # Fall back to a single shell-quoted blob if shlex can't parse it
            # (e.g. unbalanced quotes). Keeps the user's intent without crashing.
            tokens = [args]
        if tokens:
            full_cmd = directive + " " + " ".join(shlex.quote(t) for t in tokens)

    emit_info(f"  Running exec for /{name}: {full_cmd}")
    env = {**os.environ, "FORCE_COLOR": "1"}
    try:
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=_EXEC_TIMEOUT_SECONDS,
            env=env,
        )
    except subprocess.TimeoutExpired:
        emit_error(f"exec for /{name} timed out after {_EXEC_TIMEOUT_SECONDS}s")
        return
    except Exception as exc:
        emit_error(f"exec for /{name} failed to start: {exc}")
        return

    for line in result.stdout.splitlines():
        emit_shell_line(line, stream="stdout")
    for line in result.stderr.splitlines():
        emit_shell_line(line, stream="stderr")

    if result.returncode != 0:
        emit_warning(f"exec for /{name} exited with code {result.returncode}")


def reload_commands() -> None:
    """Force a fresh rescan of the command directories.

    The cache is populated once at plugin import time. Anything that writes new
    command files *after* import (e.g. the flux_bootstrap plugin installing the
    Flux suite during the ``startup`` hook) must call this so the freshly
    installed commands become dispatchable immediately -- otherwise ``/flux/...``
    is treated as ordinary input until the next restart. This is the explicit
    loader API the review asked for; prefer it over poking the private cache.
    """
    _load_markdown_commands()


def is_custom_command(name: str) -> bool:
    """True if ``name`` is a loaded custom command (namespaced or flat).

    Exposed so the host's file-path disambiguation heuristic can tell a
    genuine path (``/Users/me/file.py``) apart from a namespaced command
    (``/flux/status``) -- both have multiple slashes. Loads commands lazily
    on first use so it works even before the first dispatch.
    """
    if not _commands_loaded:
        _load_markdown_commands()
    return name in _custom_commands or name in _command_exec_directives


def _custom_help() -> List[Tuple[str, str]]:
    """Return help entries for loaded markdown commands."""
    # Reload commands to pick up any changes
    _load_markdown_commands()

    help_entries = []
    for name, description in sorted(_command_descriptions.items()):
        help_entries.append((name, description))

    return help_entries


def _handle_custom_command(command: str, name: str) -> Optional[Any]:
    """Handle a markdown-based custom command.

    Args:
        command: The full command string
        name: The command name without leading slash

    Returns:
        MarkdownCommandResult with content to be processed as input,
        or None if not found
    """
    if not name:
        return None

    # Ensure commands are loaded (use sentinel, not dict emptiness)
    if not _commands_loaded:
        _load_markdown_commands()

    # Extract any additional arguments from the command (shared by both paths)
    parts = command.split(maxsplit=1)
    args = parts[1] if len(parts) > 1 else ""

    # exec: directive wins -- run the script, bypass the agent entirely.
    exec_directive = _command_exec_directives.get(name)
    if exec_directive:
        _run_exec_directive(exec_directive, name, args=args)
        return True  # handled; do not invoke the model

    # Look up the command
    content = _custom_commands.get(name)
    if content is None:
        return None

    # If there are arguments, append them to the prompt
    if args:
        prompt = f"{content}\n\nAdditional context: {args}"
    else:
        prompt = content

    # Emit info message and return the special marker
    emit_info(f"📝 Executing markdown command: {name}")
    return MarkdownCommandResult(prompt)


# Register callbacks
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)

# Make the result class available for the command handler
# Import this in command_handler.py to check for this type
__all__ = ["MarkdownCommandResult", "reload_commands"]

# Load commands at import time
_load_markdown_commands()
