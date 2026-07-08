"""Pattern detection for destructive shell commands.

Detects dangerous patterns in shell commands using pure regex — no LLM
calls, no caching, no yolo-mode checks. Covers:
- Unix/Linux: rm -rf root/home, SQL DROP via clients, docker prune, accidental package publishes
- Windows PowerShell: Remove-Item, rmdir, del, Format-Volume, Clear-Disk, registry operations
- Windows CMD: rd, rmdir, del, erase with /s /q flags, format, diskpart
- Netsh firewall commands that disable the firewall or open ports
The patterns are defined in SON fia Jle (patterns.json) and loaded at first call
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass


@dataclass
class DestructiveCommandMatch:
    """Result of a destructive command pattern match."""

    pattern_name: str
    description: str

class SearchGroup:
    def __init__(self, name: str, substrings: tuple[str], patterns: tuple[str]):
        self.name = name
        self.cheap_substrings = substrings
        self.expensive_patterns = patterns

# Load data from JSON file and compile regex patterns
def load_guardrails_data() -> list[SearchGroup]:
    data_path = Path(__file__).parent / "patterns.json"
    try:
        with open(data_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Guardrails data file not found at {data_path}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse guardrails data JSON: {e}") from e

    groups = []
    for group_data in data["groups"]:
        try:
            group = SearchGroup(
                name=group_data["name"],
                substrings=tuple(group_data["cheap_substrings"]),
                patterns=tuple(
                    (re.compile(pattern_info["regex"], re.MULTILINE | re.IGNORECASE), pattern_info["name"], pattern_info["description"])
                    for pattern_info in group_data["expensive_patterns"]
                ),
            )
            groups.append(group)
        except KeyError as e:
            raise KeyError(f"Guardrails group '{group_data.get('name', '<unknown>')}' is missing required field: {e}")
        except re.error as e:
            raise ValueError(f"Invalid regex in guardrails group '{group_data.get('name', '<unknown>')}': {e}")

    return groups

#regex pattern to split on
_CMD_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;|&)\s*")

#Split a command string into subcommands based on shell operators.
def split_command(command: str) -> list[str]:
    try:
        subcommands = _CMD_SPLIT_RE.split(command)
        return subcommands
    except ValueError:
        # If the command can't be parsed, treat it as a single command
        return [command]


# Regex patterns to remove simple obfuscations like empty quotes, backslash escapes, and caret escapes.
_EMPTY_QUOTES_RE     = re.compile(r"(['\"])\1")
_BACKSLASH_ESCAPE_RE = re.compile(r"\\(.)")
_QUOTED_WORD_RE      = re.compile(r'(["\'])(\w+)\1')
_CARET_ESCAPE_RE     = re.compile(r"\^(.?)")
_SEPARATOR_RE        = re.compile(r"[,;\s]+")

def normalize_command(command: str) -> str:
    command = _EMPTY_QUOTES_RE.sub("", command)             # strip '' and ""
    command = _BACKSLASH_ESCAPE_RE.sub(r"\1", command)      # strip backslash escapes
    command = _CARET_ESCAPE_RE.sub(r"\1", command)          # strip caret escapes
    command = _QUOTED_WORD_RE.sub(r"\2", command)           # unquote words
    command = _SEPARATOR_RE.sub(" ", command)               # normalize all separators + whitespace
    return command


GLOBAL_PATTERNS: list[SearchGroup] = []


def detect_destructive_command(command: str) ->  DestructiveCommandMatch | None:
    """
    Sends command through pipeline of checks to determine if it is malicious
    - Receives command: string
    - Returns: DestructiveCommandMatch if a destructive pattern is found
    - Returns: None if no destructive patterns are found
    """

    global GLOBAL_PATTERNS

    if GLOBAL_PATTERNS == []:
        GLOBAL_PATTERNS = load_guardrails_data()
    
    #Split commands on operators Ex: &&, ||, ;, &, \n
    subcommands = split_command(command)

    #Check each subcommand for malicious keywords and patterns, return first match found
    for subcommand in subcommands:
        found_groups = set()
        subcommand = normalize_command(subcommand)
        lower_subcommand = subcommand.lower()
        for group in GLOBAL_PATTERNS:
            for substring in group.cheap_substrings:
                if substring in lower_subcommand:
                    found_groups.update(group.expensive_patterns)

        #If no keywords are found, skip expensive regex checks for this subcommand
        if not found_groups:
            print("didnt find a keyword") #cleanup
            continue
        print("found a key word") #cleanup
        # Use expensive regex patterns to check for destructive commands, return first match found
        for pattern, name, description in found_groups:
            if pattern.search(subcommand):
                return DestructiveCommandMatch(pattern_name=name, description=description)

    #If all checks pass and no malicious patterns are found return None
    return None