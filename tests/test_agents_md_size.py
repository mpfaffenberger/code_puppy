"""The repo's own AGENTS.md must stay small.

The file is sent to the model with every request, so each character costs
tokens on every turn of every session in this repository. Reference material
belongs in ``docs/``.
"""

from pathlib import Path

AGENTS_MD_BUDGET = 10_000
REPO_AGENTS_MD = Path(__file__).resolve().parents[1] / "AGENTS.md"


def test_repo_agents_md_fits_budget() -> None:
    length = len(REPO_AGENTS_MD.read_text(encoding="utf-8"))
    assert length <= AGENTS_MD_BUDGET, (
        f"AGENTS.md is {length:,} chars; the budget is {AGENTS_MD_BUDGET:,}. "
        "Move reference material into docs/."
    )
