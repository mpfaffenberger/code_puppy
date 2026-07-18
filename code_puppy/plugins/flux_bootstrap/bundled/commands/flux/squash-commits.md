---
name: squash-commits
description: Squash all unmerged commits on the current branch into a single commit
allowed-tools: AskUserQuestion, Bash
---

# SQUASH ALL UNMERGED COMMITS INTO ONE

Collapses every commit on your branch that hasn't landed on the default branch yet into a single commit. Useful before opening a PR or when you want a clean history.

**Example:** 7 work-in-progress commits on `luc/my-feature` → squashed into 1 clean commit, preserving all changes.

## STEP 1: Capture current state

```bash
BRANCH=$(git branch --show-current)
TICKET=$(echo "$BRANCH" | grep -oE '[A-Z]+-[0-9]+' | head -1 || echo "")
DEFAULT_BRANCH=$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || echo "main")
echo "BRANCH: $BRANCH"
echo "TICKET: $TICKET"
echo "DEFAULT_BRANCH: $DEFAULT_BRANCH"

# Commits on our branch that aren't on the default branch
COMMIT_COUNT=$(git log "$DEFAULT_BRANCH"..HEAD --oneline | wc -l | tr -d ' ')
echo "Commits to squash: $COMMIT_COUNT"
git log "$DEFAULT_BRANCH"..HEAD --oneline

# Files we touch
git diff "$DEFAULT_BRANCH" --stat
```

**Guards — stop if any of the following are true:**

- `$BRANCH` is empty or equals `HEAD` (detached HEAD state) → stop and tell the user: "You are in a detached HEAD state. Please checkout a real feature branch before squashing."
- `$COMMIT_COUNT` == 0 → stop and tell the user: "No commits found on this branch ahead of `$DEFAULT_BRANCH`. Nothing to squash."
- `$COMMIT_COUNT` == 1 → stop and tell the user: "This branch has only 1 commit ahead of `$DEFAULT_BRANCH`. There is nothing to squash — you already have a single commit."

## STEP 2: Working tree must be clean

```bash
git status --porcelain
```

If there is **any** output (staged or unstaged changes, untracked files you care about):

`AskUserQuestion` — question: "Your working tree is not clean. Squashing requires a clean tree (or stashed work). How do you want to proceed?" / header: "Unclean working tree" / options:

- `Stash changes and continue` → run `git stash push -u -m "myproj-flux-squash-wip"`. Set an internal flag that a stash was created — STEP 9 will offer to pop it.
- `Abort` → stop. Do not squash.

If the tree is already clean, continue to STEP 3.

## STEP 3: Check remote sync

