"""Pattern detection for self termination shell commands.

Detects dangerous patterns in shell commands using pure regex — no LLM
calls, no caching, no yolo-mode checks. Covers:
- Unix/Linux: kill, pkill, killall
- MacOS: kill, pkill, killall
- Windows CMD: taskkill, Stop-Process, kill, spps
"""

import re
import psutil
from dataclasses import dataclass


@dataclass
class TerminationCommandMatch:
    """Result of a self termination command pattern match."""

    pattern_name: str
    description: str = "This command can terminate the code-puppy process or parent process"
    block_immediately: bool = True


#regex pattern to split on
_CMD_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;|&)\s*")

#Split a command string into subcommands based on shell operators.
def split_command(command: str) -> list[str]:
    return _CMD_SPLIT_RE.split(command)
    

# Regex patterns to remove simple obfuscations like empty quotes, backslash escapes, and caret escapes.
_EMPTY_QUOTES_RE     = re.compile(r"(['\"])\1")
_BACKSLASH_ESCAPE_RE = re.compile(r"\\(.)")
_QUOTED_WORD_RE      = re.compile(r'(["\'])(\w+)\1')
_CARET_ESCAPE_RE     = re.compile(r"\^(.?)")
_SEPARATOR_RE        = re.compile(r"[,;\s]+")
_TOKEN_RE            = re.compile(r"\b\w+(?:-\w+)*\b")

STATIC_PROTECTED_NAMES = {
    "code-puppy",
    "code_puppy",
    "code-puppy-venv",
}

def normalize_command(command: str) -> str:
    command = _EMPTY_QUOTES_RE.sub("", command)             # strip '' and ""
    command = _BACKSLASH_ESCAPE_RE.sub(r"\1", command)      # strip backslash escapes
    command = _CARET_ESCAPE_RE.sub(r"\1", command)          # strip caret escapes
    command = _QUOTED_WORD_RE.sub(r"\2", command)           # unquote words
    command = _SEPARATOR_RE.sub(" ", command)               # normalize all separators + whitespace
    return command


def _process_name_words(name: str) -> set[str]:
    """Return lowercase words from a process name."""
    return {match.group() for match in _TOKEN_RE.finditer(name.lower())}


def get_processes() -> set[str]:
    """Return current and parent process names/PIDs plus static aliases.

    Example shape:
        {"python3", "12345", "zsh", "23456", "launchd", "1"}

    Note: sets are unordered, so this does not preserve name/PID pairing.
    """
    processes: set[str] = set(STATIC_PROTECTED_NAMES)
    process = psutil.Process()

    while process is not None:
        try:
            processes.update(_process_name_words(process.name()))
            processes.add(str(process.pid))
            process = process.parent()
        except psutil.NoSuchProcess:
            break
        except (psutil.AccessDenied, psutil.ZombieProcess):
            processes.add(str(process.pid))
            break

    return processes


def get_quoted_regions(text: str) -> list[tuple[int, int]]:
    regions = []
    i = 0
    while i < len(text):
        if text[i] in ('"', "'"):
            quote_char = text[i]
            start = i
            i += 1
            while i < len(text):
                if text[i] == '\\':
                    i += 2
                elif text[i] == quote_char:
                    regions.append((start, i))
                    break
                else:
                    i += 1
        i += 1
    return regions


def both_in_same_quote(text: str, cmd_pos: int, name_pos: int) -> bool:
    for start, end in get_quoted_regions(text):
        if start < cmd_pos and name_pos < end:
            return True
    return False


def check_window(tokens: list, candidate_commands: set, candidate_names: set, window: int = 5) -> tuple[set, set, int | None, int | None]:
    matched_commands = set()
    matched_names = set()
    cmd_idx = None
    name_idx = None

    for i, token in enumerate(tokens):
        if token in candidate_commands:
            lo = i + 1
            hi = min(len(tokens), i + window + 1)

            for j in range(lo, hi):
                if tokens[j] in candidate_names:
                    matched_commands.add(token)
                    matched_names.add(tokens[j])
                    if cmd_idx is None:
                        cmd_idx = i
                        name_idx = j

    return matched_commands, matched_names, cmd_idx, name_idx


COMMANDS = {"kill", "pkill", "killall", "taskkill", "stop-process", "spps"}

PROTECTED_NAMES = get_processes()

def detect_self_termination_command(command: str) ->  TerminationCommandMatch | None:

    #Normalize command to remove obfuscations and standardize separators
    command = normalize_command(command)

    #Split commands on operators Ex: &&, ||, ;, &, \n
    subcommands = split_command(command)

    for subcommand in subcommands:
        token_matches = list(_TOKEN_RE.finditer(subcommand.lower()))
        tokens = [m.group() for m in token_matches]
        token_set = set(tokens)

        candidate_commands = token_set & COMMANDS
        candidate_names = token_set & PROTECTED_NAMES

        if not(candidate_commands and candidate_names):
            continue

        matched_commands, matched_names, cmd_idx, name_idx = check_window(tokens, candidate_commands, candidate_names)

        if not(matched_commands and matched_names):
            continue

        if both_in_same_quote(subcommand, token_matches[cmd_idx].start(), token_matches[name_idx].start()):
            continue

        return TerminationCommandMatch(
            pattern_name=f"{', '.join(sorted(matched_commands))} targeting {', '.join(sorted(matched_names))}"
        )
    return None