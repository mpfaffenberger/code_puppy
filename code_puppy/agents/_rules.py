"""Rule-file decoding, identity checks, and size limits for agent builds."""

import os
from pathlib import Path
from typing import Optional

from code_puppy.messaging import emit_warning


def _friendly_path(candidate: Path) -> str:
    """Render ``candidate`` as ``~/relative`` when it's under ``$HOME``.

    Keeps the absolute home path out of the system prompt (and out of any
    Slack paste of the agent's "please trim AGENTS.md" reply).
    """
    try:
        return f"~/{candidate.relative_to(Path.home())}"
    except ValueError:
        return str(candidate)


# BOM signatures mapped to their codecs. Check UTF-32 before UTF-16:
# the UTF-32 LE BOM starts with the UTF-16 LE BOM bytes.
_BOM_CODECS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)


def _read_rules_text(candidate: Path) -> Optional[str]:
    """Read a rules file and detect its encoding from the BOM.

    PowerShell redirection (``echo hi > AGENTS.md``) writes UTF-16 LE
    with a BOM. A plain UTF-8 read crashes on it. This helper sniffs
    the BOM, decodes with the correct codec, and never raises. It
    returns ``None`` when the file is not readable.
    """
    try:
        raw = candidate.read_bytes()
    except OSError as exc:
        emit_warning(f"Could not read {candidate}: {exc}")
        return None
    for bom, codec in _BOM_CODECS:
        if raw.startswith(bom):
            try:
                text = raw.decode(codec)
            except UnicodeDecodeError:
                break
            # Drop the BOM character that non-sig codecs keep.
            return text.lstrip("\ufeff")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        emit_warning(
            f"{candidate} is not valid UTF-8; bad bytes were replaced. "
            f"Save the file as UTF-8 to fix this."
        )
        return raw.decode("utf-8", errors="replace")


def _truncate_agents_md(content: str, source: str, max_chars: int) -> str:
    """Cap one AGENTS.md file at ``max_chars`` with a labelled notice.

    Returns ``content`` unchanged when it's within the cap. When it overflows,
    keeps exactly the first ``max_chars`` characters of the original and
    appends a delimited warning addressed to the agent (so the agent can
    surface it to the user on the next turn). ``source`` is a human-readable
    label for the file — used in the warning so the agent can tell the user
    which specific file to trim when multiple files overflow. ``max_chars``
    is resolved once per load by the caller (see ``get_agents_md_max_chars``)
    so a session-wide ``/set`` override is honoured.
    """
    original_len = len(content)
    if original_len <= max_chars:
        return content
    dropped = original_len - max_chars
    notice = (
        f"\n\n--- AGENTS.md truncated ---\n"
        f"The {source} content was truncated: original was "
        f"{original_len:,} chars, {dropped:,} chars dropped. Please tell "
        f"the user to trim {source} below {max_chars:,} "
        f"characters so the full rules can take effect (or raise the cap "
        f"via `/set agents_md_max_chars=<int>`).\n"
        f"--- end truncation notice ---"
    )
    return content[:max_chars] + notice


def _same_file(candidate: Path, other: Optional[Path]) -> bool:
    """True when ``candidate`` is the very file ``other`` names.

    Run from the home directory, ``.code_puppy/AGENTS.md`` *is* the global
    ``~/.code_puppy/AGENTS.md``; loading it again as project rules puts the
    same text into the system prompt twice. Compared by filesystem identity,
    so symlinks and path aliases count as the same file, while a distinct
    project file with identical text still loads.
    """
    if other is None:
        return False
    try:
        return os.path.samefile(candidate, other)
    except OSError:
        return False
