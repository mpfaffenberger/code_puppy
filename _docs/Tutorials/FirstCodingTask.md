# Tutorial: Your First Coding Task

## What You'll Build

In this tutorial, you'll use Code Puppy to build a small but complete Python utility — a to-do list manager that reads and writes tasks to a file. Along the way, you'll learn how to:

- Ask Code Puppy to create files from scratch
- Review the code it generates
- Request modifications and improvements
- Run and test your code
- Use slash commands to stay in control

By the end, you'll have a working command-line to-do app and a solid feel for how to collaborate with Code Puppy on real projects.

## Before You Begin

**Time needed:** ~15 minutes

**You'll need:**
- Code Puppy installed and working (see [Installation](../Getting-Started/Installation))
- At least one AI model configured (see [Configuration](../Getting-Started/Configuration))
- A folder where you're comfortable creating files

**You should already know:**
- How to launch Code Puppy (`uvx code-puppy -i`) — covered in [Quick Start](../Getting-Started/QuickStart)
- Basic terminal navigation (`cd`, `ls`)

## The Scenario

You want a simple command-line to-do list tool. It should let you add tasks, list them, and mark them as done — all from the terminal. Instead of writing this from scratch, you'll pair with Code Puppy to build it step by step.

## Step 1: Set Up Your Workspace

Open your terminal and create a fresh directory for this tutorial:

```bash
mkdir todo-app && cd todo-app
```

Now launch Code Puppy in interactive mode:

```bash
uvx code-puppy -i
```

You should see the Code Puppy banner and a prompt:

```
🐶 Code Puppy ready! Type your request or /help for commands.
>
```

> [!TIP]
> If the onboarding wizard appears (first-time users), follow the slides to select your AI provider, then continue here.

**What happened:** You've launched Code Puppy inside your project folder. Everything Code Puppy creates will go here.

## Step 2: Create the Core Module

Type this prompt:

```
Create a Python file called todo.py with a simple to-do list manager. It should:
- Store tasks in a JSON file called tasks.json
- Support adding a task
- Support listing all tasks
- Support marking a task as done by its number
- Use a simple command-line interface with argparse
```

Code Puppy will generate the file and show you the code as it writes it.

**What happened:** Code Puppy analyzed your requirements, wrote the Python code, and saved it to `todo.py` in your current directory. You'll see the file contents displayed in the terminal with syntax highlighting.

> [!NOTE]
> The exact code may vary depending on your AI model, but the structure will be similar — an argparse-based CLI with functions for add, list, and done operations.

## Step 3: Test It Out

Ask Code Puppy to run your new tool:

```
Run todo.py with the "add" command to add a task called "Buy groceries"
```

Code Puppy will construct and execute the correct command. You should see output like:

```
✅ Added task: Buy groceries
```

Now add a couple more tasks:

```
Add two more tasks: "Write documentation" and "Review pull request"
```

**What happened:** Code Puppy ran the shell commands to add tasks. Each task was stored in `tasks.json`.

> [!TIP]
> If YOLO mode is enabled (the default), Code Puppy runs commands automatically. If you've turned it off, you'll be asked to confirm each command before it runs.

## Step 4: List Your Tasks

Now ask to see what you have:

```
List all my tasks
```

You should see output like:

```
1. [ ] Buy groceries
2. [ ] Write documentation
3. [ ] Review pull request
```

**What happened:** Code Puppy ran the list command and displayed your tasks with their status.

## Step 5: Mark a Task as Done

Let's complete one:

```
Mark task 1 as done
```

Expected output:

```
✅ Marked task 1 as done: Buy groceries
```

List the tasks again to confirm:

```
List tasks again
```

```
1. [x] Buy groceries
2. [ ] Write documentation
3. [ ] Review pull request
```

**What happened:** The first task now shows as completed. The change was persisted to `tasks.json`.

## Step 6: Request an Improvement

Here's where Code Puppy really shines — iterating on existing code. Ask for an enhancement:

```
Update todo.py to add a "remove" command that deletes a task by its number. Also add color output using ANSI codes — show completed tasks in green and pending tasks in yellow.
```

Code Puppy will read the existing file, understand its structure, and apply the changes. You'll see a diff showing exactly what was added and modified.

**What happened:** Code Puppy modified `todo.py` in place, adding the new feature while preserving everything that already worked. The diff view lets you review exactly what changed.

> [!TIP]
> Be specific about what you want changed. Instead of "make it better," describe the feature or behavior you need. Code Puppy works best with clear instructions.

## Step 7: Test the Enhancement

Test the new remove command:

```
Remove task 1 (Buy groceries) from the list and then show all remaining tasks
```

You should see the task removed and the remaining tasks renumbered:

```
1. [ ] Write documentation
2. [ ] Review pull request
```

**What happened:** Code Puppy ran the remove command and verified the result by listing the remaining tasks.

## Step 8: Add a README

Finish the project with documentation:

```
Create a README.md for this project. Include a description, installation instructions (just "requires Python 3.11+"), and usage examples for all commands: add, list, done, and remove.
```

Code Puppy will create a professional `README.md` with proper Markdown formatting.

**What happened:** You now have a complete, documented mini-project — built entirely through conversation with Code Puppy.

## Step 9: Review Your Work

Use the `/ls` command to see what Code Puppy created:

```
/ls
```

You should see:

```
todo.py
tasks.json
README.md
```

Three files, a working tool, and documentation — all built in a few minutes.

## Bonus: Explore Useful Commands

Before wrapping up, try a few helpful slash commands:

| Command | What to Try | What It Does |
|---------|-------------|---------------|
| `/help` | `/help` | See all available commands |
| `/clear` | `/clear` | Clear the conversation and start fresh |
| `/compact` | `/compact` | Summarize your conversation to free up context space |
| `/agent` | `/agent` | See available agents — try the Planning Agent for complex projects |
| `/model` | `/model` | Switch to a different AI model |
| `/save` | `/save` | Save your session to resume later |

## Final Result

You've built a complete command-line to-do app with:
- ✅ Add, list, complete, and remove tasks
- ✅ Persistent storage in JSON
- ✅ Color-coded output
- ✅ A README with usage instructions

All through natural conversation — no copy-pasting from Stack Overflow required.

## What You Learned

- **Creating files**: Describe what you want, and Code Puppy writes the code
- **Running code**: Ask Code Puppy to execute commands and it handles the details
- **Iterating**: Request changes to existing code and review the diffs
- **Slash commands**: Use `/help`, `/clear`, `/compact`, `/ls`, and others to stay in control
- **Being specific**: The more detail you provide in your prompts, the better the results

## Next Steps

- [Tutorial: Planning a Multi-File Project](PlanningProject) — Use the Planning Agent to tackle bigger projects
- [How to Switch and Use Agents](../Guides/UseAgents) — Explore specialized agents for review, security, and more
- [How to Use MCP Servers](../Guides/MCPServers) — Add integrations like GitHub, databases, and Slack
- [Slash Commands Reference](../Reference/Commands) — The complete list of commands
- [How to Manage Sessions](../Guides/ManageSessions) — Save and resume your work
