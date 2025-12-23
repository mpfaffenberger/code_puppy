# Skills Plugin 📚

Claude Code-compatible skill support for Code Puppy.

## What Are Skills?

Skills are modular knowledge packages (`SKILL.md` files) that extend the LLM's capabilities with specialized expertise, workflows, and resources.

## Quick Start

```bash
# List installed skills
/skill list

# Install a skill
/skill add ~/my-skills/pdf

# View skill details
/skill info pdf

# Show full documentation
/skill show pdf

# Remove a skill
/skill remove pdf

# Rescan skills directory
/skill refresh
```

## Skills Directory

```
~/.code_puppy/skills/
├── pdf/
│   ├── SKILL.md          # Required: skill definition
│   ├── scripts/          # Optional: helper scripts
│   └── references/       # Optional: reference docs
└── docx/
    └── SKILL.md
```

## SKILL.md Format

```yaml
---
name: my-skill              # kebab-case, required
description: "What it does" # required
license: "MIT"              # optional
---

# Skill Title

Full documentation goes here...
```

**Rules:**
- Must start with `---` (YAML frontmatter)
- `name` and `description` are required
- Body content follows the second `---`

## How It Works

1. **Startup** → Plugin scans `~/.code_puppy/skills/` for valid skills
2. **Prompts** → Skill catalog is injected into system prompts
3. **Usage** → LLM sees available skills and can request full docs

## Commands Reference

| Command | Description |
|---------|-------------|
| `/skill` | Show help |
| `/skill list` | List installed skills |
| `/skill info <name>` | Show metadata |
| `/skill show <name>` | Show full SKILL.md |
| `/skill add <path>` | Install from directory |
| `/skill remove <name>` | Uninstall skill |
| `/skill refresh` | Rescan directory |

## Creating a Skill

```bash
mkdir -p ~/.code_puppy/skills/my-skill
cat > ~/.code_puppy/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: "My awesome skill for doing X"
---

# My Skill

## When to Use
Use this skill when the user asks about X...

## Workflow
1. Step one
2. Step two
3. Done!
EOF
```

Then run `/skill refresh` to load it.
