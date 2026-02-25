"""Loading messages for spinner and status display.

Provides a shuffled deck of fun/silly loading messages that rotate
during spinner cycles. Messages are drawn from several categories
and shuffled so no message repeats until the entire deck is exhausted.

Plugins can register additional message categories via
``register_messages(category, messages)``.
"""

import random
from typing import Dict, List

# ---------------------------------------------------------------------------
# 🐶  Puppy / Dog Themed
# ---------------------------------------------------------------------------
_PUPPY_SPINNER: List[str] = [
    "sniffing around...",
    "wagging tail...",
    "pawsing for a moment...",
    "chasing tail...",
    "digging up results...",
    "barking at the data...",
    "rolling over...",
    "panting with excitement...",
    "chewing on it...",
    "prancing along...",
    "howling at the code...",
    "snuggling up to the task...",
    "bounding through data...",
    "fetching results...",
    "playing fetch with ideas...",
    "doing a happy dance...",
    "perking up ears...",
    "tilting head curiously...",
    "burying a bone of knowledge...",
    "shaking off the cobwebs...",
    "begging for treats...",
    "chasing the mailman...",
    "guarding the codebase...",
    "herding the functions...",
    "learning new tricks...",
    "napping on the keyboard...",
    "pawing at the screen...",
    "sniffing out bugs...",
    "doing zoomies...",
    "gnawing on a problem...",
    "licking the screen...",
    "being a good boy...",
    "drooling over clean code...",
    "marking territory...",
    "digging a hole in the stack...",
    "catching a frisbee...",
    "whimpering at legacy code...",
    "yipping with excitement...",
    "rolling in the data...",
    "scratching behind ear...",
    "snoozing then coding...",
    "burying the lede...",
    "unleashing the code...",
]

# ---------------------------------------------------------------------------
# 💻  Dev / Coding
# ---------------------------------------------------------------------------
_DEV_SPINNER: List[str] = [
    "refactoring reality...",
    "compiling thoughts...",
    "parsing the universe...",
    "rebasing on reality...",
    "merging timelines...",
    "deploying neurons...",
    "linting the cosmos...",
    "cherry-picking ideas...",
    "stashing thoughts...",
    "hashing it out...",
    "vibe-coding...",
]

# ---------------------------------------------------------------------------
# 🎲  Random Fun / Silly
# ---------------------------------------------------------------------------
_FUN_SPINNER: List[str] = [
    "consulting the oracle...",
    "asking the rubber duck...",
    "reading tea leaves...",
    "shaking the magic 8-ball...",
    "channeling the force...",
    "summoning the kraken...",
    "calibrating the vibe...",
    "vibing...",
    "manifesting...",
    "reticulating splines...",
    "reversing the polarity...",
    "rerouting the dilithium...",
    "consulting the ancient texts...",
    "interrogating the void...",
    "pondering the orb...",
    "adjusting the timeline...",
    "wrangling the chaos...",
    "herding cats...",
    "spinning up hamster wheels...",
    "brewing coffee...",
    "microwaving leftovers...",
    "ordering pizza...",
    "updating the spreadsheet...",
    "googling the answer...",
    "Stack Overflowing...",
    "reading the docs...",
    "RTFM-ing...",
    "blaming the intern...",
    "turning it off and on...",
    "wiggling the cables...",
    "downloading more RAM...",
    "feeding the hamsters...",
    "dusting off the cobwebs...",
    "polishing the pixels...",
    "aligning the chakras...",
    "balancing the universe...",
    "crunching the numbers...",
    "doing the math...",
    "phoning a friend...",
    "asking the audience...",
    "inserting coin...",
    "doing your work for you...",
]

# ---------------------------------------------------------------------------
# ⚡  Action Verbs (short & punchy)
# ---------------------------------------------------------------------------
_ACTION_SPINNER: List[str] = [
    "deliberating...",
    "contemplating...",
    "hypothesizing...",
    "brainstorming...",
    "strategizing...",
    "orchestrating...",
    "crafting...",
    "sculpting...",
    "weaving...",
    "assembling...",
    "constructing...",
    "investigating...",
    "researching...",
    "exploring...",
    "discovering...",
    "transforming...",
    "transmuting...",
    "conjuring...",
    "invoking...",
    "materializing...",
    "crystallizing...",
    "distilling...",
    "curating...",
    "polishing...",
    "refining...",
]


