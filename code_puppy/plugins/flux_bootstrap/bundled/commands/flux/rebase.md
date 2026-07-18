---
name: rebase
description: Rebase branch onto latest default branch, preserving individual commits
allowed-tools: AskUserQuestion, Bash
---

# REBASE ONTO LATEST DEFAULT BRANCH

Replays your branch commits on top of the latest default branch, preserving each commit individually.

**Example:** 3 commits on `luc/new-feature` + 10 new commits on `main` (or `master`/`develop`) → your 3 commits replayed on top of those 10.

## STEP 1: Capture current state

```bash
BRANCH=$(git branch --show-current)
TICKET=$(echo "$BRANCH" | grep -oE ‘[A-Z]+-[0-9]+’ | head -1 || echo "")
DEFAULT_BRANCH=$(gh repo view --json defaultBranchRef --jq ‘.defaultBranchRef.name’ 2>/dev/null || echo "main")
echo "BRANCH: $BRANCH"
echo "TICKET: $TICKET"
echo "DEFAULT_BRANCH: $DEFAULT_BRANCH"

# Commits on our branch (will be replayed)
git log "$DEFAULT_BRANCH"..HEAD --oneline

# Files we touch
git diff "$DEFAULT_BRANCH" --stat
```

Record: the commit list and changed files. Used for verification after the rebase.

**Gotcha:** If `BRANCH` is empty or `HEAD` (detached HEAD), stop and tell the user to checkout a real feature branch before rebasing.

## STEP 2: Working tree must be clean

```bash
git status --porcelain
```

If there is **any** output (staged or unstaged changes, untracked files you care about):

`AskUserQuestion` — question: "Your working tree is not clean. Rebase requires a clean tree (or stashed work). How do you want to proceed?" / header: "Unclean working tree" / options:

- `Stash changes and continue` → run `git stash push -u -m "myproj-flux-rebase-wip"`. Set an internal flag that a stash was created — STEP 9 will offer to pop it.
- `Abort` → stop. Do not rebase.

If the tree is already clean, continue to STEP 3.

## STEP 3: Sync local default branch with origin

```bash
git fetch origin "$DEFAULT_BRANCH":"$DEFAULT_BRANCH"
```

> If this fails because the local branch has diverged from origin, use `git fetch origin "$DEFAULT_BRANCH":"$DEFAULT_BRANCH" --force`.
> ⚠️ `--force` overwrites your local branch — only safe if you never commit directly to `$DEFAULT_BRANCH`.

**Gotcha:** If `$DEFAULT_BRANCH` does not exist locally yet, use `git fetch origin "$DEFAULT_BRANCH"` and ensure you have a local branch tracking `origin/$DEFAULT_BRANCH` (e.g. `git branch -u "origin/$DEFAULT_BRANCH" "$DEFAULT_BRANCH"` once) before relying on the `branch:branch` refspec.

## STEP 4: Identify potential conflicts (high-risk files)

Overlap of “files changed on `$DEFAULT_BRANCH` since the merge base” and “files changed on your branch” flags **likely** conflict hotspots — not a guarantee (conflicts can appear elsewhere; some overlaps merge cleanly).

```bash
# Files changed on default branch since our branch diverged
git diff --name-only HEAD...”$DEFAULT_BRANCH”

# Files changed on our branch
git diff --name-only “$DEFAULT_BRANCH”..HEAD
```

For any file appearing in **both** lists: read both sides to understand intent before rebasing.

## STEP 5: Rebase onto default branch

```bash
git rebase "$DEFAULT_BRANCH"
```

Git will replay each of your commits one at a time onto the tip of `$DEFAULT_BRANCH`. If there are no conflicts, this completes automatically and you can skip to STEP 7.

## STEP 6: Resolve conflicts (if any — repeat per commit)

During rebase, Git pauses at each commit that conflicts. For each pause:

```bash
git status
git diff --name-only --diff-filter=U
```

Use `git status` as the source of truth (including renames and unmerged paths that are not plain “both modified”).

### Resolution principles

- Aim for a result that matches the **intent of the commit being replayed** and is **consistent with current `$DEFAULT_BRANCH`**. Do not drop the other side’s changes without a clear reason (e.g. `$DEFAULT_BRANCH` removed deprecated code — follow that removal if correct).
- Every unmerged path must reach a resolved state and be **staged** (`git add` / `git rm` as appropriate) before `git rebase --continue`.

### By scenario (add a line or two of reasoning in your summary when non-trivial)

| Scenario                                                            | What to do                                                                                                                                                     |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Text / conflict markers**                                         | Edit the file, remove `<<<<<<<`, `=======`, `>>>>>>>`, then `git add <file>`.                                                                                  |
| **Modify/delete** — one side changed the file, the other deleted it | Decide keep file (possibly with merged content) vs delete. Keeping: fix content then `git add <file>`. Deleting: `git rm <file>`.                              |
| **Binary or generated files** (no usable markers)                   | Choose one side or regenerate: e.g. `git checkout --ours -- <file>` or `git checkout --theirs -- <file>`, or replace the file manually, then `git add <file>`. |
| **Rename / complex unmerged states**                                | Follow `git status` paths; use `git add` on the correct final path after resolving.                                                                            |
| **Submodules**                                                      | Do not guess: use submodule workflow (`git submodule status`, update pointer as intended, `git add` submodule path) or stop and ask the user.                  |

