"""Pattern detection for destructive shell commands.

Detects dangerous patterns in shell commands using pure regex — no LLM
calls, no caching, no yolo-mode checks. Covers:
- Unix/Linux: rm -rf root/home, git push --mirror, git clean -fd, git reset --hard,
  git checkout/restore ., SQL DROP via clients, docker prune, accidental package publishes
- Windows PowerShell: Remove-Item, rmdir, del, Format-Volume, Clear-Disk, registry operations
- Windows CMD: rd, rmdir, del, erase with /s /q flags, format, diskpart
"""

import re
from dataclasses import dataclass


@dataclass
class DestructiveCommandMatch:
    """Result of a destructive command pattern match."""

    pattern_name: str
    description: str


# ---------------------------------------------------------------------------
# Shell-operator regex — same approach as force_push_guard
# ---------------------------------------------------------------------------

# Matches shell operators that precede a new command in a pipeline/chain.
# E.g. "cd foo && rm -rf /" or "true || git reset --hard"
# The capture ensures the command keyword follows a real shell boundary.
_SHELL_OPERATOR_RE = re.compile(r"(?:^|&&|\|\||;|\|)\s*\w+", re.MULTILINE)


def _is_real_command(command: str) -> bool:
    """Check that the destructive keyword is an actual invocation, not a string arg.

    Handles compound commands like "cd foo && rm -rf /" while
    avoiding false positives like "echo 'rm -rf /'".

    Args:
        command: The shell command string to inspect.

    Returns:
        True if the command appears to be a real invocation.
    """
    return bool(_SHELL_OPERATOR_RE.search(command))


# ---------------------------------------------------------------------------
# Cheap pre-filter substrings — if none appear, bail immediately
# ---------------------------------------------------------------------------

_PREFILTER_SUBSTRINGS = (
    # Unix/Linux
    "rm",
    "git",
    "docker",
    "drop",
    "npm",
    "yarn",
    "twine",
    "psql",
    "mysql",
    "sqlite3",
    # Windows PowerShell (cmdlets and common aliases)
    "remove-item",
    " ri ",
    "ri ",
    " rmdir",
    "del ",
    "erase",
    "format-volume",
    "clear-disk",
    "remove-itemproperty",
    "clear-recyclebin",
    "invoke-expression",
    " irm ",
    "iex",
    "get-childitem",
    # Windows CMD
    "rd ",
    "format",
    "diskpart",
    "bcdedit",
    "reg ",
    "netsh",
)


# ---------------------------------------------------------------------------
# Pattern lists — organized by shell type
# ---------------------------------------------------------------------------

