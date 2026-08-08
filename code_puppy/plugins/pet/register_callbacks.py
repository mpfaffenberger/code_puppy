"""Desktop pet plugin -- wires everything into Code Puppy via callbacks.

Two integration points, both plugin-friendly (no core edits):

* ``startup`` -- monkey-patches the ``PromptSession`` used by the main input
  prompt so an adopted pet rides along as an animated ``bottom_toolbar``
  (right-aligned -> bottom-right). Mirrors the ``prompt_newline`` plugin.
* ``custom_command`` / ``custom_command_help`` -- exposes ``/pet`` for adopt /
  dismiss / pick / rename / quip / grid.

Everything is local string-rendering: zero LLM tokens, fails graceful.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.plugins.pet import config as pet_config
from code_puppy.plugins.pet.species import DOG_SPECIES, list_species

_COMMAND = "pet"
_PATCH_ATTR = "_pet_toolbar_original_session"

_HELP = """\
/pet on            Open the adoption picker, then summon your dog (prompt corner)
/pet off           Send the dog back to the yard (hide it)
/pet pick          Re-open the picker to swap breeds
/pet <breed>       Adopt a specific breed directly (e.g. /pet shiba)
/pet rename <name> Give your pup a new name
/pet quip          Reroll your pup's quip
/pet list | grid   Show the rarity-colored list of all 19 breeds
/pet               Show status
"""


# ── messaging shims (lazy imports keep plugin load cheap) ──────────────────
def _emit_info(msg) -> None:
    from code_puppy.messaging import emit_info

    emit_info(msg)


def _emit_success(msg) -> None:
    from code_puppy.messaging import emit_success

    emit_success(msg)


def _emit_warning(msg) -> None:
    from code_puppy.messaging import emit_warning

    emit_warning(msg)


# ── startup: install the bottom-toolbar patch ──────────────────────────────
def _install_toolbar_patch() -> None:
    """Subclass the prompt's ``PromptSession`` to inject the pet toolbar.

    Idempotent. Only the main input prompt's sessions are affected, and only
    when a pet is actually adopted -- otherwise behaviour is untouched.
    """
    from code_puppy.command_line import prompt_toolkit_completion as ptc

    if getattr(ptc, _PATCH_ATTR, None) is not None:
        return

    original_session = ptc.PromptSession
    setattr(ptc, _PATCH_ATTR, original_session)

    from code_puppy.plugins.pet.toolbar import (
        PET_STYLE,
        REFRESH_INTERVAL,
        render_toolbar,
    )

    class PetPromptSession(original_session):  # type: ignore[misc, valid-type]
        async def prompt_async(self, *args, **kwargs):
            try:
                if pet_config.is_enabled() and "bottom_toolbar" not in kwargs:
                    kwargs["bottom_toolbar"] = render_toolbar
                    kwargs["refresh_interval"] = REFRESH_INTERVAL
                    from prompt_toolkit.styles import Style, merge_styles

                    pet_style = Style.from_dict(PET_STYLE)
                    base = kwargs.get("style")
                    kwargs["style"] = (
                        merge_styles([base, pet_style]) if base else pet_style
                    )
            except Exception:
                pass  # never let the pet break the prompt
            return await super().prompt_async(*args, **kwargs)

    ptc.PromptSession = PetPromptSession


def _on_startup() -> None:
    try:
        _install_toolbar_patch()
    except Exception as exc:
        _emit_warning(f"pet: failed to install toolbar patch -- {exc}")


# ── /pet command ───────────────────────────────────────────────────────────
def _run_picker():
    import asyncio
    import concurrent.futures

    from code_puppy.plugins.pet.picker import interactive_pet_picker

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(lambda: asyncio.run(interactive_pet_picker()))
        return future.result(timeout=300)


def _adopt(species: str) -> bool:
    if species not in DOG_SPECIES:
        species = "mutt"
    pet_config.set_species(species)
    pet_config.set_enabled(True)
    dog = DOG_SPECIES[species]
    _emit_success(
        f"Adopted {pet_config.get_name()} the {species} "
        f"({dog.rarity} {dog.stars})! They'll wag in the corner of your prompt."
    )
    return True


def _custom_help() -> List[Tuple[str, str]]:
    return [(_COMMAND, "Adopt a desktop dog that lives in your prompt corner")]


def _handle_pet_command(command: str, name: str) -> Optional[bool]:
    if name != _COMMAND:
        return None

    tokens = command.split()

    if len(tokens) == 1:
        if pet_config.is_enabled():
            _reroll_quip()
            _emit_info(
                f"{pet_config.get_name()} the {pet_config.get_species()} is on duty "
                "(prompt corner). Try /pet quip, /pet off, or /pet pick."
            )
        else:
            _emit_info("No pet adopted yet. Run /pet on to pick one!\n" + _HELP)
        return True

    sub = tokens[1].lower()

    if sub == "off":
        if not pet_config.is_enabled():
            _emit_info("You don't have a pet out right now.")
            return True
        who = pet_config.get_name()
        pet_config.set_enabled(False)
        _emit_info(f"{who} trots off for a nap. Use /pet on to bring them back.")
        return True

    if sub in ("on", "pick", "adopt"):
        try:
            chosen = _run_picker()
        except Exception as exc:
            _emit_warning(f"Picker failed ({exc}). Try '/pet <breed>' directly.")
            _emit_info("Breeds: " + ", ".join(list_species()))
            return True
        if not chosen:
            _emit_warning("Adoption cancelled. The shelter understands.")
            return True
        return _adopt(chosen)

    if sub in ("list", "grid", "breeds"):
        from code_puppy.plugins.pet.grid import render_grid

        _emit_info(render_grid())
        return True

    if sub == "rename":
        if len(tokens) < 3:
            _emit_warning("Usage: /pet rename <name>")
            return True
        new_name = " ".join(tokens[2:])[:20]
        pet_config.set_name(new_name)
        _emit_success(f"Your pet shall henceforth be known as {new_name}.")
        return True

    if sub == "quip":
        if not pet_config.is_enabled():
            _emit_info("Adopt a pet first with /pet on.")
            return True
        _emit_info(f"{pet_config.get_name()} says: \u201c{_reroll_quip()}\u201d")
        return True

    if sub in DOG_SPECIES:
        return _adopt(sub)

    _emit_warning(
        f"Unknown pet command: '{sub}'. Try /pet on, /pet off, or a breed name.\n"
        + _HELP
    )
    return True


def _reroll_quip() -> str:
    from code_puppy.plugins.pet.toolbar import current_quip, reroll_quip

    reroll_quip()
    return current_quip()


register_callback("startup", _on_startup)
register_callback("custom_command", _handle_pet_command)
register_callback("custom_command_help", _custom_help)


__all__ = [
    "_adopt",
    "_custom_help",
    "_handle_pet_command",
    "_install_toolbar_patch",
    "_on_startup",
    "_run_picker",
]
