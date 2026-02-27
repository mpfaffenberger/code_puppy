#!/usr/bin/env python3
import json
import os
import re
import sys

WRAPPERS = {"sudo", "env", "nohup", "xargs", "time"}

try:
    data = json.load(sys.stdin)
    cmd = data.get("tool_input", {}).get("command", "")
    if not isinstance(cmd, str):
        sys.exit(0)
except Exception:
    sys.exit(2)  # non-blocking error feedback rather than silent allow

if not cmd:
    sys.exit(0)

# Fallback: catch `bash -c "... sed ..."` and subshell/delegation cases.
# Only match 'sed' when preceded by whitespace or start-of-string (not inside paths).
if re.search(r"(?:^|\s)sed\b", cmd):
    print(
        "[BLOCKED] sed usage detected. Use the built-in edit_file / read_file tools to modify files instead.",
        file=sys.stderr,
    )
    sys.exit(1)

# Split by command separators (;, &&, ||, |) to check each segment
parts = re.split(r"[;&|]+", cmd)
for part in parts:
    tokens = part.strip().split()
    if not tokens:
        continue

    # Skip wrapper binaries, their flags, and KEY=VALUE env assignments
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in WRAPPERS:
            i += 1
        elif t.startswith("-") or "=" in t:
            i += 1
        else:
            break
    prog = tokens[i] if i < len(tokens) else ""

    if os.path.basename(prog) == "sed":
        print(
            "[BLOCKED] sed is not allowed. Use the built-in edit_file / read_file tools to modify files instead.",
            file=sys.stderr,
        )
        sys.exit(1)

sys.exit(0)
