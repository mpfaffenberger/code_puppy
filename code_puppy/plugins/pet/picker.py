"""Interactive 'adopt a pet' picker.

Same look-and-feel as Code Puppy's ``/model`` picker (paginated-ish arrow-key
list, type-to-filter, Enter to choose) but for dogs, with a live ASCII preview
of the highlighted breed so you can see who you're adopting.
"""

from __future__ import annotations

import sys
from typing import List, Optional

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from code_puppy.plugins.pet.species import DOG_SPECIES, list_species

_RARITY_PT_STYLE = {
    "common": "fg:ansiwhite",
    "uncommon": "fg:ansigreen",
    "rare": "fg:ansiblue",
    "epic": "fg:ansimagenta",
    "legendary": "fg:ansiyellow",
}


class PetPickerMenu:
    """Arrow-key dog adoption menu returning the chosen species name."""

    def __init__(self) -> None:
        self.species: List[str] = list_species()
        self.filter_text = ""
        self.selected_index = 0
        self.result: Optional[str] = None

    @property
    def visible(self) -> List[str]:
        if not self.filter_text:
            return self.species
        needle = self.filter_text.lower()
        return [s for s in self.species if needle in s.lower()]

    def _selected_name(self) -> Optional[str]:
        vis = self.visible
        if 0 <= self.selected_index < len(vis):
            return vis[self.selected_index]
        return None

    def _clamp(self) -> None:
        vis = self.visible
        if not vis:
            self.selected_index = 0
        else:
            self.selected_index = max(0, min(self.selected_index, len(vis) - 1))

    def _render(self):
        lines = [("bold cyan", " \U0001f436 Adopt a Pet  "), ("", "\n")]
        filter_label = self.filter_text or "type to filter breeds"
        lines.append(("fg:ansibrightblack", f"  Filter: {filter_label}\n\n"))

        vis = self.visible
        if not vis:
            lines.append(("fg:ansiyellow", "  No breeds match that filter.\n\n"))
            lines.append(("fg:ansibrightblack", "  Backspace "))
            lines.append(("", "clear a char   "))
            lines.append(("fg:ansiyellow", "Esc "))
            lines.append(("", "cancel\n"))
            return lines

        # ── List (left) ────────────────────────────────────────────────────
        for idx, name in enumerate(vis):
            dog = DOG_SPECIES[name]
            is_sel = idx == self.selected_index
            prefix = " \u203a " if is_sel else "   "
            style = "fg:ansiwhite bold" if is_sel else "fg:ansibrightblack"
            lines.append((style, f"{prefix}{name:<11}"))
            lines.append((_RARITY_PT_STYLE.get(dog.rarity, ""), f" {dog.stars}"))
            lines.append(("fg:ansibrightblack", f"  ({dog.rarity})"))
            lines.append(("", "\n"))

        # ── Preview (selected dog) — the one-liner the pet actually shows ───
        sel = self._selected_name()
        if sel:
            dog = DOG_SPECIES[sel]
            pstyle = _RARITY_PT_STYLE.get(dog.rarity, "")
            face = "(\u00b7\u1d25\u00b7)"  # same compact snoot as the toolbar
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", "  preview: "))
            lines.append(("fg:ansibrightcyan", f"{face} "))
            lines.append(("fg:ansiwhite bold", f"{dog.default_name} "))
            lines.append(("fg:ansibrightblack", f"the {sel} "))
            lines.append((pstyle, f" {dog.stars}"))
            lines.append(("fg:ansibrightblack", f"  ({dog.rarity})\n"))

        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  \u2191/\u2193 "))
        lines.append(("", "navigate   "))
        lines.append(("fg:ansibrightblack", "type "))
        lines.append(("", "filter   "))
        lines.append(("fg:ansigreen", "Enter "))
        lines.append(("", "adopt   "))
        lines.append(("fg:ansiyellow", "Esc "))
        lines.append(("", "cancel\n"))
        return lines

    async def run_async(self) -> Optional[str]:
        control = FormattedTextControl(lambda: self._render())
        kb = KeyBindings()

        def refresh(event):
            control.text = self._render()
            event.app.invalidate()

        @kb.add("up")
        @kb.add("c-p")
        def _(event):
            self.selected_index -= 1
            self._clamp()
            refresh(event)

        @kb.add("down")
        @kb.add("c-n")
        def _(event):
            self.selected_index += 1
            self._clamp()
            refresh(event)

        @kb.add("backspace")
        def _(event):
            if self.filter_text:
                self.filter_text = self.filter_text[:-1]
                self._clamp()
                refresh(event)

        @kb.add("c-u")
        def _(event):
            self.filter_text = ""
            self._clamp()
            refresh(event)

        @kb.add("<any>")
        def _(event):
            if event.data and event.data.isprintable():
                self.filter_text += event.data
                self.selected_index = 0
                refresh(event)

        @kb.add("enter")
        def _(event):
            chosen = self._selected_name()
            if chosen:
                self.result = chosen
                event.app.exit()

        @kb.add("escape")
        @kb.add("c-c")
        def _(event):
            self.result = None
            event.app.exit()

        sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H")  # enter alt buffer
        sys.stdout.flush()
        try:
            app = Application(
                layout=Layout(Window(content=control, wrap_lines=True)),
                key_bindings=kb,
                full_screen=False,
            )
            await app.run_async()
        finally:
            sys.stdout.write("\x1b[?1049l")  # leave alt buffer
            sys.stdout.flush()
        return self.result


async def interactive_pet_picker() -> Optional[str]:
    """Run the adoption picker, returning the chosen species (or ``None``)."""
    from code_puppy.tools.command_runner import set_awaiting_user_input

    set_awaiting_user_input(True)
    try:
        return await PetPickerMenu().run_async()
    finally:
        set_awaiting_user_input(False)
