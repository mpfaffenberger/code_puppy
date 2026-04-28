"""Shell pass-through for direct command execution.

Prepend a prompt with `!` to execute it as a shell command directly,
bypassing the agent entirely. Inspired by Claude Code's `!` prefix.

Also auto-detects well-known CLI commands (e.g. ``ls``, ``git``, ``grep``)
so users can type them without the ``!`` prefix and still bypass the AI agent
— consuming zero tokens.

Examples:
    !ls -la
    !git status
    !python --version
    ls -la          ← auto-detected, no tokens used
    git status      ← auto-detected, no tokens used
    ls | grep test  ← auto-detected, no tokens used
"""

import os
import re
import shutil
import subprocess
import sys
import time

from rich.console import Console
from rich.markup import escape as escape_rich_markup

from code_puppy.config import get_banner_color

# The prefix character that triggers shell pass-through
SHELL_PASSTHROUGH_PREFIX = "!"

# Banner identifier — matches the key in DEFAULT_BANNER_COLORS
_BANNER_NAME = "shell_passthrough"

# ---------------------------------------------------------------------------
# Auto-detection: known CLI commands that should bypass the AI agent
# ---------------------------------------------------------------------------
# When a user types one of these commands directly (without the ``!`` prefix),
# Code Puppy automatically routes the input to the shell — no tokens consumed.
#
# Extend this set to add more commands. Keep it sorted for readability.
KNOWN_CLI_COMMANDS: frozenset[str] = frozenset(
    {
        # ── Archives ──────────────────────────────────────────────────────
        "bzip2",
        "gunzip",
        "gzip",
        "tar",
        "unzip",
        "xz",
        "zip",
        # ── Build / package managers ──────────────────────────────────────
        "cargo",
        "cmake",
        "gradle",
        "make",
        "maven",
        "mvn",
        "npm",
        "npx",
        "pip",
        "pip3",
        "poetry",
        "pnpm",
        "yarn",
        # ── Containers / orchestration ────────────────────────────────────
        "docker",
        "docker-compose",
        "helm",
        "kubectl",
        "podman",
        # ── File system ───────────────────────────────────────────────────
        "cat",
        "cd",
        "chmod",
        "chown",
        "cp",
        "dir",
        "du",
        "file",
        "find",
        "head",
        "la",
        "less",
        "ll",
        "ln",
        "locate",
        "ls",
        "mkdir",
        "more",
        "mv",
        "popd",
        "pushd",
        "pwd",
        "rm",
        "rmdir",
        "tail",
        "touch",
        "tree",
        "wc",
        # ── Language runtimes ─────────────────────────────────────────────
        "go",
        "java",
        "javac",
        "node",
        "python",
        "python3",
        "ruby",
        "rustc",
        # ── Misc utilities ────────────────────────────────────────────────
        "alias",
        "cal",
        "date",
        "df",
        "echo",
        "env",
        "export",
        "free",
        "history",
        "id",
        "info",
        "man",
        "open",
        "pbcopy",
        "pbpaste",
        "printf",
        "type",
        "uname",
        "unalias",
        "uptime",
        "which",
        "whereis",
        "whoami",
        "xclip",
        "xsel",
        # ── Network ───────────────────────────────────────────────────────
        "curl",
        "dig",
        "host",
        "ifconfig",
        "ip",
        "nc",
        "netstat",
        "nslookup",
        "ping",
        "rsync",
        "scp",
        "ssh",
        "wget",
        # ── Process / system ──────────────────────────────────────────────
        "bg",
        "fg",
        "htop",
        "jobs",
        "kill",
        "killall",
        "ps",
        "top",
        "who",
        # ── System package managers ───────────────────────────────────────
        "apt",
        "apt-get",
        "dnf",
        "pacman",
        "snap",
        "systemctl",
        "yum",
        # ── Text processing ───────────────────────────────────────────────
        "awk",
        "cut",
        "diff",
        "egrep",
        "fgrep",
        "grep",
        "jq",
        "patch",
        "rg",
        "ripgrep",
        "sed",
        "sort",
        "tee",
        "tr",
        "uniq",
        "xargs",
        # ── Version control ───────────────────────────────────────────────
        "git",
        "hg",
        "svn",
    }
)

# Commands that double as common English words and frequently appear at the
# start of natural-language prompts (e.g. "find memory leak in parser",
# "open the config file", "type the password").  For these we require stronger
# shell intent evidence before auto-routing.
_AMBIGUOUS_CLI_COMMANDS: frozenset[str] = frozenset(
    {
        "date",
        "find",
        "history",
        "id",
        "info",
        "man",
        "open",
        "type",
        "which",
        "who",
    }
)

# Patterns that strongly indicate the user intends a real shell invocation:
#   |  &  ;  <  >  `  $  ( )       — shell operators / substitution
#   -flag                           — a CLI flag (-v, --verbose, -la …)
#   ./path  ../path  /abs/path      — explicit Unix filesystem paths
#   .\path  ..\path  C:\abs\path    — explicit Windows filesystem paths
_SHELL_INTENT_RE = re.compile(
    r"[|&;<>`$()]"
    r"|(?:^|\s)-\w"
    r"|(?:^|\s)\.{1,2}[/\\]"
    r"|(?:^|\s)/"
    r"|(?:^|\s)[A-Za-z]:\\"
)