# Unix destructive patterns
_UNIX_DESTRUCTIVE_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # —— Tier 1 ——————————————————————————————————————————————————————————————
    # 1. rm -rf /  /  rm -rf /*  (recursive delete of root filesystem)
    (
        re.compile(r"\brm\b.*\s-rf?\b.*\s/\s*$"),
        "rm -rf /",
        "recursive delete of root filesystem",
    ),
    (
        re.compile(r"\brm\b.*\s-rf?\b.*\s/\*\s*$"),
        "rm -rf /*",
        "recursive delete of root filesystem (glob)",
    ),
    # 2. rm -rf ~  /  rm -rf ~/*  (recursive delete of home directory)
    (
        re.compile(r"\brm\b.*\s-rf?\b.*\s~\s*$"),
        "rm -rf ~",
        "recursive delete of home directory",
    ),
    (
        re.compile(r"\brm\b.*\s-rf?\b.*\s~/\*\s*$"),
        "rm -rf ~/*",
        "recursive delete of home directory (glob)",
    ),
    # 3. git push --mirror  (deletes remote branches not present locally)
    (
        re.compile(r"\bgit\s+push\b.*--mirror\b"),
        "git push --mirror",
        "deletes remote branches not present locally",
    ),
    # 4. git clean -fd  (deletes untracked files and directories)
    (
        re.compile(r"\bgit\s+clean\b.*-f(?:[dxf]|\s+-?[dxf])"),
        "git clean -fd",
        "deletes untracked files and directories",
    ),
    # 5. git reset --hard  (destroys all uncommitted changes)
    (
        re.compile(r"\bgit\s+reset\b.*--hard\b"),
        "git reset --hard",
        "destroys all uncommitted changes",
    ),
    # 6. git checkout -- .  /  git restore .  (discards all working dir changes)
    (
        re.compile(r"\bgit\s+(?:checkout|restore)\b.*\s--?\s*\.\s*$"),
        "git checkout/restore .",
        "discards all working directory changes",
    ),
    # —— Tier 2 ——————————————————————————————————————————————————————————————
    # 7. DROP TABLE/DATABASE/SCHEMA via SQL client
    (
        re.compile(
            r"(?:psql|mysql|sqlite3)\b.*(?:-c|-e)\b.*DROP\s+(?:TABLE|DATABASE|SCHEMA)\b",
            re.IGNORECASE,
        ),
        "DROP via SQL client",
        "drops a table/database/schema via SQL client",
    ),
    (
        re.compile(
            r"DROP\s+(?:TABLE|DATABASE|SCHEMA)\b.*\|\s*(?:psql|mysql|sqlite3)\b",
            re.IGNORECASE,
        ),
        "DROP via SQL pipe",
        "drops a table/database/schema piped to SQL client",
    ),
    # 8. docker system prune -af  /  docker volume prune -f
    (
        re.compile(
            r"\bdocker\s+(?:system|volume)\s+prune\b.*(?:-[af]|\s-[af]|\s--all)"
        ),
        "docker prune",
        "nukes Docker resources without confirmation",
    ),
    # 9. npm publish  /  yarn publish  /  twine upload
    (
        re.compile(r"\b(?:npm|yarn)\s+publish\b"),
        "npm/yarn publish",
        "accidental package publishing",
    ),
    (
        re.compile(r"\btwine\s+upload\b"),
        "twine upload",
        "accidental package publishing",
    ),
]

# Windows PowerShell destructive patterns
_POWERSHELL_DESTRUCTIVE_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # —— Tier 1 PowerShell ————————————————————————————————————————————————————
    # 1. Remove-Item/ri with -Recurse/-r or -Force/-f flags
    (
        re.compile(
            r"(?:^|[;|&])\s*(?:Remove-Item|ri)\b.*\s-(?:r|recurse|f|force)\b",
            re.IGNORECASE,
        ),
        "Remove-Item with recursive/force flags",
        "deletion with recursive or force flag",
    ),
    # 2. Remove-Item -Recurse -Force on system directories
    (
        re.compile(
            r"\b(?:Remove-Item|ri)\b.*\s-(?:r|recurse)\b.*(?:C:|Windows|System32|Users|Program Files|ProgramData)",
            re.IGNORECASE,
        ),
        "Remove-Item on system location",
        "deletion operation on system directory or drive",
    ),
    # 3. Get-ChildItem piped to Remove-Item (pipeline delete)
    (
        re.compile(
            r"\|\s*\b(?:Remove-Item|ri|del|erase)\b",
            re.IGNORECASE,
        ),
        "Piped deletion command",
        "deletion via pipeline (potentially recursive)",
    ),
    # 4. Format-Volume (disk formatting)
    (
        re.compile(
            r"\b(?:Format-Volume|fdisk)\b",
            re.IGNORECASE,
        ),
        "Format-Volume",
        "formats a disk volume",
    ),
    # 5. Clear-Disk (wipes disk)
    (
        re.compile(
            r"\bClear-Disk\b",
            re.IGNORECASE,
        ),
        "Clear-Disk",
        "removes all data and OEM recovery partitions",
    ),
    # 6. Remove-ItemProperty on critical registry paths
    (
        re.compile(
            r"\b(?:Remove-ItemProperty|rp)\b.*\sHK(?:LM|CU|CR|U|CC):",
            re.IGNORECASE,
        ),
        "Remove-ItemProperty registry",
        "removes critical registry values",
    ),
    # 7. Clear-RecycleBin with -Force
    (
        re.compile(
            r"\b(?:Clear-RecycleBin|recycle)\b.*\s-(?:f|force)\b",
            re.IGNORECASE,
        ),
        "Clear-RecycleBin -Force",
        "permanently deletes all recycle bin contents",
    ),
    # 8. Invoke-WebRequest / Invoke-RestMethod piped to IEX (remote code execution)
    (
        re.compile(
            r"\b(?:irm|Invoke-WebRequest|iwr|Invoke-RestMethod|curl|wget)\b.*\|\s*(?:iex|Invoke-Expression)\b",
            re.IGNORECASE,
        ),
        "Download + Execute (IWR| IEX)",
        "downloads and executes remote code",
    ),
]

