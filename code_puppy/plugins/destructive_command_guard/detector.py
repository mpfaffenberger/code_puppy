"""Pattern detection for destructive shell commands.

Detects dangerous patterns in shell commands using pure regex — no LLM
calls, no caching, no yolo-mode checks. Covers:
- Unix/Linux: rm -rf root/home, SQL DROP via clients, docker prune, accidental package publishes
- Windows PowerShell: Remove-Item, rmdir, del, Format-Volume, Clear-Disk, registry operations
- Windows CMD: rd, rmdir, del, erase with /s /q flags, format, diskpart
The patterns are defined in patterns directory as JSON files and loaded at load time
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass
from collections.abc import Sequence
import shlex


@dataclass
class DestructiveCommandMatch:
    """Result of a destructive command pattern match."""

    pattern_name: str
    description: str
    block_immediately: bool


class SearchGroup:
    def __init__(
        self,
        name: str,
        substrings: frozenset[str],
        patterns: tuple[tuple[re.Pattern, str, str, bool], ...],
    ):
        self.name = name
        self.cheap_substrings = substrings
        self.expensive_patterns = patterns


# Load data from JSON files inside patterns directory and compile regex patterns
def load_guardrails_data() -> list[SearchGroup]:
    data_dir = Path(__file__).parent / "patterns"
    json_files = sorted(data_dir.glob("*.json"))
    all_groups = []

    for data_path in json_files:
        try:
            with open(data_path, "r", encoding = "utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"Failed to parse guardrails data JSON: {e}") from e

        if "groups" not in data:
            print("groups not in data")
            raise KeyError(f"Guardrails file '{data_path.name}' is missing required top-level 'groups' key")

        for group_data in data["groups"]:
            try:   
                group = SearchGroup(
                    name=group_data["name"],
                    substrings=frozenset(
                        keyword.lower()
                        for keyword in group_data["cheap_substrings"]
                    ),
                    patterns=tuple(
                        (re.compile(pattern_info["regex"], re.IGNORECASE), pattern_info["name"], pattern_info["description"], pattern_info["block_immediately"])
                        for pattern_info in group_data["expensive_patterns"]
                    ),
                )
                all_groups.append(group)
            except KeyError as e:
                raise KeyError(f"Guardrails group '{group_data.get('name', '<unknown>')}' is missing required field: {e}")
            except re.error as e:
                raise ValueError(f"Invalid regex in guardrails group '{group_data.get('name', '<unknown>')}': {e}")
    
    if not all_groups:
        raise ValueError("No guardrails groups found in any JSON files")
    
    return all_groups


#regex pattern to split on
_CMD_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;|&|\|)\s*")

#Split a command string into subcommands based on shell operators.
def split_command(command: str) -> list[str]:
    return _CMD_SPLIT_RE.split(command)


# Regex patterns to remove simple obfuscations like empty quotes, backslash escapes, and caret escapes.
_EMPTY_QUOTES_RE     = re.compile(r"(['\"])\1")
_BACKSLASH_ESCAPE_RE = re.compile(r"\\(.)")
_QUOTED_WORD_RE      = re.compile(r'(["\'])(\w+)\1')
_CARET_ESCAPE_RE     = re.compile(r"\^(.?)")
_SEPARATOR_RE        = re.compile(r"[,\s]+")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")

def normalize_command(command: str) -> str:
    command = _EMPTY_QUOTES_RE.sub("", command)             # strip '' and ""
    command = _BACKSLASH_ESCAPE_RE.sub(r"\1", command)      # strip backslash escapes
    command = _CARET_ESCAPE_RE.sub(r"\1", command)          # strip caret escapes
    command = _QUOTED_WORD_RE.sub(r"\2", command)           # unquote words
    command = _SEPARATOR_RE.sub(" ", command)               # normalize all separators + whitespace
    return command

# Intentionally small: only wrappers whose option syntax we understand belong here.
_WRAPPERS = {"sudo", "env", "nice", "nohup", "time", "command"}
_SUDO_VALUE_OPTIONS = {"-u", "-g", "-h", "-p", "-r", "-t"}
_SUDO_LONG_VALUE_OPTIONS = {
    "--user",
    "--group",
    "--host",
    "--prompt",
    "--role",
    "--type",
}

"""
Find Executable Logic
"""
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


def find_command_executable(tokens: list[str]) -> set[str]:
    """Return the executable after supported shell wrappers.

    The executable is returned as a set so callers can intersect it directly
    with known command names. An unrecognizable or empty command returns an
    empty set.
    """
    index = _skip_assignments(tokens, 0)
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            continue
        if token not in _WRAPPERS:
            return {token}

        index = _skip_wrapper(tokens, index)
        if index is None:
            return set()
        index = _skip_assignments(tokens, index)

    return set()


"""
Detect Destructive Command Pipeline
"""
GLOBAL_PATTERNS: list[SearchGroup] | None = None


def detect_destructive_command(command: str) ->  DestructiveCommandMatch | None:
    """
    Sends command through pipeline of checks to determine if it is malicious
    - Receives command: string
    - Returns: DestructiveCommandMatch if a destructive pattern is found
    - Returns: None if no destructive patterns are found
    """

    global GLOBAL_PATTERNS
    if GLOBAL_PATTERNS is None:
        try:
            GLOBAL_PATTERNS = load_guardrails_data()
        except Exception as e:
            return DestructiveCommandMatch(
                pattern_name = "Failed to load JSON data",
                description = "The data inside of /plugins/destructive_command_guardrail/patterns is corrupted or wrong. Please fix this issue to run commands",
                block_immediately = True
            )

    #Normalize command to remove obfuscations and standardize separators
    norm_command = normalize_command(command)

    #Split commands on operators Ex: &&, ||, ;, &, \n
    subcommands = split_command(norm_command)

    #Check each subcommand for malicious keywords and patterns, return first match found
    for subcommand in subcommands:
        # Tokenize command
        try:
            tokens = [token.lower() for token in shlex.split(subcommand, posix=True)]
        except ValueError:
            return None

        #Find executable
        executable = find_command_executable(tokens)

        found_groups = set()
        for group in GLOBAL_PATTERNS:
            if(group.cheap_substrings & executable):
                found_groups.update(group.expensive_patterns)

        #If no keywords are found, skip expensive regex checks for this subcommand
        if not found_groups:
            continue
        # Use expensive regex patterns to check for destructive commands, return first match found
        for pattern, name, description, block_immediately in found_groups:
            if pattern.search(norm_command):
                return DestructiveCommandMatch(pattern_name=name, description=description, block_immediately=block_immediately)

    #If all checks pass and no malicious patterns are found return None
    return None