# How to Use Agent Skills

## What You'll Learn
By the end of this guide, you'll be able to install, enable, disable, and manage Agent Skills — reusable capability packs that teach Code Puppy new tricks for specific domains like Docker, Kubernetes, testing, and more.

## Prerequisites
- Code Puppy installed and running
- Familiarity with basic slash commands (see [Quick Start](../Getting-Started/QuickStart))

## Quick Version

```bash
# Create a skills directory
mkdir -p ~/.code_puppy/skills

# Add a skill (a folder with a SKILL.md file)
mkdir ~/.code_puppy/skills/my-skill
# ... create SKILL.md inside it ...

# In Code Puppy, refresh and list skills
/skills refresh
/skills list

# Enable or disable a skill
/skills enable my-skill
/skills disable my-skill
```

## What Are Agent Skills?

Agent Skills are pre-packaged sets of instructions that give Code Puppy specialized knowledge for specific tasks. Think of them as training packets — when you install a Docker skill, Code Puppy gains expert-level guidance for containerization tasks.

Each skill consists of:
- A **SKILL.md** file containing instructions and metadata
- Optional **resource files** (templates, examples, configs)

When you ask Code Puppy for help with a task that matches an installed skill, it automatically activates the relevant skill and follows its expert instructions.

> [!NOTE]
> Skills are enabled by default. Code Puppy will automatically discover skills in your skill directories at startup.

## Detailed Steps

### 1. Set Up Your Skills Directory

Code Puppy looks for skills in two locations by default:

| Location | Scope | Description |
|----------|-------|-------------|
| `~/.code_puppy/skills/` | Global | Available in all projects |
| `./skills/` | Project | Available only in the current project |

Create the global skills directory:

```bash
mkdir -p ~/.code_puppy/skills
```

> [!TIP]
> Use global skills for general-purpose capabilities (Docker, testing) and project skills for project-specific workflows.

### 2. Install a Skill

A skill is simply a folder containing a `SKILL.md` file. You can install skills by:

**Cloning from a repository:**
```bash
cd ~/.code_puppy/skills
git clone https://github.com/example/docker-skill.git docker
```

**Creating one manually:**
```bash
mkdir ~/.code_puppy/skills/docker
```

