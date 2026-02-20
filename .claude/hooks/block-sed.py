#!/usr/bin/env python3
import sys, json, re

try:
    data = json.load(sys.stdin)
    cmd = data.get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)

if not cmd:
    sys.exit(0)

# Split by command separators (;, &&, ||, |) to check each segment
# This handles "echo hi; sed ..." correctly
parts = re.split(r'[;&|]+', cmd)

for part in parts:
    tokens = part.strip().split()
    if not tokens:
        continue
    
    # First token is the command name
    prog = tokens[0]
    
    # Also handle `sudo sed` or `env sed`
    if prog in ["sudo", "env", "nohup"] and len(tokens) > 1:
        prog = tokens[1]
        
    if prog == "sed":
        print("[BLOCKED] sed is not allowed. Use the built-in edit_file / read_file tools to modify files instead.", file=sys.stderr)
        sys.exit(1)

sys.exit(0)
