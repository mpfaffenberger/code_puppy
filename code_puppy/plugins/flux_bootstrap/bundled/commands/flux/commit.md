---
name: commit
description: Create a detailed commit message from branch changes
argument-hint: amend
---

# CREATE A DETAILED COMMIT MESSAGE

## STEP 1: Detect mode

If argument (case-insensitive) equals `amend`, enter **amend mode**:

- Run `git log -1 --format=%B` and display: `"Previous commit message: <message>"`
- Use it as context in STEP 4; newly generated message is authoritative
- Use `git commit --amend -m "..."` in STEP 5 instead of `git commit -m "..."`

## STEP 2: Detect commit prefix

```bash
BRANCH=$(git branch --show-current)
TICKET=$(echo "$BRANCH" | grep -oE '[A-Z]+-[0-9]+' | head -1 || echo "")
echo "BRANCH: $BRANCH"
echo "TICKET: $TICKET"
```

- `$TICKET` non-empty → prefix: `$TICKET:` (e.g. `PROJ-123: description`)
- `$TICKET` empty → `AskUserQuestion`:
  - Question: "No Jira ticket found in branch name. What type of commit is this?"
  - Header: "Commit type"
  - Options: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`
  - Prefix: `<type>: description`

## STEP 3: Identify changed files

List all files changed vs main branch (both modified and new).

## STEP 4: Generate commit message

Generate an informative commit message for the changes. In amend mode, use the previous message as context to incorporate any new staged changes.

## STEP 5: Confirm and apply

```bash
git status
git diff --stat HEAD
```

If no changes, tell the user and stop.

**Amend mode:** if no staged changes, print `"Nothing is staged. Stage your changes with \`git add\` before amending."` and stop.

**Amend mode only** — show before confirmation:

> ⚠️ `--amend` rewrites history. If this branch has already been pushed, a force-push will be required.

Present the message from STEP 4, then `AskUserQuestion`:

- Normal: "Ready to commit with the message above?" → `["Yes, commit now", "No, let me review first"]`
- Amend: "Ready to amend the previous commit with the message above?" → `["Yes, amend now", "No, let me review first"]`

If "No, let me review first" → stop.

**Normal mode:**

```bash
git add .
git commit -m "$(cat <<'EOF'
$COMMIT_PREFIX Your generated message here
EOF
)"
```

**Amend mode:**

```bash
git add .
git commit --amend -m "$(cat <<'EOF'
$COMMIT_PREFIX Your refined message here

EOF
)"
```

IMPORTANT: Never use `$DETAILED_MSG` or any shell variable for the commit message. Write the actual generated message inline in the heredoc.

IMPORTANT: DO NOT push unless the user specifically asks!

## STEP 6: Summarize

Summarize completion. In amend mode, note "Amended previous commit" instead of "Created new commit".

## HARD CONSTRAINT

`//flux/commit` MUST NOT push to any remote unless the user explicitly asks. MUST NOT modify any source files or task files. The only permitted operations are reading git history, staging files, and creating/amending a commit. Write the commit message inline — never via shell variables.

## Propose next step

Then propose the next step: `//flux/create-pr` (include arguments if needed).

Valid `//flux` commands: `//flux/config`, `//flux/create-jira`, `//flux/new`, `//flux/ask`, `//flux/split`, `//flux/aug`, `//flux/exec`, `//flux/qa`, `//flux/tests`, `//flux/commit`, `//flux/create-pr`, `//flux/review`, `//flux/address-feedback`, `//flux/status`, `//flux/view-looper`, `//flux/auto-pilot`, `//flux/rebase`. Do NOT suggest any command not on this list.

=================
$ARGUMENTS
