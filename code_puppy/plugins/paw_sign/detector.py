"""Detection + rewriting for paw-signing git commit commands.

The single public entry point is :func:`paw_sign_command`. It is deliberately
conservative: it only rewrites a command when doing so is provably safe, and
returns ``None`` (leave it alone) for anything ambiguous. A corrupted
``git commit`` is far worse than a missing paw print.

Safety strategy
---------------
We use :mod:`shlex` purely to *analyse* the command (respecting quotes), never
to rebuild it. We only append when the ``git commit -m`` invocation is the
**last** command in the chain -- then a plain string append unambiguously
flows into that commit, preserving any shell substitutions, heredocs, or exotic
quoting in the original untouched.

Examples that get signed::

    git commit -m "fix the thing"
    git add . && git commit -m "fix the thing"
    git commit --message "wip" --amend

Examples we leave alone (return ``None``)::

    git commit -m "wip" && git push      # commit isn't last
    git commit --amend                    # editor commit, no -m
    git status                            # not a commit at all
"""

import shlex
from typing import List, Optional

# NOTE: the paw print is written as a unicode escape (U+1F43E) on purpose.
# This repo's emoji_filter strips literal emoji from file writes, which would
# silently eat the paw. The escape is plain ASCII in source and resolves to the
# real glyph at runtime.
PAW_SIGN = "[-- paw-signed: code-puppy \U0001f43e --]"

# A stable substring (no emoji) used for idempotency -- survives even if the
# emoji has been stripped from a previously-signed command.
_ALREADY_SIGNED = "paw-signed: code-puppy"

# Shell operators that separate one command from the next.
_OPERATORS = frozenset({"&&", "||", ";", "|", "&"})


def _split_segments(tokens: List[str]) -> List[List[str]]:
    """Split a flat token list into command segments on shell operators."""
    segments: List[List[str]] = [[]]
    for tok in tokens:
        if tok in _OPERATORS:
            segments.append([])
        else:
            segments[-1].append(tok)
    return segments


def _is_commit_with_message(segment: List[str]) -> bool:
    """Return True if a token segment is ``git commit`` carrying a message flag.

    Handles ``-m``, ``--message``, ``--message=...`` and combined short flags
    such as ``-am`` / ``-sm``. Deliberately rejects editor-style commits
    (``git commit`` / ``git commit --amend`` with no message flag).
    """
    if len(segment) < 2 or segment[0] != "git" or segment[1] != "commit":
        return False
    for tok in segment[2:]:
        if tok in ("-m", "--message") or tok.startswith("--message="):
            return True
        # Combined short flags like -am, -sm. Guard against long flags such as
        # --amend, which contain an "m" but are not message flags.
        if tok.startswith("-") and not tok.startswith("--") and "m" in tok:
            return True
    return False


def paw_sign_command(command: str) -> Optional[str]:
    """Return ``command`` with the paw-sign appended, or ``None`` for no change.

    Args:
        command: The shell command about to run.

    Returns:
        The rewritten command string when it is a safe-to-sign ``git commit``
        whose message-bearing invocation is the last in the chain; otherwise
        ``None`` (meaning: leave the original command untouched).
    """
    # Cheap pre-filters before paying for shlex.
    if not command or "commit" not in command:
        return None
    if _ALREADY_SIGNED in command:
        return None

    try:
        tokens = shlex.split(command)
    except ValueError:
        # Unbalanced quotes / un-parseable -- never risk mangling it.
        return None

    if not tokens:
        return None

    segments = _split_segments(tokens)
    # Only safe to append at the end when the *last* segment is the commit.
    if not _is_commit_with_message(segments[-1]):
        return None

    return f"{command.rstrip()} -m {shlex.quote(PAW_SIGN)}"