# Windows CMD destructive patterns
_CMD_DESTRUCTIVE_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # —— Tier 1 CMD ———————————————————————————————————————————————————————————
    # 1. rd /s /q - recursive silent delete
    (
        re.compile(
            r"\b(?:rmdir|rd)\b.*\s/s\b.*\s/q\b",
            re.IGNORECASE,
        ),
        "rd /s /q",
        "recursive silent directory delete",
    ),
    (
        re.compile(
            r"\b(?:rmdir|rd)\b.*\s/q\b.*\s/s\b",
            re.IGNORECASE,
        ),
        "rd /s /q",
        "recursive silent directory delete",
    ),
    # 2. del /s /q /f on system directories
    (
        re.compile(
            r"\b(?:del|erase)\b.*\s/s\b.*(?:Windows|System32|Program)",
            re.IGNORECASE,
        ),
        "del /s system files",
        "recursive delete of system files",
    ),
    (
        re.compile(
            r"\b(?:del|erase)\b.*\s/f\b.*\s/s\b.*(?:Windows|System32|Program)",
            re.IGNORECASE,
        ),
        "del /f /s system files",
        "force recursive delete of system files",
    ),
    # 3. format command without confirmation
    (
        re.compile(
            r"(?:^|&&|\|\||;|\|)\s*format\b.*\s(?:C:|D:|E:)",
            re.IGNORECASE,
        ),
        "format",
        "formats drive",
    ),
    (
        re.compile(
            r"(?:^|&&|\|\||;|\|)\s*format\b.*\s/q\b.*\s(?:C:|D:|E:)",
            re.IGNORECASE,
        ),
        "format /q",
        "quick formats drive",
    ),
    # 4. diskpart invocation (almost never legitimate in automation)
    (
        re.compile(
            r"\bdiskpart\b",
            re.IGNORECASE,
        ),
        "diskpart",
        "diskpart disk management tool",
    ),
    # 5. bcdedit (boot configuration) modifications
    (
        re.compile(
            r"\bbcdedit\b.*\s/(?:delete|set|export|import|bootsequence)\b.*\s(?:{.*}|.*bootmgr|.*resume)",
            re.IGNORECASE,
        ),
        "bcdedit destructive",
        "modifies critical boot configuration",
    ),
    # 6. reg delete on critical keys
    (
        re.compile(
            r"\breg\s+delete\b.*\sHK(?:LM|CR|CU)",
            re.IGNORECASE,
        ),
        "reg delete",
        "deletes critical registry keys",
    ),
]

# Combine all patterns
_DESTRUCTIVE_PATTERNS = (
    _UNIX_DESTRUCTIVE_PATTERNS
    + _POWERSHELL_DESTRUCTIVE_PATTERNS
    + _CMD_DESTRUCTIVE_PATTERNS
)


def detect_destructive_command(command: str) -> DestructiveCommandMatch | None:
    """Check if a shell command contains a destructive operation.

    Uses a cheap substring pre-filter before any regex work, then verifies
    the command is a real invocation (not a string argument), then checks
    patterns first-match-wins.

    Args:
        command: The shell command string to inspect.

    Returns:
        DestructiveCommandMatch if a destructive pattern is found, None otherwise.
    """
    # Quick pre-filter: bail if none of the trigger substrings appear
    command_lower = command.lower()
    if not any(sub in command_lower for sub in _PREFILTER_SUBSTRINGS):
        return None

    # Ensure the command is a real invocation, not a string argument
    if not _is_real_command(command):
        return None

    for pattern, name, description in _DESTRUCTIVE_PATTERNS:
        if pattern.search(command):
            return DestructiveCommandMatch(pattern_name=name, description=description)

    return None