# ===========================================================================
#  STANDALONE MESSAGES (no prefix — used only in the status display)
# ===========================================================================
_STANDALONE_MESSAGES: List[str] = [
    # 🐶 Puppy
    "Puppy pondering...",
    "Nose to the ground...",
    "Tail-wagging intensifies...",
    "Sitting. Staying. Coding...",
    "Belly rub loading...",
    "Paws on keyboard...",
    "Puppy eyes activated...",
    # 🎲 Fun
    "Loading loading screen...",
    "It's not a bug...",
    "Works on my machine...",
    "Have you tried unplugging?",
    "Percussive maintenance...",
    "Deleting System32... jk...",
    "50/50 lifeline used...",
    "Plot twist incoming...",
    "Stay tuned...",
    "Warming up the flux capacitor...",
    # 🤓 Nerdy / Pop culture
    "sudo make me a sandwich...",
    "There is no spoon...",
    "Hello, World!...",
    "I'm sorry Dave...",
    "To infinity and beyond...",
    "May the source be with you...",
    "Use the --force, Luke...",
    "Live long and prosper...",
    "Beam me up, Scotty...",
    "Winter is compiling...",
    "One does not simply code...",
    "My precious... data...",
    "I am Groot (processing)...",
    "Avengers, assemble code...",
    "This is the way...",
    "I have spoken...",
    "Bazinga!...",
    "Allons-y!...",
    "Fantastic!...",
    "Geronimo!...",
    "Elementary, my dear...",
    "The cake is a lie...",
    "Do a barrel roll...",
    "All your base are belong...",
    "It's dangerous to go alone...",
]

# ===========================================================================
#  Plugin Registry
# ===========================================================================
_plugin_categories: Dict[str, List[str]] = {}
_plugins_initialized: bool = False


def _ensure_plugins_loaded() -> None:
    """Fire the register_loading_messages callback once.

    This is called lazily the first time messages are requested,
    giving plugins time to register their callbacks at import.
    """
    global _plugins_initialized
    if _plugins_initialized:
        return
    _plugins_initialized = True

    from code_puppy.callbacks import on_register_loading_messages

    on_register_loading_messages()


def register_messages(category: str, messages: List[str]) -> None:
    """Register additional loading messages from a plugin.

    Parameters
    ----------
    category:
        A unique category name (e.g. ``"walmart"``).  If the category
        already exists the new messages are **appended**.
    messages:
        List of message strings.  For spinner messages these will be
        prefixed with ``"<PuppyName> is "`` automatically — keep them
        lowercase and gerund-style (e.g. ``"rolling back prices..."``).
    """
    if category in _plugin_categories:
        _plugin_categories[category].extend(messages)
    else:
        _plugin_categories[category] = list(messages)


def unregister_messages(category: str) -> None:
    """Remove a previously registered message category."""
    _plugin_categories.pop(category, None)


# ===========================================================================
#  Public API
# ===========================================================================


def _all_spinner_messages() -> List[str]:
    """Combine built-in + plugin spinner messages (not standalone)."""
    _ensure_plugins_loaded()
    combined = _PUPPY_SPINNER + _DEV_SPINNER + _FUN_SPINNER + _ACTION_SPINNER
    for msgs in _plugin_categories.values():
        combined = combined + msgs
    return combined


def get_spinner_messages() -> List[str]:
    """Return a shuffled copy of all spinner messages.

    Each call produces a fresh shuffle so that a spinner can draw
    through the entire deck without repeats.
    """
    msgs = _all_spinner_messages()
    random.shuffle(msgs)
    return msgs


def get_all_messages() -> List[str]:
    """Return all messages (spinner + standalone) for status display."""
    return _all_spinner_messages() + list(_STANDALONE_MESSAGES)


def get_messages_by_category() -> Dict[str, List[str]]:
    """Return messages organized by category (useful for testing)."""
    _ensure_plugins_loaded()
    result = {
        "puppy": list(_PUPPY_SPINNER),
        "dev": list(_DEV_SPINNER),
        "fun": list(_FUN_SPINNER),
        "action": list(_ACTION_SPINNER),
        "standalone": list(_STANDALONE_MESSAGES),
    }
    for cat, msgs in _plugin_categories.items():
        result[cat] = list(msgs)
    return result
