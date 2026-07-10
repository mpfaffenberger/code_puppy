"""Pattern detection for destructive shell commands.

Detects dangerous patterns in shell commands using pure regex — no LLM
calls, no caching, no yolo-mode checks. Covers:
- Unix/Linux: rm -rf root/home, SQL DROP via clients, docker prune, accidental package publishes
- Windows PowerShell: Remove-Item, rmdir, del, Format-Volume, Clear-Disk, registry operations
- Windows CMD: rd, rmdir, del, erase with /s /q flags, format, diskpart
The patterns are defined in patterns directory as JSON files and loaded at first call
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
    def __init__(self, name: str, substrings: tuple[str], patterns: tuple[tuple[re.Pattern, str, str], ...]):
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
            raise KeyError(f"Guardrails file '{data_path.name}' is missing required top-level 'groups' key")

        for group_data in data["groups"]:
            try:   
                group = SearchGroup(
                    name=group_data["name"],
                    substrings=tuple(group_data["cheap_substrings"]),
                    patterns=tuple(
                        (re.compile(pattern_info["regex"], re.IGNORECASE), pattern_info["name"], pattern_info["description"])
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
    else:      
        return all_groups

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

def normalize_command(command: str) -> str:
    command = _EMPTY_QUOTES_RE.sub("", command)             # strip '' and ""
    command = _BACKSLASH_ESCAPE_RE.sub(r"\1", command)      # strip backslash escapes
    command = _CARET_ESCAPE_RE.sub(r"\1", command)          # strip caret escapes
    command = _QUOTED_WORD_RE.sub(r"\2", command)           # unquote words
    command = _SEPARATOR_RE.sub(" ", command)               # normalize all separators + whitespace
    return command


GLOBAL_PATTERNS: list[SearchGroup] = None


def detect_destructive_command(command: str) ->  DestructiveCommandMatch | None:
    """
    Sends command through pipeline of checks to determine if it is malicious
    - Receives command: string
    - Returns: DestructiveCommandMatch if a destructive pattern is found
    - Returns: None if no destructive patterns are found
    """

    global GLOBAL_PATTERNS

    if GLOBAL_PATTERNS is None:
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
            continue
        # Use expensive regex patterns to check for destructive commands, return first match found
        for pattern, name, description in found_groups:
            if pattern.search(subcommand):
                return DestructiveCommandMatch(pattern_name=name, description=description)

    #If all checks pass and no malicious patterns are found return None
    return None