# Pre-compiled regex: first "word" of the input (handles leading whitespace)
_FIRST_WORD_RE = re.compile(r"^\s*(\S+)")


def is_known_cli_command(task: str) -> bool:
    """Return True when *task* starts with a well-known CLI command name **and**
    the overall input looks like a real shell invocation rather than natural
    language.

    Three-stage filter (conservative by design):

    1. **Known list** — first token must be in ``KNOWN_CLI_COMMANDS``.
    2. **PATH check** — the executable must actually exist on ``$PATH``
       (via ``shutil.which``).  This rejects invented commands that happen to
       share a name with a list entry on this machine.
    3. **Ambiguity guard** — for commands that are also common English words
       (``find``, ``open``, ``date`` …) the rest of the input must show at
       least one strong shell-intent signal: a flag (``-v``), a path
       (``./src``), or a shell operator (``|``, ``>``, etc.).

    Single-word inputs (``pwd``, ``git``) skip stage 3 — they're unambiguous.

    Args:
        task: Raw user input string.

    Returns:
        True if the input should be routed directly to the shell.
    """
    stripped = task.strip()

    # Already handled by other code paths — skip early.
    if stripped.startswith(SHELL_PASSTHROUGH_PREFIX) or stripped.startswith("/"):
        return False

    match = _FIRST_WORD_RE.match(stripped)
    if not match:
        return False

    first_word = match.group(1).lower()

    # Stage 1: must be a known CLI command.
    if first_word not in KNOWN_CLI_COMMANDS:
        return False

    # Stage 2: executable must exist on PATH (prevents false positives on
    # machines where the command isn't installed, and catches typos).
    if shutil.which(first_word) is None:
        return False

    # Single-word commands are unambiguous — accept immediately.
    if " " not in stripped:
        return True

    # Stage 3: ambiguous English words require explicit shell-intent evidence.
    if first_word in _AMBIGUOUS_CLI_COMMANDS and not _SHELL_INTENT_RE.search(stripped):
        return False

    return True


# ---------------------------------------------------------------------------
# PowerShell Verb-Noun cmdlet detection (cross-platform)
# ---------------------------------------------------------------------------
# PowerShell cmdlets follow an approved Verb-Noun naming convention:
#   Get-ChildItem, Set-Location, Invoke-WebRequest, etc.
# These are NOT in KNOWN_CLI_COMMANDS because they use a unique naming pattern.
# PowerShell Core (pwsh) runs on Windows, macOS, AND Linux — so this detection
# is NOT gated by platform.  Instead, we check for `pwsh`/`powershell` on PATH.
_PS_CMDLET_RE = re.compile(
    r"^(?:Get|Set|New|Remove|Start|Stop|Invoke|Write|Read|"
    r"Copy|Move|Rename|Test|Out|Format|Select|Where|Sort|"
    r"Add|Clear|Compare|Convert|ConvertFrom|ConvertTo|"
    r"Disable|Enable|Enter|Exit|Export|Import|Join|"
    r"Limit|Measure|Merge|Pop|Push|Redo|Reset|"
    r"Restore|Resume|Save|Search|Send|Split|"
    r"Step|Submit|Switch|Sync|Undo|Uninstall|"
    r"Unlock|Unregister|Update|Use|Wait|Watch)-\w+",
    re.IGNORECASE,
)

# Cache for PowerShell availability — computed once per session.
# None means "not yet checked", True/False is the cached result.
_powershell_available: bool | None = None


def _is_powershell_on_path() -> bool:
    """Return True if ``pwsh`` or ``powershell`` is available on ``$PATH``.

    Result is cached for the lifetime of the process so we only pay the
    ``shutil.which`` cost once per session — not on every keystroke.
    """
    global _powershell_available
    if _powershell_available is None:
        _powershell_available = (
            shutil.which("pwsh") is not None or shutil.which("powershell") is not None
        )
    return _powershell_available


def is_powershell_cmdlet(task: str) -> bool:
    """Return True when *task* looks like a PowerShell Verb-Noun cmdlet.

    Works on **any platform** where PowerShell Core (``pwsh``) or legacy
    ``powershell`` is installed.  The availability check is cached so only
    the very first call per session incurs a ``shutil.which`` lookup.

    Examples that match:
        Get-ChildItem
        Get-ChildItem -Path ./src
        Set-Location C:\\projects
        Invoke-WebRequest https://example.com

    Examples that do NOT match:
        Get some coffee           (not Verb-Noun)
        ls -la                    (handled by is_known_cli_command)
        Select the right option   (no hyphen-joined noun)

    Args:
        task: Raw user input string.

    Returns:
        True if the input should be routed to PowerShell directly.
    """
    stripped = task.strip()

    # Already handled by other code paths.
    if stripped.startswith(SHELL_PASSTHROUGH_PREFIX) or stripped.startswith("/"):
        return False

    # Must match Verb-Noun pattern first (cheap regex check).
    if not _PS_CMDLET_RE.match(stripped):
        return False

    # Must have PowerShell available (cached after first call).
    return _is_powershell_on_path()


