"""Pattern detection for git force push commands.

Detects force push patterns in shell commands, covering all the sneaky
ways git lets you wreck a remote branch.
"""

import re
from dataclasses import dataclass


@dataclass
class ForcePushMatch:
    """Result of a force push pattern match."""

    pattern_name: str
    description: str


# Matches shell operators that precede a new command in a pipeline/chain.
# E.g. "cd foo && git push --force" or "true || git push -f"
_SHELL_OPERATOR_RE = re.compile(r"(?:^|&&|\|\||;|\|)\s*git\s+push\b", re.MULTILINE)

# Ordered by specificity — first match wins.
# Each tuple: (compiled regex, human-readable name, what it catches)
_FORCE_PUSH_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"\bgit\s+push\b.*--force-with-lease"),
        "--force-with-lease",
        "force push with lease (safer, but still rewrites history)",
    ),
    (
        re.compile(r"\bgit\s+push\b.*--force-if-includes"),
        "--force-if-includes",
        "force push with includes check (still rewrites history)",
    ),
    (
        re.compile(r"\bgit\s+push\b.*--force"),
        "--force",
        "force push (rewrites remote history)",
    ),
    (
        re.compile(r"\bgit\s+push\b.*\s-f\b"),
        "-f",
        "force push shorthand (rewrites remote history)",
    ),
    (
        re.compile(r"\bgit\s+push\b.*\s-F\b"),
        "-F",
        "force push shorthand (rewrites remote history)",
    ),
    # The +refspec syntax: git push origin +main, git push origin +HEAD:main
    (
        re.compile(r"\bgit\s+push\b.*\s\+"),
        "+refspec",
        "force push via +refspec prefix (rewrites remote history)",
    ),
]


def _is_git_push_a_command(command: str) -> bool:
    """Check that 'git push' is an actual command, not a string argument.

    Handles compound commands like "cd foo && git push --force" while
    avoiding false positives like "echo 'git push --force'".

    Args:
        command: The shell command string to inspect.

    Returns:
        True if 'git push' appears as an actual command invocation.
    """
    return bool(_SHELL_OPERATOR_RE.search(command))


def detect_force_push(command: str) -> ForcePushMatch | None:
    """Check if a shell command contains a git force push.

    Args:
        command: The shell command string to inspect.

    Returns:
        ForcePushMatch if a force push pattern is found, None otherwise.
    """
    # Quick pre-filter: skip entirely if "push" isn't even in the command
    if "push" not in command:
        return None

    # Ensure 'git push' is an actual command, not a string argument
    if not _is_git_push_a_command(command):
        return None

    for pattern, name, description in _FORCE_PUSH_PATTERNS:
        if pattern.search(command):
            return ForcePushMatch(pattern_name=name, description=description)

    return None
