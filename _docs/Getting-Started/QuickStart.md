# Quick Start Tutorial

## What You'll Achieve

In about 5 minutes, you'll launch Code Puppy, send it your first coding task, and see it create, modify, and run code — all from your terminal.

## Before You Begin

**Time needed:** ~5 minutes

**You'll need:**
- Code Puppy installed (see [Installation](Installation))
- An AI model configured (see [Initial Configuration](Configuration))

## Step 1: Launch Code Puppy

Open your terminal, navigate to a project directory (or any folder you'd like to work in), and launch Code Puppy in interactive mode:

```bash
uvx code-puppy -i
```

> [!TIP]
> You can also use the shorter alias: `uvx pup -i`

You should see the Code Puppy banner and a prompt waiting for your input:

```
🐶 Code Puppy ready! Type your request or /help for commands.
>
```

If this is your very first launch, the onboarding wizard will appear first. Follow the slides to pick your model provider, then press Enter on the final slide to start coding.

## Step 2: Ask Code Puppy to Create a File

Type a simple request at the prompt:

```
Create a Python file called hello.py that prints "Hello from Code Puppy!"
```

**What happens:** Code Puppy reads your request, generates the code, and writes it to `hello.py` in your current directory. You'll see the file content displayed as it's created.

## Step 3: Run Your Code

Now ask Code Puppy to run it:

```
Run hello.py
```

**What happens:** Code Puppy executes the file and shows you the output:

```
Hello from Code Puppy!
```

> [!NOTE]
> If **YOLO mode** is enabled (the default), Code Puppy runs shell commands automatically. If you've disabled YOLO mode, it will ask for your confirmation before running each command.

## Step 4: Ask for a Modification

Let's make the code more interesting:

```
Update hello.py to accept a name as a command-line argument and greet that person. If no name is given, default to "World".
```

**What happens:** Code Puppy modifies the existing file, adding argument parsing. You'll see a diff of what changed.

## Step 5: Test the Changes

```
Run hello.py with the argument "Buddy"
```

Expected output:

```
Hello, Buddy!
```

## Step 6: Explore Useful Commands

Code Puppy has slash commands for common tasks. Try these:

| Command | What It Does |
|---------|--------------|
| `/help` | Show all available commands |
| `/model` | Switch to a different AI model |
| `/agent` | Switch between agents (e.g., Planning Agent for complex tasks) |
| `/show` | Display your current configuration |
| `/cd <dir>` | Change your working directory |
| `/clear` | Clear the conversation and start fresh |
| `/tutorial` | Re-run the onboarding tutorial |

Try typing `/help` now to see the full list of commands.

## Step 7: Try a Real-World Task

Now try something more useful in your own project. Navigate to a project directory and ask Code Puppy to help:

```
/cd ~/my-project
```

Then try prompts like:

- *"Explain what this project does"*
- *"Find and fix any bugs in the main module"*
- *"Write unit tests for the utils module"*
- *"Add a README.md for this project"*

> [!TIP]
> **Be specific.** Instead of "improve this code," say "add error handling to the file-reading function and log any exceptions." The more detail you give, the better the results.

## What You Learned

- How to launch Code Puppy in interactive mode
- How to ask Code Puppy to create and modify files
- How to run code through Code Puppy
- Essential slash commands for navigation and control
- Tips for writing effective prompts

## Next Steps

- [How to Switch Models](../Guides/SwitchModels) — Try different AI models for different tasks
- [How to Switch and Use Agents](../Guides/UseAgents) — Use the Planning Agent for complex, multi-step projects
- [How to Use MCP Servers](../Guides/MCPServers) — Add integrations like GitHub, databases, and more
- [Slash Commands Reference](../Reference/Commands) — Full list of all available commands
- [FAQ & Troubleshooting](../FAQ) — Common questions and fixes
