---
name: create-pr
description: Create a GitHub PR for the current branch, or show the existing PR URL and status
---

# CREATE A GITHUB PULL REQUEST

## STEP 1: Validate branch

```bash
BRANCH=$(git branch --show-current)
echo "CURRENT_BRANCH: $BRANCH"
```

If `BRANCH` is `main` or `master`, print and stop:

```
Error: You are on the default branch ("$BRANCH").
Switch to a feature branch before opening a PR.
```

## STEP 2: Check for existing PR

```bash
EXISTING=$(gh pr view --json number,url,state,title 2>/dev/null)
echo "$EXISTING"
```

If output is non-empty JSON, print and stop:

```
A PR already exists for this branch:
  Title:  <title>
  URL:    <url>
  State:  <state>
```

## STEP 3: Check for commits ahead of default branch

```bash
DEFAULT_BRANCH=$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || echo "main")
echo "DEFAULT_BRANCH: $DEFAULT_BRANCH"
COMMIT_COUNT=$(git rev-list HEAD ^"origin/${DEFAULT_BRANCH}" --count 2>/dev/null || echo "0")
echo "COMMIT_COUNT: $COMMIT_COUNT"
```

If `COMMIT_COUNT` is `0`, print and stop:

```
Warning: No commits ahead of origin/$DEFAULT_BRANCH.
Push at least one commit before opening a PR.
```

## STEP 4: Derive PR title from branch name

```bash
BRANCH=$(git branch --show-current)
SLUG=$(echo "$BRANCH" | sed 's|.*/||')
JIRA_ID=$(echo "$SLUG" | grep -oE '^[A-Z]+-[0-9]+' || true)
if [ -n "$JIRA_ID" ]; then
  DESC=$(echo "$SLUG" | sed "s/^${JIRA_ID}-//")
else
  DESC="$SLUG"
fi
TITLE_DESC=$(echo "$DESC" | tr '-' ' ' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2)); print}')
if [ -n "$JIRA_ID" ]; then
  PR_TITLE="${JIRA_ID}: ${TITLE_DESC}"
else
  PR_TITLE="${TITLE_DESC}"
fi
echo "PR_TITLE: $PR_TITLE"
```

Examples: `rio/MYPROJ-745-add-create-pr-command` → `MYPROJ-745: Add Create Pr Command` | `feat/dark-mode` → `Dark Mode`

## STEP 5: Detect PR template

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
TEMPLATE_PATH=""

# Check single-file locations in GitHub-documented priority order
for candidate in \
  ".github/pull_request_template.md" \
  ".github/PULL_REQUEST_TEMPLATE.md" \
  "docs/pull_request_template.md" \
  "docs/PULL_REQUEST_TEMPLATE.md" \
  "pull_request_template.md" \
  "PULL_REQUEST_TEMPLATE.md"; do
  if [ -f "$REPO_ROOT/$candidate" ]; then
    TEMPLATE_PATH="$REPO_ROOT/$candidate"
    break
  fi
done

# Check directory locations if no single-file match found
TEMPLATE_NOTE=""
TEMPLATE_DIR=""
if [ -z "$TEMPLATE_PATH" ]; then
  for dir in \
    ".github/PULL_REQUEST_TEMPLATE" \
    "docs/PULL_REQUEST_TEMPLATE" \
    "PULL_REQUEST_TEMPLATE"; do
    if [ -d "$REPO_ROOT/$dir" ]; then
      TEMPLATE_COUNT=$(ls "$REPO_ROOT/$dir/"*.md 2>/dev/null | wc -l | tr -d ' ')
      if [ "$TEMPLATE_COUNT" -gt 1 ]; then
        TEMPLATE_NOTE="Multiple templates found in $dir — automatic selection is ambiguous. Falling back to default body."
        TEMPLATE_DIR="$REPO_ROOT/$dir"
        break
      elif [ "$TEMPLATE_COUNT" -eq 1 ]; then
        TEMPLATE_PATH=$(ls "$REPO_ROOT/$dir/"*.md 2>/dev/null | head -1)
        break
      fi
    fi
  done
fi

if [ -n "$TEMPLATE_PATH" ]; then
  echo "TEMPLATE_FOUND: yes"
  echo "TEMPLATE_PATH: $TEMPLATE_PATH"
  echo "---TEMPLATE_BEGIN---"
  cat "$TEMPLATE_PATH"
  echo "---TEMPLATE_END---"
else
  echo "TEMPLATE_FOUND: no"
  if [ -n "$TEMPLATE_NOTE" ]; then
    echo "TEMPLATE_NOTE: $TEMPLATE_NOTE"
    ls "$TEMPLATE_DIR/"*.md 2>/dev/null | sed 's|.*/||' | while read f; do echo "  - $f"; done
  fi
fi
```

## STEP 6: Generate PR body from diff

```bash
git log HEAD ^origin/${DEFAULT_BRANCH} --oneline
git diff origin/${DEFAULT_BRANCH}...HEAD --stat
```

**If a template was found in STEP 5:**

Parse every section heading from the template file (e.g., `## 📝 Problem`, `## 💡 Solution`, `### 📚 References`, `### CCM:`, `### 🖼️ Screenshots`, `### 📖 Build History`).

Fill in **EVERY section** from the template using context from the current implementation:

- Do not invent your own sections
- Do not skip any sections
- Do not reorder sections
- Match the exact heading text, emoji, and formatting from the template
- Preserve verbatim any HTML comments, unchecked checkboxes (`- [ ] ...`), and static non-heading text from the template; only replace designated placeholder text (e.g., italic or angle-bracket placeholders like `*describe here*` or `<your text>`)

**If no template was found:**

Write a PR body with:

- `## Summary` — 1–3 bullets: what changed and why (specific to actual commits/files, no placeholders)
- `## Test plan` — concrete manual verification steps specific to the changes

In both cases, the body is written as literal text inline in the heredoc in STEP 7. Do NOT use a shell variable for the body.

## STEP 7: Create the PR

Do NOT pass `--web`, `--fill`, `--draft`, `--reviewer`, `--label`, `--milestone`, or `--assignee`. Write body inline in the heredoc — do NOT use shell variables for it:

```bash
PR_URL=$(gh pr create \
  --title "$PR_TITLE" \
  --body "$(cat <<'EOF'
<generated body — either template-filled or fallback Summary+Test plan>
EOF
)")
echo "PR_URL: $PR_URL"
```

On non-zero exit, surface the raw `gh` error verbatim. Common causes: not authenticated (`gh auth login`), no remote tracking branch (`git push -u origin <branch>`), network/API error.

## STEP 8: Print result

```
PR created successfully:
  Title:  <PR_TITLE>
  URL:    <PR_URL>
```

Do NOT open a browser window.

## HARD CONSTRAINT

`/flux/create-pr` MUST NOT modify any source files, task files, or config files. The only permitted operations are reading git history, running `gh` commands, and pushing the branch if needed. Write the PR body inline — never via shell variables. Do NOT open a browser window.

## Propose next step

Then propose the next step: `/flux/review`

Valid `//flux` commands: `/flux/config`, `/flux/new`, `/flux/ask`, `/flux/split`, `/flux/aug`, `/flux/exec`, `/flux/qa`, `/flux/tests`, `/flux/commit`, `/flux/create-pr`, `/flux/review`, `/flux/address-feedback`, `/flux/status`, `/flux/auto-pilot`, `/flux/rebase`. Do NOT suggest any command not on this list.
