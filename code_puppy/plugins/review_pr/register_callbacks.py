"""Plugin: `/review-pr` — hand the agent a structured PR review mission.

Usage:
    /review-pr                  Review the PR for the current branch
    /review-pr 123              Review PR #123 in the current repo
    /review-pr <github-url>     Review the PR at the given URL
    /review-pr --help           Show usage

The command itself is dumb on purpose (YAGNI): it just builds a beefy prompt
and returns it. The *agent* does the heavy lifting via `gh` + shell tools.
That keeps responsibilities clean (SRP) — plugin = command framing, agent =
code review.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error, emit_info


COMMAND_NAME = "review-pr"


_USAGE = (
    "Usage: /review-pr [PR_NUMBER | GITHUB_PR_URL]\n"
    "  /review-pr               → review the current branch's open PR\n"
    "  /review-pr 123           → review PR #123 in the current repo\n"
    "  /review-pr <url>         → review the PR at that GitHub URL"
)


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            COMMAND_NAME,
            "Review a GitHub PR (uses `gh`). Optional arg: PR number or URL.",
        )
    ]


def _parse_target(command: str) -> Optional[str]:
    """Return the raw PR target (number, URL, or '' for current branch).

    Returns None if the user asked for --help (already handled).
    """
    parts = command.split(maxsplit=1)
    if len(parts) == 1:
        return ""

    arg = parts[1].strip()
    if arg in {"--help", "-h", "help"}:
        emit_info(_USAGE)
        return None
    return arg


def _build_prompt(target: str) -> str:
    """Compose the review instructions sent to the agent."""
    if target:
        target_clause = (
            f"The user wants you to review this PR: **{target}**.\n"
            "Resolve it with the `gh` CLI (number → current repo, URL → that repo)."
        )
    else:
        target_clause = (
            "No PR was specified — review the PR associated with the **current branch**.\n"
            "Use `gh pr view --json number,url,title,headRefName,baseRefName` to discover it.\n"
            "If no PR exists for the current branch, stop and tell the user."
        )

    return f"""You are doing a **pull request review**. Be thorough, fair, and a little spicy.

{target_clause}

## Step 1 — Gather context
Run (in order, only what you need):
  1. `gh pr view <target> --json number,title,author,url,baseRefName,headRefName,body,additions,deletions,changedFiles,labels,isDraft,mergeable,reviewDecision`
  2. `gh pr diff <target>` to read the actual diff
  3. `gh pr checks <target>` for CI status
  4. (Optional) `gh pr view <target> --comments` if you need existing discussion

If any command fails (auth, not-a-repo, no PR), surface a clean error and stop.

## Step 2 — Analyze
Walk the diff and judge it on:
  - **Correctness** — bugs, off-by-ones, race conditions, error handling, edge cases
  - **Design** — SOLID, DRY, YAGNI violations; leaky abstractions; tight coupling
  - **Readability** — naming, function size, comments where the *why* is non-obvious
  - **Tests** — coverage for new logic, missing edge cases, brittle mocks
  - **Security** — injection, secrets, unvalidated input, authz gaps
  - **Performance** — obvious quadratic loops, N+1 queries, needless allocations
  - **Style/Lint** — only call out if it's actually wrong, not just taste

Honor the Zen of Python even for non-Python code.

## Step 3 — Report
Output a single markdown report with these sections (omit empty ones):

### 🫧 PR Review: <title> (#<number>)
- **Author:** …  **Base ← Head:** …  **CI:** …  **Mergeable:** …
- **TL;DR:** one-sentence verdict.

### ✅ What's good
Bullet list. Be specific — point at files/functions.

### 🔴 Blocking issues
Things that *must* be fixed before merge. Each item:
- **File:line** — what's wrong, why, and a concrete fix.

### 🟡 Suggestions (non-blocking)
Nice-to-haves, refactors, follow-ups.

### 🧪 Test gaps
Specific scenarios that should have tests.

### 🏁 Recommendation
One of: **APPROVE**, **REQUEST CHANGES**, or **COMMENT** — with a one-line justification.

## Rules
- Do **NOT** post the review to GitHub. Just print it. The user decides whether to submit.
- Don't run mutating `gh` commands (no `gh pr review --approve`, no merges, no closes).
- If the diff is huge (>1500 lines), say so and focus on the highest-signal files.
- Quote short snippets (≤10 lines) when calling out specific code.
"""


def _handle_custom_command(command: str, name: str) -> Optional[object]:
    if name != COMMAND_NAME:
        return None

    target = _parse_target(command)
    if target is None:
        # --help was shown; mark as handled without invoking the model.
        return True

    # Sanity-check gh is available so we fail fast with a friendly hint.
    import shutil

    if shutil.which("gh") is None:
        emit_error(
            "/review-pr: GitHub CLI (`gh`) not found on PATH. "
            "Install it from https://cli.github.com/ and run `gh auth login`."
        )
        return True

    emit_info(f"🫧 Fetching PR review mission for: {target or '<current branch>'}")
    return _build_prompt(target)


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)


__all__ = [
    "COMMAND_NAME",
    "_custom_help",
    "_handle_custom_command",
    "_build_prompt",
    "_parse_target",
]
