"""Conservative, side-effect-free shell command-prefix classification."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache


class PrefixKind(str, Enum):
    PREFIX = "prefix"
    INJECTION = "command_injection_detected"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class PrefixVerdict:
    kind: PrefixKind
    prefix: str | None = None
    reason: str = ""


_SIMPLE_PREFIXES = frozenset(
    {
        "cat",
        "echo",
        "head",
        "ls",
        "pwd",
        "rg",
        "sed",
        "tail",
        "wc",
        "which",
    }
)
_GIT_PREFIXES = frozenset(
    {
        "diff",
        "log",
        "rev-parse",
        "show",
        "status",
    }
)
_TWO_TOKEN_PREFIXES = {
    "cargo": frozenset({"check", "clippy", "test"}),
    "go": frozenset({"test", "vet"}),
}


def _has_shell_composition(command: str) -> str | None:
    """Return the first unquoted shell feature that changes composition."""
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote == "'":
            if char == "'":
                quote = None
            index += 1
            continue
        if quote == '"':
            if char == '"':
                quote = None
            elif char == "`":
                return "backtick command substitution"
            elif char == "$" and index + 1 < len(command) and command[index + 1] == "(":
                return "dollar command substitution"
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "`":
            return "backtick command substitution"
        elif char == "$" and index + 1 < len(command) and command[index + 1] == "(":
            return "dollar command substitution"
        elif char in {";", "|", "&", "<", ">", "\n", "\r"}:
            return f"shell composition token {char!r}"
        index += 1
    if quote is not None or escaped:
        return "unterminated shell quoting"
    return None


@lru_cache(maxsize=1024)
def classify_command(command: str) -> PrefixVerdict:
    """Classify a command into a stable prefix, injection marker, or none."""
    command = (command or "").strip()
    if not command:
        return PrefixVerdict(PrefixKind.NONE, reason="empty command")
    composition = _has_shell_composition(command)
    if composition:
        return PrefixVerdict(PrefixKind.INJECTION, reason=composition)
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        return PrefixVerdict(PrefixKind.NONE, reason=f"cannot parse command: {exc}")
    if not argv:
        return PrefixVerdict(PrefixKind.NONE, reason="empty command")
    if "=" in argv[0] and not argv[0].startswith(("./", "/")):
        return PrefixVerdict(PrefixKind.NONE, reason="environment assignment prefix")

    executable = os.path.basename(argv[0])
    if executable in _SIMPLE_PREFIXES:
        return PrefixVerdict(PrefixKind.PREFIX, executable, "known simple command")
    if executable == "git" and len(argv) > 1 and argv[1] in _GIT_PREFIXES:
        return PrefixVerdict(
            PrefixKind.PREFIX, f"git {argv[1]}", "known git read command"
        )
    if (
        executable in _TWO_TOKEN_PREFIXES
        and len(argv) > 1
        and argv[1] in _TWO_TOKEN_PREFIXES[executable]
    ):
        return PrefixVerdict(
            PrefixKind.PREFIX,
            f"{executable} {argv[1]}",
            "known verification command",
        )
    if executable == "uv" and len(argv) > 2 and argv[1] == "run":
        nested = os.path.basename(argv[2])
        if nested in {"pytest", "ruff"}:
            return PrefixVerdict(
                PrefixKind.PREFIX,
                f"uv run {nested}",
                "known project verification command",
            )
    if executable in {"pytest", "ruff"}:
        return PrefixVerdict(
            PrefixKind.PREFIX, executable, "known project verification command"
        )
    return PrefixVerdict(PrefixKind.NONE, reason="no stable allowlist prefix")
