# Installation

## Overview
This guide walks you through installing Code Puppy on your system. By the end, you'll have Code Puppy ready to launch from your terminal.

## Prerequisites

> [!NOTE]
> Before you begin, make sure you have:
> - **Python 3.11 or later** (3.11, 3.12, or 3.13)
> - A terminal or command prompt
> - At least one AI provider API key (e.g., OpenAI, Anthropic, Google Gemini, Cerebras) — or you can configure one during the onboarding wizard

## Install with UV (Recommended)

[UV](https://docs.astral.sh/uv/) is a fast Python package manager. Using `uvx` lets you run Code Puppy without installing it permanently — it creates an isolated environment automatically.

### macOS / Linux

**Step 1: Install UV** (skip if you already have it)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Step 2: Launch Code Puppy**

```bash
uvx code-puppy
```

That's it! UV downloads and runs Code Puppy in one step. On your first launch, the onboarding wizard will guide you through initial setup.

### Windows

**Step 1: Install UV** (run in PowerShell as Administrator)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Step 2: Launch Code Puppy**

```powershell
uvx code-puppy
```

> [!TIP]
> On Windows, you can also install Code Puppy as a global tool for the best experience with keyboard shortcuts (Ctrl+C / Ctrl+X cancellation):
> ```powershell
> uv tool install code-puppy
> code-puppy
> ```

## Install with pip

If you prefer pip, you can install Code Puppy into any Python 3.11+ environment:

```bash
pip install code-puppy
```

Then run it:

```bash
code-puppy
```

## Launch Options

Code Puppy provides two command aliases — you can use either one:

| Command | Description |
|---------|-------------|
| `code-puppy` | Full command name |
| `pup` | Short alias — same thing, fewer keystrokes |

### Interactive Mode

Launch directly into interactive mode (recommended for most use):

```bash
uvx code-puppy -i
```

### Single Prompt Mode

Run a single prompt and exit:

```bash
uvx code-puppy -p "Create a hello world Python script"
```

### Specify a Model or Agent

```bash
# Use a specific model
uvx code-puppy -m gpt-5 -i

# Use a specific agent
uvx code-puppy -a code-puppy -i
```

### Check Version

```bash
uvx code-puppy --version
```

## Verify It's Working

Run Code Puppy in interactive mode:

```bash
uvx code-puppy -i
```

You should see:
- The Code Puppy banner with ASCII art
- The onboarding wizard (on first launch)
- A prompt waiting for your input

Type simple request to confirm everything works:

```
What files are in the current directory?
```

Code Puppy should list the files and respond. You're all set!

## Common Issues

| Problem | Solution |
|---------|----------|
| `command not found: uvx` | UV isn't installed or isn't on your PATH. Re-run the UV install script and restart your terminal. |
| `Python 3.11+ required` | Upgrade your Python installation. Code Puppy requires Python 3.11, 3.12, or 3.13. |
| `Permission denied` on macOS/Linux | Try running the UV install script without `sudo`. UV installs to your home directory. |
| Code Puppy starts but can't complete tasks | You likely need to configure an API key. See [Initial Configuration](Configuration). |
| Slow first launch | The first run downloads dependencies. Subsequent launches are much faster. |
| Ctrl+C doesn't cancel on Windows (via uvx) | Install as a global tool instead: `uv tool install code-puppy`, then run with `code-puppy`. |

## Updating Code Puppy

If you use `uvx`, you always get the latest version automatically. To force an update:

```bash
uvx --upgrade code-puppy
```

If you installed with pip:

```bash
pip install --upgrade code-puppy
```

## Uninstalling

If installed as a UV tool:

```bash
uv tool uninstall code-puppy
```

If installed with pip:

```bash
pip uninstall code-puppy
```

Code Puppy stores configuration in `~/.code_puppy/`. Remove that directory to completely clean up:

```bash
rm -rf ~/.code_puppy
```

## Next Steps

- [Initial Configuration](Configuration) — Set up your API keys and preferences
- [Quick Start Tutorial](QuickStart) — Complete your first coding task
