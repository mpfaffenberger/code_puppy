# Windows Unicode Encoding Fix

## Problem

On Windows, the default console encoding is often **CP1252** (or CP437 in some regions) instead of UTF-8. This causes `UnicodeEncodeError` and `UnicodeDecodeError` when:

1. **Printing Unicode characters** (✓ ✅ ❌ ⚠ ➜ 📁 etc.) to stdout/stderr
2. **Reading subprocess output** from commands like ripgrep that output Unicode
3. **Command history** containing Unicode characters

### Error Examples:

```python
UnicodeEncodeError: 'charmap' codec can't encode character '\u2713' in position 0: character maps to <undefined>

UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d in position 322: character maps to <undefined>
```

## Root Cause

Windows console uses legacy encodings:
- **CP1252** (Western European)
- **CP437** (DOS OEM)
- **CP932** (Japanese Shift-JIS)
- etc.

These **cannot** represent Unicode characters outside their limited character set.

## Solution

We fixed this in three places:

### 1. Test Scripts (`test_windows_coordinates.py`)

**Replace Unicode symbols with ASCII:**
```python
# Before:
print("✓ Success")  # FAILS on Windows
print("❌ Error")   # FAILS on Windows

# After:
print("[OK] Success")  # Works everywhere
print("[X] Error")    # Works everywhere
```

**Force UTF-8 for stdout/stderr:**
```python
import sys
import io

if platform.system() == "Windows":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
```

### 2. Subprocess Calls (`file_operations.py`, `command_runner.py`)

**Add explicit UTF-8 encoding:**
```python
# Before:
result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

# After:
result = subprocess.run(
    cmd, 
    capture_output=True, 
    text=True, 
    encoding='utf-8',      # Force UTF-8 decoding
    errors='replace',      # Replace invalid chars instead of crashing
    timeout=30
)
```

### 3. Subprocess.Popen (`command_runner.py`)

```python
process = subprocess.Popen(
    command,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding='utf-8',      # Added
    errors='replace',      # Added
    ...
)
```

## Files Changed

### Test Scripts:
- ✅ `test_windows_coordinates.py` - UTF-8 wrapper + ASCII symbols

### Source Code:
- ✅ `code_puppy/tools/file_operations.py` - grep subprocess UTF-8
- ✅ `code_puppy/tools/command_runner.py` - Popen UTF-8 encoding

## Why This Works

### Option 1: ASCII Symbols (Safest)
```python
# These work EVERYWHERE without any encoding setup:
"[OK]" "[X]" "[!]" "[+]" "[-]" "->" "Files:" "Target:"
```

### Option 2: UTF-8 Wrapper (For Unicode support)
```python
# Wrap stdout/stderr to handle UTF-8:
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Now these work:
"✓" "✅" "❌" "⚠" "📁" "🎯"
```

### Option 3: Subprocess Encoding (For command output)
```python
# Explicitly decode subprocess output as UTF-8:
subprocess.run(..., encoding='utf-8', errors='replace')

# Handles ripgrep output, git output, etc. that contain Unicode
```

## Symbol Mapping (ASCII Equivalents)

For scripts that can't use UTF-8 wrapper:

| Unicode | ASCII | Meaning |
|---------|-------|--------|
| ✓ / ✅  | [OK]  | Success |
| ❌      | [X]   | Error |
| ⚠       | [!]   | Warning |
| ➜       | ->    | Arrow |
| 📁      | Files:| Files |
| 🎯      | Target:| Target |
| 📋      | Steps:| Steps |
| 🔍      | Search:| Search |
| 📸      | Image:| Screenshot |

## Testing

Run the test script on Windows:
```bash
python test_windows_coordinates.py
```

**Expected:** No encoding errors, all output displays correctly.

## Best Practices Going Forward

### For Internal Code (agents, tools):
✅ **Use Rich console** - It handles Unicode automatically:
```python
from rich.console import Console
console = Console()
console.print("[green]✅ Success![/green]")  # Works!
```

### For Test Scripts / Standalone Files:
✅ **Use ASCII symbols** for maximum compatibility:
```python
print("[OK] Test passed")  # Instead of "✅ Test passed"
```

### For Subprocess:
✅ **Always specify encoding**:
```python
subprocess.run(..., encoding='utf-8', errors='replace')
```

## Why Not Set PYTHONIOENCODING?

```bash
# This works but is unreliable:
export PYTHONIOENCODING=utf-8  # Unix
set PYTHONIOENCODING=utf-8     # Windows
```

**Problems:**
- Doesn't work if user's environment overrides it
- Doesn't work in all shells (PowerShell, cmd.exe behave differently)
- Doesn't work for subprocess output
- Requires user action

**Better:** Fix it in code so it works regardless of environment.

## Related Issues

- Windows CP1252/CP437 encoding limitations
- Ripgrep output containing Unicode
- Git output containing Unicode (branch names, commit messages)
- File paths with non-ASCII characters
- Command history with emojis/Unicode

## References

- [Python subprocess encoding documentation](https://docs.python.org/3/library/subprocess.html#subprocess.Popen)
- [Python TextIOWrapper documentation](https://docs.python.org/3/library/io.html#io.TextIOWrapper)
- [Windows Code Pages](https://learn.microsoft.com/en-us/windows/win32/intl/code-page-identifiers)

---

**Status:** ✅ Fixed  
**Affects:** Windows users only  
**Impact:** All subprocess output and Unicode symbols now work correctly on Windows
