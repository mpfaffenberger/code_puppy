# How to Create Custom Commands

## What You'll Learn
By the end of this guide, you'll be able to create your own slash commands that send reusable prompts to the AI model.

## Prerequisites
- Code Puppy installed and working
- A project directory where you want to add custom commands

## Quick Version

1. Create a commands directory in your project:
   ```bash
   mkdir -p .claude/commands
   ```
2. Create a Markdown file — the filename becomes the command name:
   ```bash
   echo "Review this code for security vulnerabilities" > .claude/commands/security-review.md
   ```
3. Use it in Code Puppy:
   ```
   /security-review
   ```

That's it! The Markdown content is sent to the model as a prompt.

## Detailed Steps

### 1. Choose a Commands Directory

Code Puppy scans three directories in your project for custom command files:

| Directory | File Pattern | Best For |
|-----------|-------------|----------|
| `.claude/commands/` | `*.md` | General-purpose custom commands |
| `.github/prompts/` | `*.prompt.md` | GitHub-compatible prompt templates |
| `.agents/commands/` | `*.md` | Agent-specific commands |

Create whichever directory suits your workflow:

```bash
# Most common choice
mkdir -p .claude/commands

# If you also use GitHub Copilot prompts
mkdir -p .github/prompts

# For agent-related commands
mkdir -p .agents/commands
```

> [!TIP]
> You can use all three directories at once. Code Puppy loads commands from all of them.

### 2. Create a Command File

Create a Markdown file in your chosen directory. The **filename** (without `.md`) becomes the **command name**.

```bash
# Creates the command /review
cat > .claude/commands/review.md << 'EOF'
Review the code I've shared for:
- Correctness and potential bugs
- Performance issues
- Readability and maintainability
- Best practices for this language

Provide specific suggestions with code examples.
EOF
```

For `.github/prompts/`, use the `.prompt.md` extension:

```bash
# Creates the command /review
cat > .github/prompts/review.prompt.md << 'EOF'
Review this code for best practices and potential issues.
EOF
```

### 3. Use Your Custom Command

Start Code Puppy (or if it's already running, commands are picked up automatically). Type your command with a `/` prefix:

```
/review
```

You'll see:
```
📝 Executing markdown command: review
```

The full content of your Markdown file is sent to the model as a prompt.

### 4. Pass Additional Context

You can add extra text after the command name. It's appended to the prompt as "Additional context":

```
/review Focus especially on error handling in the auth module
```

This sends the model your full Markdown prompt **plus** the extra text you provided.

> [!TIP]
> This is great for commands that are templates — write the general instructions in the file, then add specifics each time you use them.

## Examples

### Example 1: Code Review Command

**File:** `.claude/commands/review.md`
```markdown
Review the code for:
- Bugs and edge cases
- Performance issues  
- Security vulnerabilities
- Code style and readability

Provide actionable suggestions with corrected code snippets.
```

**Usage:**
```
/review
/review Pay close attention to the input validation
```

### Example 2: Test Generator

**File:** `.claude/commands/gen-tests.md`
```markdown
Generate comprehensive unit tests for the code or module I describe.
Include:
- Happy path tests
- Edge cases
- Error handling tests
- Use the project's existing test framework and conventions
```

**Usage:**
```
/gen-tests for the user authentication functions
```

### Example 3: Documentation Writer

**File:** `.claude/commands/document.md`
```markdown
Write clear, concise documentation for the code I provide.
Include:
- A brief overview of what it does
- Parameters and return values
- Usage examples
- Any important notes or caveats
```

**Usage:**
```
/document
```

### Example 4: Commit Message Helper

**File:** `.claude/commands/commit-msg.md`
```markdown
Look at the current staged changes (use git diff --staged) and write a
conventional commit message. Follow this format:

type(scope): short description

Longer description if needed.

Use types: feat, fix, docs, style, refactor, test, chore
```

**Usage:**
```
/commit-msg
```

## How Custom Commands Appear in Help

Your custom commands show up when you type `/help`. The description displayed is taken from the **first non-heading, non-empty line** of your Markdown file (truncated to 50 characters).

To control what shows in `/help`, make the first line of your Markdown a clear, short description:

```markdown
Review code for bugs, performance, and style issues.

Detailed instructions follow below...
```

This shows in `/help` as:
```
/review    Execute markdown command: Review code for bugs, performance, and style issues.
```

## Handling Duplicate Names

If two files across different directories have the same name, Code Puppy automatically adds a numeric suffix to avoid conflicts:

- `.claude/commands/review.md` → `/review`
- `.agents/commands/review.md` → `/review2`

> [!NOTE]
> To avoid confusion, give your command files unique names across all directories.

## Options & Variations

| Feature | Details |
|---------|----------|
| **File format** | Standard Markdown (`.md`) |
| **Naming** | Filename becomes the command; use hyphens or underscores (e.g., `code-review.md` → `/code-review`) |
| **Arguments** | Any text after the command name is appended as additional context |
| **Reloading** | Commands are reloaded each time you view `/help`, so changes are picked up without restarting |
| **Sharing** | Commit your `.claude/commands/` directory to share custom commands with your team |

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Command doesn't appear in `/help` | File is in the wrong directory or has wrong extension | Make sure the file is in `.claude/commands/`, `.github/prompts/`, or `.agents/commands/` with the correct extension |
| Command appears but nothing happens | Markdown file is empty | Add content to the file |
| Wrong command name | Unexpected filename parsing | For `.github/prompts/`, use `.prompt.md` extension; for others, use `.md` |
| Duplicate command names | Same filename in multiple directories | Rename one of the files to be unique |

## Related Guides
- [How to Use Agents](UseAgents) — Built-in agents with specialized behaviors
- [How to Use Agent Skills](AgentSkills) — Extend agent capabilities
- [Reference: Slash Commands](../Reference/Commands) — All built-in commands
