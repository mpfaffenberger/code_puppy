"""Tiered budget-aware packing for the system-prompt recall block.

Three priority classes, fed from the kennel, sized to fit a configurable
token budget without ever calling an LLM or shipping a tokenizer:

* **P0 - user preferences**: every drawer in ``user:default``. Short,
  durable, pervasive ("Mike hates emojis"). Capped at ~30% of budget.
* **P1 - sticky repo notes**: drawers in ``repo:<cwd>`` with ``role='note'``,
  i.e. content written via the ``kennel_remember`` tool. Highest signal-to-
  token ratio in the kennel. Capped at ~30% of budget.
* **P2 - recent assistant responses**: drawers in ``repo:<cwd>`` with
  ``role='assistant'``. Fills whatever budget remains after P0 + P1.

Token budget is enforced via the well-known 1-token approximate-4-chars
heuristic. Cheap, zero-dep, accurate to plus-or-minus 20% which is fine
for "do not blow the context."
"""

from __future__ import annotations

from dataclasses import dataclass

from . import kennel
from .config import (
    CHARS_PER_TOKEN,
    MIN_DRAWER_CHARS,
    PROMPT_BUDGET_CHARS,
    PROMPT_BUDGET_TOKENS,
    STICKY_QUOTA,
    USER_PREFS_QUOTA,
)
from .kennel import Drawer
from .wings import USER_WING, detect_cwd, repo_wing

# Reserve a little slack so the rendered header/scaffolding doesn't push us
# over the requested budget. Headers + section dividers eat ~50 tokens.
_HEADER_SLACK_CHARS = 50 * CHARS_PER_TOKEN

# We over-fetch from SQLite then truncate to fit. Cheap, simple.
_FETCH_LIMIT = 50

# How many chars of remaining budget is too little to bother starting a new
# drawer with. Avoids "...truncated]" being most of the rendered line.
_MIN_REMAINING_CHARS = 120


@dataclass(slots=True)
class PackSection:
    title: str
    lines: list[str]
    used_chars: int


def _agent_label(d: Drawer) -> str:
    meta = d.metadata or {}
    return str(meta.get("agent") or d.role or "?")


def _format_drawer(d: Drawer, max_chars: int) -> str:
    """Render one drawer to a markdown bullet, fitting within ``max_chars``.

    The bullet looks like ``- [ts] _agent_ : content...`` with the content
    truncated as needed. Returns an empty string if the bullet skeleton
    alone wouldn't fit.
    """
    head = f"- [{d.ts}] _{_agent_label(d)}_ : "
    if max_chars <= len(head) + 20:
        return ""
    body_budget = max_chars - len(head)
    body = d.content.strip().replace("\n", " ")
    if len(body) > body_budget:
        body = body[: body_budget - 1].rstrip() + "..."
    return head + body


def _pack_class(
    drawers: list[Drawer],
    budget_chars: int,
    min_chars: int = MIN_DRAWER_CHARS,
) -> PackSection:
    """Greedily pack drawers into ``budget_chars``, newest first.

    Skips drawers smaller than ``min_chars`` (probably noise). Truncates
    the last drawer if it would otherwise push us over. Stops once the
    remaining budget gets too small to be useful.
    """
    lines: list[str] = []
    used = 0
    for d in drawers:
        if len(d.content.strip()) < min_chars:
            continue
        remaining = budget_chars - used
        if remaining < _MIN_REMAINING_CHARS:
            break
        rendered = _format_drawer(d, max_chars=remaining)
        if not rendered:
            break
        lines.append(rendered)
        used += len(rendered) + 1  # +1 for the newline that joins them
    return PackSection(title="", lines=lines, used_chars=used)


def pack(cwd_override: str | None = None) -> str | None:
    """Build the system-prompt recall block under the configured budget.

    Returns ``None`` when there is nothing useful to surface (empty kennel,
    every drawer too short, etc.) - the ``load_prompt`` callback contract
    interprets ``None`` as "skip me".
    """
    cwd = cwd_override if cwd_override is not None else detect_cwd()
    repo_w = repo_wing(cwd)

    total_budget = max(0, PROMPT_BUDGET_CHARS - _HEADER_SLACK_CHARS)
    p0_budget = int(total_budget * USER_PREFS_QUOTA)
    p1_budget = int(total_budget * STICKY_QUOTA)

    # P0 - user preferences. We pull every role; user-wing drawers tend to
    # be ``role='note'`` (explicit) but allow assistant too just in case.
    user_drawers = kennel.recent_drawers(USER_WING, limit=_FETCH_LIMIT)
    p0 = _pack_class(user_drawers, p0_budget)
    p0.title = "User Preferences"

    # P1 - sticky notes for this repo (role='note' only).
    sticky = kennel.recent_drawers(repo_w, limit=_FETCH_LIMIT, role="note")
    p1 = _pack_class(sticky, p1_budget)
    p1.title = "Project Decisions"

    # P2 - recent assistant responses fill whatever budget remains.
    p2_budget = total_budget - p0.used_chars - p1.used_chars
    assistant = kennel.recent_drawers(repo_w, limit=_FETCH_LIMIT, role="assistant")
    p2 = _pack_class(assistant, max(0, p2_budget))
    p2.title = "Recent Context"

    sections = [s for s in (p0, p1, p2) if s.lines]
    if not sections:
        return None

    return _render(sections, repo_w)


def _render(sections: list[PackSection], repo_w: str) -> str:
    """Render the packed sections into the final markdown block."""
    out: list[str] = [
        "## Mist Memory - Memory",
        (
            f"_Repo wing: `{repo_w}` | token budget: "
            f"{PROMPT_BUDGET_TOKENS} (~{PROMPT_BUDGET_CHARS} chars)_"
        ),
        "",
    ]
    for s in sections:
        out.append(f"### {s.title}")
        out.extend(s.lines)
        out.append("")
    return "\n".join(out)