# ---------------------------------------------------------------------------
# Platform-aware shell resolution
# ---------------------------------------------------------------------------

# Cache for the resolved shell — computed once per session.
_cached_platform_shell: list[str] | None = None


def _get_platform_shell() -> list[str]:
    """Return the shell executable + invocation flag for the current platform.

    - **Windows**: prefer ``pwsh`` (PowerShell Core) → ``powershell``
      (legacy) → ``cmd``.
    - **Unix**: use ``$SHELL`` env var → fallback to ``/bin/sh``.

    Result is cached for the lifetime of the process so we only pay the
    ``shutil.which`` cost once — not on every command.

    Returns:
        A list like ``["pwsh", "-Command"]`` or ``["/bin/zsh", "-c"]``
        suitable for ``subprocess.run([*shell, command], ...)``.
    """
    global _cached_platform_shell
    if _cached_platform_shell is not None:
        return _cached_platform_shell

    if sys.platform == "win32":
        for ps in ("pwsh", "powershell"):
            if shutil.which(ps):
                _cached_platform_shell = [ps, "-Command"]
                return _cached_platform_shell
        _cached_platform_shell = ["cmd", "/c"]
    else:
        shell = os.environ.get("SHELL", "/bin/sh")
        _cached_platform_shell = [shell, "-c"]

    return _cached_platform_shell


def _get_console() -> Console:
    """Get a Rich console for direct output.

    Separated for testability — tests can mock this to capture output.
    """
    return Console()


def _format_banner() -> str:
    """Format the SHELL PASSTHROUGH banner using the configured color.

    Uses the same `[bold white on {color}]` pattern as rich_renderer.py
    so the banner looks consistent with SHELL COMMAND, EDIT FILE, etc.

    Returns:
        Rich markup string for the banner.
    """
    color = get_banner_color(_BANNER_NAME)
    return f"[bold white on {color}] 🐚 SHELL PASSTHROUGH [/bold white on {color}]"


def is_shell_passthrough(task: str) -> bool:
    """Check if user input is a shell pass-through command.

    A pass-through command starts with `!` followed by a non-empty command.
    A bare `!` with nothing after it is NOT a pass-through.

    Args:
        task: Raw user input string.

    Returns:
        True if the input is a shell pass-through command.
    """
    stripped = task.strip()
    return (
        stripped.startswith(SHELL_PASSTHROUGH_PREFIX)
        and len(stripped) > len(SHELL_PASSTHROUGH_PREFIX)
        and not stripped[len(SHELL_PASSTHROUGH_PREFIX) :].isspace()
    )


def extract_command(task: str) -> str:
    """Extract the shell command from a pass-through input.

    Strips the leading `!` prefix and any surrounding whitespace.

    Args:
        task: Raw user input (must pass `is_shell_passthrough` check).

    Returns:
        The shell command to execute.
    """
    return task.strip()[len(SHELL_PASSTHROUGH_PREFIX) :].strip()


def execute_shell_passthrough(task: str) -> None:
    """Execute a shell command directly, bypassing the agent.

    Renders a colored banner (matching the codebase banner system) so the
    user instantly sees they're in pass-through mode, then inherits stdio
    for raw terminal output.

    Ctrl+C during execution kills the subprocess, not Code Puppy.

    Args:
        task: Raw user input starting with `!`.
    """
    console = _get_console()
    command = extract_command(task)

    if not command:
        console.print(
            "[yellow]Empty command. Usage: !<command> (e.g., !ls -la)[/yellow]"
        )
        return

    # Escape command to prevent Rich markup injection
    safe_command = escape_rich_markup(command)

    # Banner + command on one line, context hint below
    banner = _format_banner()
    console.print(f"\n{banner} [dim]$ {safe_command}[/dim]")
    console.print("[dim]↳ Direct shell · Bypassing AI agent[/dim]")

    start_time = time.monotonic()

    try:
        shell_args = _get_platform_shell()
        result = subprocess.run(
            [*shell_args, command],
            shell=False,
            cwd=os.getcwd(),
            # Inherit stdio — output goes straight to the terminal
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        elapsed = time.monotonic() - start_time

        if result.returncode == 0:
            console.print(
                f"[bold green]✅ Done[/bold green] [dim]({elapsed:.1f}s)[/dim]"
            )
        else:
            console.print(
                f"[bold red]❌ Exit code {result.returncode}[/bold red] "
                f"[dim]({elapsed:.1f}s)[/dim]"
            )

    except KeyboardInterrupt:
        elapsed = time.monotonic() - start_time
        console.print(
            f"\n[bold yellow]⚡ Interrupted[/bold yellow] [dim]({elapsed:.1f}s)[/dim]"
        )

    except Exception as e:
        safe_error = escape_rich_markup(str(e))
        console.print(f"[bold red]Shell error:[/bold red] {safe_error}")