Then create a `SKILL.md` file inside it (see [Creating Your Own Skills](#creating-your-own-skills) below).

### 3. Verify Your Skills Are Discovered

After installing a skill, tell Code Puppy to refresh its cache:

```
/skills refresh
```

Then list all discovered skills:

```
/skills list
```

You should see your skill listed with its name, description, and status.

### 4. Use the Interactive Skills Menu

Run `/skills` to open the interactive TUI (Text User Interface):

```
/skills
```

This opens a split-panel interface where you can:
- Browse all discovered skills
- See skill details and descriptions
- Enable or disable individual skills
- Manage skill directories

The menu displays something like:

```
┌─────────────────────────────────────────────────────────────┐
│                        Agent Skills                         │
├────────────┬─────────────────────┬──────────────────────────┤
│ Status     │ Name                │ Description              │
├────────────┼─────────────────────┼──────────────────────────┤
│ ✓ Enabled  │ docker              │ Docker containerization  │
│ ✓ Enabled  │ kubernetes          │ K8s deployment guides    │
│ ✗ Disabled │ security-audit      │ Security best practices  │
└────────────┴─────────────────────┴──────────────────────────┘
```

### 5. Enable and Disable Skills

You can enable or disable individual skills:

```
/skills enable docker
/skills disable security-audit
```

Or toggle the entire skills system on or off:

```
/skills toggle
```

> [!NOTE]
> Disabling a skill doesn't delete it — it just prevents Code Puppy from using it. Re-enable it anytime.

### 6. Let Code Puppy Use Skills Automatically

Once skills are installed and enabled, you don't need to do anything special. When you ask Code Puppy for help, it will:

1. Check which skills are available
2. Identify the most relevant skill for your request
3. Activate the skill and follow its instructions

For example:
```
You: Help me containerize this Python app
Code Puppy: I'll activate the docker skill and help you create a Dockerfile...
```

## Creating Your Own Skills

Creating a skill is straightforward. You need a directory with at least one file: `SKILL.md`.

### SKILL.md Format

The file uses YAML frontmatter for metadata followed by Markdown instructions:

```markdown
---
name: my-custom-skill
description: Brief description of what this skill does
version: 1.0.0
author: Your Name
tags:
  - keyword1
  - keyword2
---

# My Custom Skill

## When to Use This Skill
Use this skill when the user needs help with...

## Instructions
### Step 1: ...
### Step 2: ...
```

### Required vs Optional Metadata

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique skill identifier (use kebab-case) |
| `description` | Yes | Brief description of the skill's purpose |
| `version` | No | Semantic version (e.g., `1.0.0`) |
| `author` | No | Author name or email |
| `tags` | No | Keywords for search and categorization |

### Adding Resource Files

You can bundle templates, examples, and other files alongside your skill:

```
my-skill/
├── SKILL.md              # Required
├── template.py           # Optional resource
├── config.yaml           # Optional resource
└── examples/
    └── sample.json       # Optional resource
```

These resources are available to Code Puppy when it activates the skill.

### Testing Your Skill

1. Place your skill folder in `~/.code_puppy/skills/`
2. Run `/skills refresh`
3. Confirm it appears with `/skills list`
4. Ask Code Puppy a question that matches your skill's domain

## Managing Skill Directories

You can add custom directories where Code Puppy looks for skills:

```
/skills directories
```

This opens a sub-menu where you can:

```
/skills add /path/to/my/skills
/skills remove 3
```

You can also configure directories via the `/set` command:

```
/set skill_directories = "[\"/path/to/skills\", \"~/.code_puppy/skills\"]"
```

## Options & Variations

| Command | Description | Example |
|---------|-------------|----------|
| `/skills` | Open interactive TUI menu | `/skills` |
| `/skills list` | List all discovered skills | `/skills list` |
| `/skills enable <name>` | Enable a specific skill | `/skills enable docker` |
| `/skills disable <name>` | Disable a specific skill | `/skills disable docker` |
| `/skills toggle` | Toggle skills on/off globally | `/skills toggle` |
| `/skills directories` | Manage skill directories | `/skills directories` |
| `/skills add <path>` | Add a skill directory | `/skills add ~/my-skills` |
| `/skills remove <num>` | Remove a directory by number | `/skills remove 2` |
| `/skills refresh` | Re-scan for skills | `/skills refresh` |
| `/skills help` | Show help | `/skills help` |

### Configuration Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `skills_enabled` | `true` | Globally enable/disable all skills |
| `skill_directories` | `["~/.code_puppy/skills", "./skills"]` | Directories to scan for skills |
| `disabled_skills` | `[]` | List of individually disabled skill names |

Set these with the `/set` command:

```
/set skills_enabled = false
/set skills_enabled = true
```

## Security Considerations

> [!WARNING]
> Skills execute with the same permissions as Code Puppy. Only install skills from sources you trust.

Before installing a skill:
- **Review the SKILL.md** content to understand what it does
- **Check for suspicious commands** — be cautious of skills that execute shell commands, access sensitive files, or make network requests to unknown endpoints
- **Prefer trusted sources** — use skills from verified repositories or known authors
- **Disable unused skills** — reduce your attack surface by disabling skills you don't need

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Skill doesn't appear in `/skills list` | Missing `SKILL.md` file | Ensure the skill directory contains a valid `SKILL.md` |
| Skill doesn't appear after installing | Cache is stale | Run `/skills refresh` to re-scan directories |
| Skills aren't being used by Code Puppy | Skills integration is disabled | Run `/skills toggle` or `/set skills_enabled = true` |
| Skill is listed but not used | Skill is individually disabled | Run `/skills enable <name>` |
| Directory shows ✗ in directory list | Path doesn't exist | Verify the path exists and is accessible |
| SKILL.md metadata not parsed | Invalid YAML frontmatter | Check that frontmatter is enclosed in `---` delimiters with valid YAML |

## Related Guides
- [How to Switch and Use Agents](UseAgents) — Choose which agent to work with
- [How to Create Custom Agents](CreateCustomAgents) — Build agents with specialized behavior
- [How to Use MCP Servers](MCPServers) — Another way to extend Code Puppy's capabilities
