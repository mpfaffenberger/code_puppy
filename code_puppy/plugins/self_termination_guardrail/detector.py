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
import shlex
from collections.abc import Sequence


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
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


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


# Intentionally small: only wrappers whose option syntax we understand belong here.
_WRAPPERS = {"sudo", "env", "nice", "nohup", "time", "command"}
_SUDO_VALUE_OPTIONS = {"-u", "-g", "-h", "-p", "-r", "-t"}
_SUDO_LONG_VALUE_OPTIONS = { "--user", "--group", "--host", "--prompt", "--role", "--type",}


def _skip_assignments(tokens: Sequence[str], index: int) -> int:
    while index < len(tokens) and _ASSIGNMENT.fullmatch(tokens[index]):
        index += 1
    return index


def _skip_wrapper(tokens: Sequence[str], wrapper_index: int) -> int | None:
    """Return the index immediately after one recognized wrapper and its options."""
    wrapper = tokens[wrapper_index]
    index = wrapper_index + 1

    if wrapper == "sudo":
        return _skip_sudo_options(tokens, index)
    if wrapper == "env":
        return _skip_env_options(tokens, index)
    if wrapper == "nice":
        return _skip_nice_options(tokens, index)
    if wrapper == "command":
        while index < len(tokens) and tokens[index] in {"-p"}:
            index += 1
        return index

    # nohup and time options vary by implementation. ``--`` is universally
    # useful; otherwise leave the next token alone so it is treated as a command.
    if index < len(tokens) and tokens[index] == "--":
        return index + 1
    return index


def _skip_sudo_options(tokens: Sequence[str], index: int) -> int | None:
    while index < len(tokens):
        option = tokens[index]
        if option == "--":
            return index + 1
        if option in _SUDO_VALUE_OPTIONS or option in _SUDO_LONG_VALUE_OPTIONS:
            if index + 1 >= len(tokens):
                return None
            index += 2
        elif option.startswith("--") and "=" in option:
            index += 1
        elif option.startswith("-"):
            # Flags such as -n and bundled flags such as -nE need no value.
            index += 1
        else:
            return index
    return index


def _skip_env_options(tokens: Sequence[str], index: int) -> int | None:
    while index < len(tokens):
        option = tokens[index]
        if option == "--":
            return index + 1
        if option == "-u" or option == "--unset":
            if index + 1 >= len(tokens):
                return None
            index += 2
        elif option in {"-i", "--ignore-environment", "-0", "--null"}:
            index += 1
        elif _ASSIGNMENT.fullmatch(option):
            index += 1
        else:
            return index
    return index


def _skip_nice_options(tokens: Sequence[str], index: int) -> int | None:
    if index < len(tokens) and tokens[index] == "--":
        return index + 1
    if index < len(tokens) and tokens[index] in {"-n", "--adjustment"}:
        if index + 1 >= len(tokens):
            return None
        return index + 2
    return index


def find_command_executable(tokens: list[str]) -> tuple[set[str], set[str]]:
    """Return the executable and its arguments after supported shell wrappers.

    Both values are sets so callers can perform direct set intersections with
    the command and protected-process collections. An unrecognizable or empty
    command returns two empty sets.
    """
    index = _skip_assignments(tokens, 0)
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            continue
        if token not in _WRAPPERS:
            return {token}, set(tokens[index + 1 :])

        index = _skip_wrapper(tokens, index)
        if index is None:
            return set(), set()
        index = _skip_assignments(tokens, index)

    return set(), set()


COMMANDS = {"kill", "pkill", "killall", "taskkill", "stop-process", "spps"}

STATIC_PROTECTED_NAMES = { "code-puppy", "code_puppy", "code-puppy-venv", "$$", "$ppid", }

PROTECTED_NAMES = get_processes()

def detect_self_termination_command(command: str) ->  TerminationCommandMatch | None:
    #Normalize command to remove obfuscations and standardize separators
    norm_command = normalize_command(command)
    
    #Split commands on operators Ex: &&, ||, ;, &, \n
    subcommands = split_command(norm_command)

    for subcommand in subcommands:

        #Tokenize command
        try:
            tokens = [token.lower() for token in shlex.split(subcommand, posix=True)]
        except ValueError:
            return None

        # Find the executable separately from its arguments so quoted command
        # text and wrapper options cannot be mistaken for a command.
        executable, args = find_command_executable(tokens)
        matched_commands = executable & COMMANDS
        matched_names = {
            arg.removesuffix(".exe") for arg in args
        } & PROTECTED_NAMES

        if not (matched_commands and matched_names):
            continue

        return TerminationCommandMatch(
            pattern_name=(
                f"{', '.join(sorted(matched_commands))} targeting "
                f"{', '.join(sorted(matched_names))}"
            )
        )
    return None