### If `git rebase --continue` fails

- Grep or search for leftover `<<<<<<<` / conflict markers.
- Run `git diff --check` for whitespace or conflict artifacts.
- Ensure **all** previously unmerged files are staged; unstaged resolutions block continue.

### Empty commits after resolution

If Git says the commit is now empty: **`git rebase --skip`** only when you are sure the replayed change is fully redundant (e.g. identical patch already on `$DEFAULT_BRANCH`). Skipping drops a commit — default to investigating rather than skipping blindly.

> Abort at any time: `git rebase --abort` (restores pre-rebase state; does not restore an unstashed stash — your stash from STEP 2 remains).

## STEP 7: Verify — history and files

```bash
# Commits on top of default branch (see note below on count)
git log "$DEFAULT_BRANCH"..HEAD --oneline

# Changed files vs default branch — should reflect your work (paths may shift if trees moved)
git diff "$DEFAULT_BRANCH" --stat
```

**Commit count:** Expect the **same number of commits** as in STEP 1 only if your branch was **linear** (no merge commits you introduced). If you had merge commits from `$DEFAULT_BRANCH` into the branch, the replayed count can differ — compare **content** (`git diff "$DEFAULT_BRANCH" --stat`, behavior) rather than count alone.

Confirm history and diffs match expectations (no dropped features). If changes are missing — investigate before pushing.

## STEP 8: Confirm push (AskUserQuestion)

After a rebase, commit hashes differ from any previous push of the same branch. Choose the right push: first-time upstream vs `--force-with-lease` when the branch already exists on the remote.

```bash
git rev-parse @{u} >/dev/null 2>&1 && echo HAS_UPSTREAM || echo NO_UPSTREAM
```

- **`NO_UPSTREAM`** (first push of this branch): `AskUserQuestion` — question: "Rebase is complete and verified. Push this branch and set upstream with `git push -u origin \"$BRANCH\"`? (No force needed.)" / header: "Push branch" / options: `Yes, push now` | `No, I'll push manually later`

  - Yes → `git push -u origin "$BRANCH"`
  - No → skip push; say so in STEP 9.

- **`HAS_UPSTREAM`**: `AskUserQuestion` — question: "Rebase rewrote history. Push with `git push --force-with-lease origin \"$BRANCH\"`? Refuses if someone else pushed in the meantime. Only do this for your own feature branch — never `$DEFAULT_BRANCH`." / header: "Push rebased branch" / options: `Yes, force-with-lease now` | `No, I'll push manually later`
  - Yes → `git push --force-with-lease origin "$BRANCH"`
  - No → skip push; say so in STEP 9.

If `--force-with-lease` fails because the remote moved, run `git fetch origin`, re-evaluate (and re-ask if appropriate), then retry.

**Gotcha:** `--force-with-lease` can still fail if the remote branch was deleted/recreated or the ref lease is stale — fetch and understand remote state before forcing.

> ⚠️ Never `git push --force` without lease, and never force-push `$DEFAULT_BRANCH` (see HARD CONSTRAINT).

## STEP 9: Summarize

Report:

- `$TICKET` (if any) and `$BRANCH`
- Original commits from STEP 1 vs final `git log "$DEFAULT_BRANCH"..HEAD --oneline` (note if merge commits made counts differ)
- How many commits from `$DEFAULT_BRANCH` were incorporated under you
- Conflicts: how many stops, which files, any modify/delete/binary/submodule cases
- Push: done vs deferred by user choice
- If STEP 2 stashed: use `AskUserQuestion` — question: "You stashed changes before the rebase. Do you want to pop the stash now?" / header: "Restore stash" / options: `Yes, pop stash now` | `No, I'll pop it manually later`
  - Yes → run `git stash pop`. If it produces conflicts, list the conflicted files and instruct the user to resolve them manually (`git add <file>` after editing, then `git stash drop` once done — do NOT run `git stash pop` again).
  - No → remind the user to run `git stash pop` manually when ready.

## HARD CONSTRAINT

`//flux/rebase` MUST NOT squash or modify commit content except as required for conflict resolution during `git rebase --continue`. MUST NOT commit to `$DEFAULT_BRANCH`. MUST NOT use `git push --force` (use `--force-with-lease` when updating an existing remote branch). The only permitted history edits are the rebase itself and conflict resolutions in STEP 6.

## Propose next step

Then propose the next step: `//flux/create-pr` (include arguments if needed).

Valid `//flux` commands: `//flux/config`, `//flux/create-jira`, `//flux/new`, `//flux/ask`, `//flux/split`, `//flux/aug`, `//flux/exec`, `//flux/qa`, `//flux/tests`, `//flux/commit`, `//flux/create-pr`, `//flux/review`, `//flux/address-feedback`, `//flux/status`, `//flux/view-looper`, `//flux/auto-pilot`, `//flux/rebase`. Do NOT suggest any command not on this list.

=================
$ARGUMENTS
