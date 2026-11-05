"""The repo's own AGENTS.md must fit the default rules cap.

``load_puppy_rules`` keeps only the first ``AGENTS_MD_MAX_CHARS_DEFAULT``
characters of each rules file, so anything past the cap silently drops out of
every agent's system prompt. The file crept over the cap for ten commits
without anyone noticing, cutting off the Rules section entirely.
"""

from pathlib import Path

from code_puppy.config import AGENTS_MD_MAX_CHARS_DEFAULT

REPO_AGENTS_MD = Path(__file__).resolve().parents[1] / "AGENTS.md"


def test_repo_agents_md_fits_default_cap():
    length = len(REPO_AGENTS_MD.read_text(encoding="utf-8"))
    assert length <= AGENTS_MD_MAX_CHARS_DEFAULT, (
        f"AGENTS.md is {length:,} chars; Code Puppy truncates it at "
        f"{AGENTS_MD_MAX_CHARS_DEFAULT:,}. Move reference material into docs/."
    )
