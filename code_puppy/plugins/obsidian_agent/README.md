# Obsidian Agent

The Obsidian Agent adds a specialized Code Puppy agent for working with Obsidian vaults through the official `obsidian` CLI.

## What it does

- Discovers vaults, notes, folders, links, tags, tasks, templates, and related Obsidian state.
- Uses the Obsidian CLI for vault-aware operations instead of blindly editing files.
- Follows a read-before-write workflow for note changes.
- Requires explicit confirmation for destructive, broad, or hard-to-reverse operations.
- Helps troubleshoot common CLI setup issues.

## Requirements

- Obsidian desktop 1.12.7 or newer.
- Obsidian's command line interface enabled in Settings → General.
- The Obsidian desktop app running, or available to be launched by the CLI.
- The `obsidian` command available on `PATH`.

Useful checks:

```bash
which obsidian
obsidian version
obsidian help
obsidian vaults total verbose
```

## Usage

Switch to the agent from Code Puppy and ask for an Obsidian task. Include a vault name or vault-relative path when relevant.

Examples:

- "Find notes about release planning in my work vault."
- "Create a meeting note from my weekly meeting template."
- "Append this task to today's daily note."
- "Show unresolved links and propose a cleanup plan."

For broad updates, the agent should present a plan and ask for confirmation before making changes. Tiny bureaucracy, but the useful kind.

## Safety notes

The agent intentionally avoids personal defaults. It does not include any user-specific vault names, local paths, or private note structure.

It treats these as confirmation-required operations:

- Permanent deletes, moves, and renames.
- History or sync restores.
- Publish changes.
- Plugin, theme, snippet, sync, reload, restart, and developer/debug commands.
- Arbitrary JavaScript evaluation.
