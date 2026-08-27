"""The REPL prompt must fit the terminal it is drawn in.

Regression coverage for a prompt that wrapped at 80 columns -- the most
common terminal width there is -- and split its own ``>>>`` marker across
two rows, leaving the user typing after a lone ``>``.

``platform_utils.startup_banner_text`` already budgets the *banner* by
width (CODE PUPPY -> PUP below 79 columns, pinned by
tests/test_platform_utils.py). These tests hold the prompt to the same
standard.
"""

import inspect
import os

from rich.cells import cell_len

from code_puppy.command_line import completers
from code_puppy.command_line.completers import (
    _fit_prompt_parts,
    _middle_truncate,
    get_prompt_with_active_model,
)

BASE = ">>> "


def rendered_width(parts, base: str = BASE) -> int:
    """Cells consumed by the prompt prefix as it is actually assembled."""
    puppy, agent, model, cwd = parts
    total = 0
    if puppy:
        total += cell_len(puppy) + 1
    if agent:
        total += cell_len(agent) + 3
    if model:
        total += cell_len(model) + 1
    if cwd:
        total += cell_len(cwd) + 3
    return total + cell_len(base)


def test_the_exact_case_from_the_audit_fits_in_80_columns():
    """The captured 80-col prompt used to wrap and split the arrow."""
    parts = _fit_prompt_parts(
        "airmac-puppy",
        "Code-Puppy 🐶",
        "[claude-code-claude-opus-4-8-long]",
        "~/codepuppy",
        BASE,
        80,
    )
    assert rendered_width(parts) <= 80


def test_arrow_is_never_what_gets_dropped(monkeypatch):
    """Whatever else goes, the prompt still ends in an arrow.

    Width is driven by patching ``shutil.get_terminal_size`` rather than
    by a keyword argument: the shipped ``statusline`` and
    ``prompt_newline`` plugins wrap this function with
    ``def patched(base=">>> ")``, so a new parameter would raise
    TypeError through them and take the prompt out entirely.
    """
    monkeypatch.setattr(
        completers.shutil,
        "get_terminal_size",
        lambda fallback=None: os.terminal_size((20, 24)),
    )
    fragments = get_prompt_with_active_model(BASE)
    assert fragments, "prompt must never render empty"
    assert fragments[-1][1] == BASE


def test_public_signature_stays_plugin_compatible():
    """Shipped plugins wrap this as ``patched(base)`` with no **kwargs.

    Adding a parameter to the public prompt builder is a breaking change
    for the plugin ecosystem, not just an internal refactor.
    """
    params = list(inspect.signature(get_prompt_with_active_model).parameters)
    assert params == ["base"], (
        "statusline/prompt_newline wrap this as patched(base=...); "
        f"extra parameters break them. Got: {params}"
    )


def test_dual_model_worst_case_fits():
    """An agent override renders TWO model ids -- the widest real case."""
    parts = _fit_prompt_parts(
        "puppy",
        "Agent",
        "[openrouter/anthropic/claude-sonnet-4.5 → anthropic/claude-opus-4-1-20250805]",
        "~/work/clients/acme/backend/services/api",
        BASE,
        80,
    )
    assert rendered_width(parts) <= 80


def test_model_survives_longer_than_decoration():
    """You need to know which model is spending your money."""
    puppy, agent, model, cwd = _fit_prompt_parts(
        "airmac-puppy", "Code-Puppy", "[gpt-5]", "~/a/b/c/d/e/f/g", BASE, 46
    )
    assert model, "model dropped before puppy name/cwd"
    assert not puppy or not cwd


def test_wide_terminal_keeps_every_segment_intact():
    """No gratuitous trimming when there is room."""
    parts = _fit_prompt_parts(
        "airmac-puppy", "Code-Puppy 🐶", "[gpt-5]", "~/codepuppy", BASE, 200
    )
    assert parts == ("airmac-puppy", "Code-Puppy 🐶", "[gpt-5]", "~/codepuppy")


def test_absurdly_narrow_terminal_degrades_to_bare_arrow():
    """A 20-col terminal gets a usable prompt, not a shredded one."""
    assert _fit_prompt_parts("p", "A", "[m]", "~/x", BASE, 20) == ("", "", "", "")


def test_emoji_counted_as_two_cells_not_one():
    """Naive len() would under-count the agent emoji and still overflow."""
    wide = "🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶"
    assert cell_len(wide) == 20
    parts = _fit_prompt_parts("puppy", wide, "[gpt-5]", "~/codepuppy", BASE, 60)
    assert rendered_width(parts) <= 60


def test_middle_truncate_keeps_both_ends_of_a_model_id():
    """Model ids carry meaning at both ends; a tail ellipsis loses half."""
    out = _middle_truncate("openrouter/anthropic/claude-opus-4-8", 20)
    assert cell_len(out) <= 20
    assert out.startswith("open")
    assert out.endswith("4-8")
    assert "…" in out


def test_fits_across_a_sweep_of_widths():
    """No width between 30 and 200 may overflow."""
    for columns in range(30, 201):
        parts = _fit_prompt_parts(
            "airmac-puppy",
            "Code-Puppy 🐶",
            "[claude-code-claude-opus-4-8-long]",
            "~/codepuppy/deep/nested/path",
            BASE,
            columns,
        )
        assert rendered_width(parts) <= columns, f"overflow at {columns} cols"


def test_leaves_room_to_actually_type():
    """A prompt that fills the line exactly is still unusable."""
    parts = _fit_prompt_parts(
        "airmac-puppy",
        "Code-Puppy 🐶",
        "[claude-code-claude-opus-4-8-long]",
        "~/codepuppy",
        BASE,
        80,
    )
    assert 80 - rendered_width(parts) >= 20, "no room left to type a prompt"
