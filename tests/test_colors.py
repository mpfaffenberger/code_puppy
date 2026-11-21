"""Code Puppy's default theme: 0.0.x's colours, readable on light and dark terminals."""

from __future__ import annotations

import pytest

from code_puppy import colors

LIGHT_BACKGROUND = "#FFFFFF"
DARK_BACKGROUND = "#1E1E1E"
MIN_CONTRAST = 3.5


def _luminance(colour: str) -> float:
    channels = (int(colour[index : index + 2], 16) / 255 for index in (1, 3, 5))
    red, green, blue = (
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    )
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(a: str, b: str) -> float:
    darker, lighter = sorted((_luminance(a), _luminance(b)))
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("colour", colors.TEXT)
@pytest.mark.parametrize("background", [LIGHT_BACKGROUND, DARK_BACKGROUND])
def test_text_reads_on_light_and_dark_terminals(colour: str, background: str) -> None:
    assert _contrast(colour, background) >= MIN_CONTRAST


def test_every_role_paints_in_a_text_colour() -> None:
    text = set(colors.TEXT)
    for name, value in colors.ROLES.items():
        if name.startswith("DIFF_"):
            continue
        shades = value if isinstance(value, tuple) else (value.removeprefix("bold "),)
        assert set(shades) <= text, name


def test_hues_match_code_puppy_0_0_x() -> None:
    """Accent bright blue, info cyan, success green, warnings yellow, errors red."""
    assert colors.ROLES["ACCENT"] == f"bold {colors.BLUE}"
    assert colors.ROLES["BANNER"] == (colors.BLUE, colors.CYAN, colors.GREEN)
    expected_sgr = {"LITHIUM": 94, "AI_CYAN": 36, "AQUA": 32, "AI_YELLOW": 33}
    for name, code in expected_sgr.items():
        assert colors.SHADES[name].sgr == code
    assert colors.SHADES["CALCIUM"].sgr == 31


def test_colours_are_distinct() -> None:
    """The theme keys its palette slots by colour, so a repeat would lose one."""
    shades = [
        shade.colour for shade in (*colors.SHADES.values(), *colors.NEON.values())
    ]
    assert len(shades) == len(set(shades))


def test_pax_paints_with_code_puppys_colours(installed_distribution: None) -> None:
    from pydantic_ai_pax.ui.rendering import splash, theme

    assert theme.ACCENT == f"bold {colors.BLUE}"
    assert theme.color(theme.ERROR) == colors.RED
    assert theme.BANNER == colors.ROLES["BANNER"]
    assert theme.diff_theme().addition == colors.ROLES["DIFF_ADDITION"]
    assert splash.LITHIUM == colors.NEON["LITHIUM"].colour


def test_sixteen_colour_terminals_get_0_0_x_codes(
    installed_distribution: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pydantic_ai_pax.ui.rendering import theme

    monkeypatch.delenv("COLORTERM", raising=False)
    assert theme.sgr(theme.ACCENT) == "\x1b[1;94m"
    assert theme.sgr(theme.SUCCESS) == "\x1b[32m"
    assert theme.sgr(theme.SUGAR) == "\x1b[39m"


def test_a_palette_paints_each_shade_from_its_slot(
    installed_distribution: None,
) -> None:
    from pydantic_ai_pax.ui.rendering import theme

    name = next(choice for choice in theme.names() if choice != "default")
    with theme.use(lambda: name):
        palette = theme.current()
        assert palette is not None
        for shade in colors.SHADES.values():
            slot = palette.ansi[shade.slot]
            expected = theme._readable(slot, palette.bg, palette.fg)
            assert theme.color(shade.colour) == expected
