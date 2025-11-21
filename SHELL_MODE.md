# 🐚 Interactive Shell Mode

Code Puppy now supports context switching between the AI assistant and an interactive shell!

## Usage

### Enter Interactive Shell Mode

Simply type `/shell` with no arguments:

```bash
>>> /shell
```

You'll see:

```
🐚 Entering Interactive Shell Mode
Type commands directly. Use 'exit', 'quit', or '/back' to return to Code Puppy.
Working directory: ~/dev/code_puppy

shell ~/dev/code_puppy $ 
```

### Execute Commands

Now you're in shell mode! Execute any command:

```bash
shell ~/dev/code_puppy $ ls -la
shell ~/dev/code_puppy $ git status
shell ~/dev/code_puppy $ cd src
shell ~/dev/code_puppy/src $ pwd
shell ~/dev/code_puppy/src $ cat somefile.py
```

### Return to Code Puppy

Type any of these to go back:

- `exit`
- `quit`
- `/back`
- Press `Ctrl+D`

```bash
shell ~/dev $ exit

🐶 Returning to Code Puppy mode

>>> # Back in Code Puppy!
```

## Single Command Mode (Original Behavior)

You can still execute a single command without entering interactive mode:

```bash
>>> /shell ls -la
# Executes command and returns to Code Puppy
```

Or use the shorthand:

```bash
>>> /! git status
```

## Features

- ✅ **Persistent directory changes**: `cd` commands persist across the session
- ✅ **Real-time output**: See command output as it happens
- ✅ **Command history**: Use arrow keys to navigate previous commands
- ✅ **Exit codes**: See when commands fail with exit codes
- ✅ **Ctrl+C handling**: Cancel current input without exiting
- ✅ **Current directory in prompt**: Always know where you are

## Why This Is Awesome

**Before:**
```bash
>>> /shell ls
>>> /shell cd src
>>> /shell ls
>>> /shell cat file.py
```

**Now:**
```bash
>>> /shell
shell $ ls
shell $ cd src
shell $ ls
shell $ cat file.py
shell $ exit
>>> # Back to AI mode!
```

No more typing `/shell` for every command! Just drop into a shell when you need it, do your thing, then bounce back to your AI buddy! 🐶

## Technical Details

- Built on top of Python's `subprocess` module
- Uses `prompt_toolkit` for enhanced input handling (falls back to basic `input()` if not available)
- Maintains working directory state across commands
- Runs in async context for smooth integration with Code Puppy's event loop

---

*Happy shell-ing! 🐚🐶*