Fetch the remote branch ref (quietly, so offline environments don't hard-fail), then check if the remote is ahead of the local branch:

```bash
git fetch origin "$BRANCH" 2>/dev/null || true

REMOTE_AHEAD=$(git rev-list HEAD..origin/"$BRANCH" --count 2>/dev/null || echo "0")
echo "Remote ahead by: $REMOTE_AHEAD commit(s)"
```

If `$REMOTE_AHEAD` > 0 → **stop** and inform the user:

> ⚠️ Your local branch `$BRANCH` is behind its remote counterpart (`origin/$BRANCH`) by **$REMOTE_AHEAD commit(s)**. Squashing now would rewrite history on top of a stale base, causing a push conflict.
>
> **What to do first:**
>
> 1. Run `//flux/rebase` to bring your branch up to date with the latest `$DEFAULT_BRANCH` while incorporating the remote's changes.
> 2. Once your branch is in sync, run `//flux/squash-commits` again.
>
> Alternatively, run `git pull --rebase origin $BRANCH` to sync with the remote, then re-run `//flux/squash-commits`.

If `$REMOTE_AHEAD` == 0 (or the remote branch doesn't exist yet), continue to STEP 4.

## STEP 4: Show commits and confirm

Display the commits that will be squashed:

```bash
echo "The following $COMMIT_COUNT commits will be squashed into one:"
git log "$DEFAULT_BRANCH"..HEAD --oneline
```

`AskUserQuestion` — question: "Squash these $COMMIT_COUNT commits into one?" / header: "Confirm squash" / options:

- `Yes, squash them` → continue to STEP 5.
- `Abort` → stop. Do not squash.

## STEP 5: Build the combined commit message

Collect all commit subjects and bodies, in chronological order (oldest first), and format as a bulleted list:

```bash
SQUASH_MSG=$(git log "$DEFAULT_BRANCH"..HEAD --format="- %s%n%b" --reverse | sed '/^$/d' | sed 's/^- -/  -/')
echo "Proposed commit message:"
echo "---"
echo "$SQUASH_MSG"
echo "---"
```

`AskUserQuestion` — question: "Use this combined commit message for the squashed commit?" / header: "Commit message" / options:

- `Yes, use this message` → use `$SQUASH_MSG` as-is. Continue to STEP 6.
- `Let me write my own` → `AskUserQuestion` — question: "Enter your commit message:" / header: "Custom message" / options: _(free text — user selects Other)_. Use the user's input as `$SQUASH_MSG`.

## STEP 6: Squash

Perform the squash using a soft reset to the merge base, then commit:

```bash
MERGE_BASE=$(git merge-base HEAD "$DEFAULT_BRANCH")
echo "Merge base: $MERGE_BASE"
git reset --soft "$MERGE_BASE"
git commit -m "$SQUASH_MSG"
```

> **What this does:** `git reset --soft` moves HEAD back to the merge base while keeping all changes staged, then a single `git commit` creates one new commit containing everything.

## STEP 7: Verify

Confirm the squash produced exactly 1 commit and that all changes are intact:

```bash
echo "Commits on branch after squash:"
git log "$DEFAULT_BRANCH"..HEAD --oneline

echo ""
echo "Changed files vs $DEFAULT_BRANCH:"
git diff "$DEFAULT_BRANCH" --stat
```

Expected: exactly 1 commit in the log. Changed files should match what was there before the squash. If the log shows more than 1 commit or the diff looks wrong — stop and investigate before pushing.

## STEP 8: Confirm push

After a squash, commit hashes differ from any previous push of the same branch. Choose the right push: first-time upstream vs `--force-with-lease` when the branch already exists on the remote.

```bash
git rev-parse @{u} >/dev/null 2>&1 && echo HAS_UPSTREAM || echo NO_UPSTREAM
```

- **`NO_UPSTREAM`** (first push of this branch): `AskUserQuestion` — question: "Squash is complete and verified. Push this branch and set upstream with `git push -u origin \"$BRANCH\"`? (No force needed.)" / header: "Push branch" / options: `Yes, push now` | `No, I'll push manually later`

  - Yes → `git push -u origin "$BRANCH"`
  - No → skip push; say so in STEP 9.

- **`HAS_UPSTREAM`**: `AskUserQuestion` — question: "Squash rewrote history. Push with `git push --force-with-lease origin \"$BRANCH\"`? Refuses if someone else pushed in the meantime. Only do this for your own feature branch — never `$DEFAULT_BRANCH`." / header: "Push squashed branch" / options: `Yes, force-with-lease now` | `No, I'll push manually later`
  - Yes → `git push --force-with-lease origin "$BRANCH"`
  - No → skip push; say so in STEP 9.

If `--force-with-lease` fails because the remote moved, run `git fetch origin`, re-evaluate (and re-ask if appropriate), then retry.

> ⚠️ Never `git push --force` without lease, and never force-push `$DEFAULT_BRANCH`.

## STEP 9: Summarize

Report:

- `$TICKET` (if any) and `$BRANCH`
- How many commits were squashed into 1 (the original `$COMMIT_COUNT`)
- The final commit message used
- Push: done vs deferred by user choice
- If STEP 2 stashed: use `AskUserQuestion` — question: "You stashed changes before squashing. Do you want to pop the stash now?" / header: "Restore stash" / options: `Yes, pop stash now` | `No, I'll pop it manually later`
  - Yes → run `git stash pop`. If it produces conflicts, list the conflicted files and instruct the user to resolve them manually (`git add <file>` after editing, then `git stash drop` once done — do NOT run `git stash pop` again).
  - No → remind the user to run `git stash pop` manually when ready.

## HARD CONSTRAINT

`//flux/squash-commits` MUST NOT modify commit content beyond the squash itself. MUST NOT commit to `$DEFAULT_BRANCH`. MUST NOT use `git push --force` (use `--force-with-lease` when updating an existing remote branch). MUST NOT touch any commits already present on `$DEFAULT_BRANCH`.

## Propose next step

Then propose the next step: `//flux/create-pr` (include arguments if needed).

Valid `//flux` commands: `//flux/config`, `//flux/create-jira`, `//flux/new`, `//flux/ask`, `//flux/split`, `//flux/aug`, `//flux/exec`, `//flux/qa`, `//flux/tests`, `//flux/commit`, `//flux/create-pr`, `//flux/review`, `//flux/address-feedback`, `//flux/status`, `//flux/view-looper`, `//flux/auto-pilot`, `//flux/rebase`, `//flux/squash-commits`. Do NOT suggest any command not on this list.

=================
$ARGUMENTS
