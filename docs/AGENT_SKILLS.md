# 🎯 Agent Skills Integration

> **Official Spec:** [https://agentskills.io](https://agentskills.io)

Agent Skills are reusable, modular capabilities that extend Code Puppy's functionality. Think of them as specialized training packets you can dynamically load when needed—like teaching your puppy new tricks on demand! 🐕

---

## 📋 Table of Contents

1. [What Are Agent Skills?](#what-are-agent-skills)
2. [Installing Skills](#installing-skills)
3. [Using the /skills TUI Menu](#using-the-skills-tui-menu)
4. [How Skills Work](#how-skills-work)
5. [Skill Namespaces (Large Catalogs)](#skill-namespaces-large-catalogs)
6. [Creating Your Own Skills](#creating-your-own-skills)
7. [Configuration Options](#configuration-options)
8. [Security Considerations](#security-considerations)

---

## What Are Agent Skills?

Agent Skills are pre-packaged capabilities that can be dynamically discovered, loaded, and used by agents. They consist of:

- **SKILL.md** - The main instruction file with YAML frontmatter metadata
- **Resources** - Optional supporting files (templates, examples, configs)
- **Metadata** - Name, description, version, author, and tags

Skills enable you to:

- 📦 Share reusable workflows and best practices
- 🎯 Give agents specialized knowledge for specific tasks
- 🔌 Extend functionality without modifying core code
- 🏗️ Build domain-specific expertise (DevOps, security, testing, etc.)

---

## Installing Skills

Skills are installed by placing them in designated skill directories. Code Puppy scans these directories at startup to discover available skills.

### Default Skill Directories

By default, Code Puppy looks for skills in:

1. **`~/.code_puppy/skills/`** - User-level skills (global)
2. **`./skills/`** - Project-level skills (local)

### Installation Steps

1. **Create the skills directory** (if it doesn't exist):

   ```bash
   mkdir -p ~/.code_puppy/skills
   ```

2. **Download or clone a skill** into the directory:

   ```bash
   # Example: Installing a docker skill
   cd ~/.code_puppy/skills
   git clone https://github.com/example/code-puppy-docker.git docker
   
   # Or manually create the skill directory
   mkdir my-custom-skill
   ```

3. **Verify the skill** has a `SKILL.md` file:

   ```bash
   ls ~/.code_puppy/skills/my-custom-skill/SKILL.md
   ```

4. **Refresh skill discovery**:

   ```
   /skills refresh
   ```

### Skill Directory Structure

```
~/.code_puppy/skills/
├── docker/
│   ├── SKILL.md          # Required: Skill instructions + metadata
│   ├── docker-compose.yml # Optional: Supporting resource
│   └── Dockerfile.template # Optional: Supporting resource
├── kubernetes/
│   ├── SKILL.md
│   └── k8s-templates/
└── security-audit/
    ├── SKILL.md
    └── audit-checklist.md
```

---

## Using the /skills TUI Menu

Code Puppy provides an interactive TUI (Text User Interface) for managing skills.

### Launching the Menu

```
/skills
```

This opens an interactive menu where you can browse, enable, disable, and configure skills.

### Quick Commands

| Command | Description |
|---------|-------------|
| `/skills` | Launch the interactive TUI menu |
| `/skills list` | List all discovered skills |
| `/skills enable <name>` | Enable a specific skill |
| `/skills disable <name>` | Disable a specific skill |
| `/skills toggle` | Toggle skills integration on/off |
| `/skills directories` | Manage skill directories |
| `/skills add <path>` | Add a skill directory |
| `/skills remove <num>` | Remove a skill directory by number |
| `/skills refresh` | Refresh skill cache |
| `/skills help` | Show help message |

### Interactive Menu Options

When you run `/skills`, you'll see:

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

Total: 3 skills found

Commands:
  list              - List all skills
  enable <skill>    - Enable a specific skill
  disable <skill>   - Disable a specific skill
  toggle            - Toggle skills integration on/off
  directories       - Manage skill directories
  refresh           - Refresh skill cache
  help              - Show this help
  exit              - Exit skills menu
```

---

## How Skills Work

Skills integrate with agents through two mechanisms: **prompt injection** and **dedicated tools**.

### 1. Prompt Injection

When skills are enabled, Code Puppy automatically injects available skills into the system prompt:

```xml
<available_skills>
  <skill>
    <name>docker</name>
    <description>Expert guidance for Docker containerization, Dockerfile optimization, and docker-compose orchestration</description>
  </skill>
  <skill>
    <name>kubernetes</name>
    <description>Kubernetes deployment patterns, manifest generation, and cluster management</description>
  </skill>
</available_skills>
```

This tells the agent what skills are available without loading their full content.

### 2. Skill Tools

Agents have access to two dedicated tools for working with skills:

#### `list_or_search_skills`

Lists all available skills, optionally filtered by a search query.

**When to use:**
- At the start of a task to see what's available
- When you need to find a skill matching specific keywords

**Example:**
```python
# List all skills
list_or_search_skills()

# Search for docker-related skills
list_or_search_skills(query="docker")
```

**Returns:**
- `skills`: List of skill metadata (name, description, path, tags)
- `total_count`: Total number of skills found
- `query`: The search query (if provided)

#### `activate_skill`

Loads and activates a specific skill by name.

**When to use:**
- When a user's task matches a skill's description
- To load the full instructions for a specific capability

**Example:**
```python
activate_skill(skill_name="docker")
```

**Returns:**
- `skill_name`: Name of the activated skill
- `content`: Full SKILL.md content (including instructions)
- `resources`: List of available resource files
- `error`: Error message (if activation failed)

### Skill Activation Flow

1. **Discovery** → Code Puppy scans skill directories at startup
2. **Prompt Injection** → Available skills are listed in the system prompt
3. **User Request** → User asks for help with a specific domain
4. **Skill Selection** → Agent identifies the relevant skill
5. **Activation** → Agent calls `activate_skill(skill_name="...")`
6. **Execution** → Agent follows the loaded skill instructions

---

## Skill Namespaces (Large Catalogs)

Everything above describes the default behavior: a flat list of every
enabled skill's name + description gets injected into the system
prompt, and the agent picks one with `list_or_search_skills` /
`activate_skill`. That works fine for a handful of skills. It stops
working well somewhere in the dozens-to-hundreds range - flat lists
that size burn a lot of context, and models (especially smaller/faster
ones) get worse at picking the right item the longer the list gets.

The **namespace_skill_search** builtin plugin fixes this by grouping
skills into **namespaces** and replacing the flat list with a compact
directory - the same shape OpenAI ships for large tool catalogs
(tool_search + namespace grouping) and Anthropic ships for large MCP
tool sets (Tool Search Tool), reimplemented here in a model-agnostic
way so it behaves identically on Claude, GPT, Gemini, or any other
provider wired through Code Puppy's ModelFactory.

### What changes automatically

This plugin is builtin and on by default - you don't need to install or
configure anything. The first time Code Puppy starts with it present:

1. Every enabled skill gets grouped into a **namespace**, derived from
   its first `tags:` entry in `SKILL.md` (untagged skills land in a
   `General` namespace). No changes to your existing `SKILL.md` files
   are required.
2. The system prompt gets a short **namespace directory** instead of
   one line per skill - a handful of lines like:

   ```text
   ## Skill Namespaces
   47 skills available across 8 namespaces. Individual skills are NOT
   listed here - browse or search instead.

   - **finance** (12): variance-analysis, gl-daily, +10 more
   - **devops** (9): docker, kubernetes, terraform
   - **General** (3): my-custom-skill, ...
   ```

3. The old per-skill flat list (`frontmatter_in_system_prompt`) is
   turned **off** automatically, so you don't end up paying for both
   the old list and the new directory at once. This is a one-time,
   persisted change - see [Turning it off](#turning-it-off) below if
   you want the flat list back.

### The browse_skill_namespace tool

Agents get one new tool with three modes, matching the three things you
actually need to do at this scale:

| Call | Mode | What it returns |
|------|------|------------------|
| `browse_skill_namespace()` | Directory | Every namespace name + skill count (same content as the prompt block) |
| `browse_skill_namespace(namespace='finance')` | Namespace | Every skill inside that one namespace |
| `browse_skill_namespace(query='variance')` | Search | Keyword search across name/description/tags, across **all** namespaces at once |

You can also combine `namespace=` and `query=` to search within one
namespace. The normal flow is: browse the directory, drill into (or
search within) the namespace that looks relevant, then call
`activate_skill(name)` on whatever you find - exactly like you would
after `list_or_search_skills`. `list_or_search_skills` still exists and
still works; `browse_skill_namespace` is additive, not a replacement.

**Example:**

```python
# 1. See what domains exist
browse_skill_namespace()
# -> directory mode: namespaces=['finance', 'devops', 'General'], total_skills=47

# 2. Drill into the relevant one
browse_skill_namespace(namespace='finance')
# -> namespace mode: skills=[{name: 'variance-analysis', ...}, ...], total_skills=12

# 3. Or skip straight to a keyword search across everything
browse_skill_namespace(query='variance')
# -> search mode: skills=[{name: 'variance-analysis', namespace: 'finance', ...}]

# 4. Load the one you want
activate_skill(skill_name='variance-analysis')
```

### Namespace sizing

If any single namespace grows past ~10 skills, the directory block
flags it as an `oversized namespace` - a visible nudge (not an
enforced limit; skill tags aren't this plugin's to rewrite) that it
might be worth splitting that tag into more specific ones. If two
skills anywhere end up with the exact same name, the directory also
adds a note flagging the collision, since `activate_skill(name)` can't
disambiguate between them on its own.

### Turning it off

If you'd rather go back to the flat per-skill list:

```
/plugins disable namespace_skill_search
/skills frontmatter on
```

The first command stops the plugin from running at all (no namespace
directory, no `browse_skill_namespace` tool). The second restores the
original flat list - it won't come back on its own just from disabling
the plugin, since the earlier flip is a persisted config change, not
something tied to the plugin being active.

---

## Creating Your Own Skills

Creating a skill is straightforward. You need a directory with at least one file: `SKILL.md`.

### SKILL.md Format

The `SKILL.md` file uses **YAML frontmatter** for metadata followed by **Markdown content** for instructions.

```markdown
---
name: docker-expert
description: Expert guidance for Docker containerization, multi-stage builds, and compose orchestration
version: 1.0.0
author: Your Name
tags:
  - docker
  - containers
  - devops
  - deployment
---

# Docker Expert Skill

## When to Use This Skill

Use this skill when the user needs help with:
- Writing or optimizing Dockerfiles
- Setting up docker-compose configurations
- Container best practices and security
- Multi-stage builds for smaller images

## Instructions

### 1. Dockerfile Best Practices

Always follow these principles:

- Use specific base image tags (not `latest`)
- Leverage multi-stage builds to minimize image size
- Combine RUN commands to reduce layers
- Use `.dockerignore` to exclude unnecessary files

### 2. Security Guidelines

- Run containers as non-root users
- Scan images for vulnerabilities
- Minimize installed packages
- Use distroless or slim base images when possible

### 3. Common Patterns

```dockerfile
# Multi-stage build example
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM node:18-alpine
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY . .
USER node
CMD ["node", "server.js"]
```

## Available Tools

When this skill is activated, you can use standard file tools to:
- Create Dockerfiles
- Generate docker-compose.yml files
- Set up .dockerignore

## Resources

This skill includes:
- `docker-compose.yml.template` - Starter compose template
- `.dockerignore.example` - Common ignore patterns
```

### Required Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique skill identifier (kebab-case recommended) |
| `description` | string | Yes | Brief description of what the skill does |
| `version` | string | No | Semantic version (e.g., "1.0.0") |
| `author` | string | No | Author name or email |
| `tags` | list | No | List of keywords for categorization. **The first tag also determines the skill's namespace** — see below. |

> **Namespace tip:** if `namespace_skill_search` is enabled (the default —
> see [Skill Namespaces (Large Catalogs)](#skill-namespaces-large-catalogs)),
> your skill's **first** `tags:` entry becomes its namespace, grouping it
> with every other skill that shares that first tag. An untagged skill
> falls into a generic `General` namespace alongside every other untagged
> skill. Put your most specific, meaningful category **first** —
> e.g. `docker` before `devops` for a Docker-specific skill — rather than
> leading with a broad tag that dumps unrelated skills into the same
> bucket. Namespace matching is case-insensitive, so `docker`/`Docker`/
> `DOCKER` all land in one namespace regardless of casing.

### Frontmatter Examples

**Minimal (required only):**
```yaml
---
name: my-skill
description: Does something useful
---
```

**Complete (all fields):**
```yaml
---
name: python-testing
description: Comprehensive Python testing with pytest, including fixtures, mocks, and coverage
version: 2.1.0
author: Jane Developer <jane@example.com>
tags:
  - python
  - testing
  - pytest
  - quality
---
```

### Including Resources

You can bundle additional files with your skill. Place them in the same directory as `SKILL.md`:

```
my-skill/
├── SKILL.md              # Required
├── template.py           # Optional resource
├── config.yaml           # Optional resource
└── examples/
    └── sample.json       # Optional resource
```

These resources are listed when the skill is activated via the `resources` field in the output.

### Skill Naming Conventions

- Use **kebab-case** (e.g., `docker-compose`, `python-testing`)
- Keep names **descriptive but concise**
- Avoid generic names like `utils` or `helpers`
- Prefix domain-specific skills (e.g., `aws-s3`, `gcp-cloudrun`)

### Testing Your Skill

1. Place your skill in `~/.code_puppy/skills/`
2. Run `/skills refresh`
3. Verify it appears in `/skills list`
4. Test activation by asking an agent to use it

---

## Configuration Options

Agent Skills can be configured through Code Puppy's configuration system.

### Configuration Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `skills_enabled` | boolean | `true` | Globally enable/disable skills integration |
| `skill_directories` | JSON list | `["~/.code_puppy/skills", "./skills"]` | Directories to scan for skills |
| `disabled_skills` | JSON list | `[]` | List of skill names to disable |

### Setting Configuration Values

Use the `/set` command to configure skills:

```
# Disable skills integration entirely
/set skills_enabled = false

# Enable skills integration
/set skills_enabled = true

# Add a custom skill directory
/set skill_directories = "[\"/path/to/skills\", \"~/.code_puppy/skills\"]"

# Disable specific skills
/set disabled_skills = "[\"skill-one\", \"skill-two\"]"
```

### Managing Skill Directories

You can also manage directories via the TUI:

```
/skills directories
```

This shows:
```
Skill Directories:
  1. ✓ /home/user/.code_puppy/skills
  2. ✓ /path/to/project/skills
  3. ✗ /old/path (does not exist)

Commands:
  add <path>        - Add a skill directory
  remove <num>      - Remove directory by number
  list              - List directories
  back              - Return to main menu
```

### Configuration File Location

Settings are stored in `~/.code_puppy/puppy.cfg`:

```ini
[puppy]
skills_enabled = true
skill_directories = ["/home/user/.code_puppy/skills", "./skills"]
disabled_skills = ["deprecated-skill"]
```

---

## Security Considerations

⚠️ **Important:** Skills execute with the same permissions as Code Puppy. Follow these security best practices:

### Skill Sources

- **Only install skills from trusted sources**
- Review skill content before installing
- Be cautious with skills that request elevated permissions
- Prefer skills from verified repositories or official sources

### Skill Content

- **Review SKILL.md** before using a new skill
- Check what tools and commands the skill uses
- Be wary of skills that:
  - Execute arbitrary shell commands
  - Access sensitive files or environment variables
  - Make network requests to unknown endpoints
  - Modify system configurations

### File System Access

Skills can access:
- Files within their own directory
- The project working directory
- Any files Code Puppy has access to

**Recommendation:** Run Code Puppy with minimal necessary permissions.

### Network Security

Skills may include instructions that:
- Download resources from the internet
- Call external APIs
- Clone repositories

**Best practice:** Review any URLs or network operations in skill instructions.

### Sandboxing Recommendations

For maximum security:

1. **Use a dedicated environment** (container, VM, or restricted user)
2. **Limit file system access** to only necessary directories
3. **Monitor network activity** when using new skills
4. **Keep skills updated** to receive security patches
5. **Disable unused skills** to reduce attack surface

### Reporting Security Issues

If you discover a security vulnerability in a skill:

1. Disable the skill immediately: `/skills disable <skill-name>`
2. Report to the skill author
3. For core skills functionality issues, report to Code Puppy

### Skill Verification

Before installing a skill, verify:

- [ ] Source is trustworthy (official repo, known author)
- [ ] SKILL.md content is reviewed
- [ ] No suspicious shell commands or network calls
- [ ] Resource files are safe (no binaries, scripts are reviewed)
- [ ] Skill is actively maintained

---

## Example Workflow

Here's a complete example of using Agent Skills:

```bash
# 1. Start Code Puppy
code-puppy

# 2. Check available skills
/skills list

# 3. Start a conversation with an agent
/agent code-puppy

# 4. The agent automatically knows about available skills
# When you ask for docker help, it activates the docker skill

# User: Help me containerize this Python app
# Agent: I'll help you containerize this Python app. Let me activate the docker skill first.
# [Agent calls activate_skill(skill_name="docker")]
# [Agent follows skill instructions to create Dockerfile, .dockerignore, docker-compose.yml]
```

---

## Additional Resources

- **Official Spec:** [https://agentskills.io](https://agentskills.io)
- **Skill Registry:** Community-contributed skills (coming soon)
- **Creating Skills Guide:** This document + spec at agentskills.io

---

*Happy skill building! 🐕🎯*
