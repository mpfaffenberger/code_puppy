"""Monkey patches for third-party libraries.

Historically pydantic-ai focused, this module now collects all runtime
monkey patches code-puppy applies to its dependencies.  Each patch is
idempotent and NEVER raises, but failures are not silent:

- A missing OPTIONAL third-party lib (json_repair, wcwidth, prompt_toolkit,
  termflow) is genuinely fine and only logged at DEBUG level.
- Failure to locate/patch a pydantic-ai (or other patched-lib) internal —
  missing module, missing attribute, changed shape detected at apply time —
  is logged LOUDLY via ``logger.error``, because it means a security or
  correctness layer silently degraded (e.g. tool-call hooks not firing).

Logging uses the stdlib ``logging`` module, NOT ``code_puppy.messaging``:
patches apply at the very top of ``cli_runner`` before the messaging
system is up (see cli_runner.py lines 6-9).

Usage:
    from code_puppy.pydantic_patches import apply_all_patches
    apply_all_patches()
"""

import importlib.metadata
import logging
import warnings

from code_puppy.patch_support import LOUD_FAILURES as _LOUD_FAILURES
from code_puppy.patch_support import optional_lib_missing as _optional_lib_missing
from code_puppy.patch_support import patch_failed as _patch_failed
from code_puppy.tool_call_patches import (
    patch_tool_call_callbacks,
    patch_tool_call_json_repair,
)

logger = logging.getLogger(__name__)


def _get_code_puppy_version() -> str:
    """Get the current code-puppy version."""
    try:
        return importlib.metadata.version("code-puppy")
    except Exception:
        return "0.0.0-dev"


def patch_user_agent() -> bool:
    """Patch pydantic-ai's User-Agent to use Code-Puppy's version.

    pydantic-ai sets its own User-Agent ('pydantic-ai/x.x.x') via a @cache-decorated
    function. We replace it with a dynamic function that returns:
    - 'KimiCLI/0.63' for Kimi models
    - 'Code-Puppy/{version}' for all other models

    This MUST be called before any pydantic-ai models are created.
    """
    try:
        import pydantic_ai.models as pydantic_models

        if not hasattr(pydantic_models, "get_user_agent"):
            raise AttributeError("pydantic_ai.models.get_user_agent not found")

        version = _get_code_puppy_version()

        # Clear cache if already called
        if hasattr(pydantic_models.get_user_agent, "cache_clear"):
            pydantic_models.get_user_agent.cache_clear()

        def _get_dynamic_user_agent() -> str:
            """Return User-Agent based on current model selection."""
            try:
                from code_puppy.config import get_global_model_name

                model_name = get_global_model_name()
                if model_name and "kimi" in model_name.lower():
                    return "KimiCLI/0.63"
            except Exception:
                pass
            return f"Code-Puppy/{version}"

        pydantic_models.get_user_agent = _get_dynamic_user_agent
        assert pydantic_models.get_user_agent is _get_dynamic_user_agent
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_user_agent",
            exc,
            "the Code-Puppy User-Agent is DISABLED; requests use pydantic-ai's default.",
        )


def patch_message_history_cleaning() -> bool:
    """Disable overly strict message history cleaning in pydantic-ai."""
    try:
        from pydantic_ai import _agent_graph

        if not hasattr(_agent_graph, "_clean_message_history"):
            raise AttributeError(
                "pydantic_ai._agent_graph._clean_message_history not found"
            )

        # v2 signature: _clean_message_history(messages, *, repair_last_response=False)
        _identity = lambda messages, **_kwargs: messages  # noqa: E731
        _agent_graph._clean_message_history = _identity
        assert _agent_graph._clean_message_history is _identity
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_message_history_cleaning",
            exc,
            "strict history cleaning is ACTIVE and may drop valid messages.",
        )


def patch_prompt_toolkit_emoji_width() -> bool:
    """Patch prompt_toolkit's character width calculation for emojis.

    Modern terminals render most emojis as 2 cells wide, but wcwidth often
    returns 1 for many emoji codepoints. This causes cursor misalignment.

    This patch:
    1. Returns 0 for variation selectors (zero-width modifiers)
    2. Returns 2 for emoji codepoints (terminals render them wide)
    3. Falls back to wcwidth for non-emoji characters
    """
    try:
        import wcwidth
        from prompt_toolkit import utils as pt_utils
    except ImportError as exc:
        return _optional_lib_missing("patch_prompt_toolkit_emoji_width", exc)

    try:
        _original_get_cwidth = pt_utils.get_cwidth

        def _patched_get_cwidth(char: str) -> int:
            """Get character width with better emoji support."""
            code = ord(char)

            # Variation selectors are zero-width
            if 0xFE00 <= code <= 0xFE0F:  # VS1-VS16
                return 0

            # Emoji codepoints - terminals render these as 2 cells wide
            # even when wcwidth says 1
            if (
                0x1F300 <= code <= 0x1F9FF  # Misc Symbols/Pictographs, Emoticons
                or 0x1F600 <= code <= 0x1F64F  # Emoticons
                or 0x1F680 <= code <= 0x1F6FF  # Transport/Map symbols
                or 0x1FA00 <= code <= 0x1FAFF  # Symbols/Pictographs Extended-A
                or 0x2600 <= code <= 0x26FF  # Misc Symbols (☀️, ⚡, etc)
                or 0x2700 <= code <= 0x27BF  # Dingbats (✂️, ✈️, etc)
                or 0x1F1E0 <= code <= 0x1F1FF  # Regional indicators (flags)
            ):
                return 2

            # Use wcwidth for non-emoji
            w = wcwidth.wcwidth(char)
            if w >= 0:
                return w

            return _original_get_cwidth(char)

        pt_utils.get_cwidth = _patched_get_cwidth
        assert pt_utils.get_cwidth is _patched_get_cwidth
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_prompt_toolkit_emoji_width",
            exc,
            "emoji cursor alignment fixes are DISABLED.",
            target="prompt_toolkit",
        )


def patch_termflow_clipboard() -> bool:
    """Disable termflow's OSC 52 clipboard hijacking globally.

    termflow's ``RenderFeatures.clipboard`` defaults to ``True``.  When a
    code block finishes rendering, the renderer emits an OSC 52 escape
    sequence (``\x1b]52;c;<base64>\x07``) that modern terminals interpret
    as a silent clipboard-write command — clobbering whatever the user had.

    PR #335 added explicit ``RenderFeatures(clipboard=False)`` at the two
    known instantiation sites, but that's whack-a-mole: any future code path
    (or a new termflow version with changed defaults) reintroduces the bug.

    This patch kills the behaviour at the source by replacing
    ``Renderer._copy_to_clipboard`` with a no-op, so it does not matter
    whether any caller remembers to disable the feature flag.
    """
    try:
        from termflow.render.renderer import Renderer
    except ImportError as exc:
        return _optional_lib_missing("patch_termflow_clipboard", exc)

    try:
        if not hasattr(Renderer, "_copy_to_clipboard"):
            raise AttributeError("termflow Renderer._copy_to_clipboard not found")
        Renderer._copy_to_clipboard = lambda self, text: None  # type: ignore[method-assign]
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_termflow_clipboard",
            exc,
            "OSC 52 clipboard hijacking is ACTIVE; code blocks may silently "
            "overwrite the user's clipboard.",
            target="termflow",
        )


def _no_pad_render_code_line(_line, highlighted, width, margin, style, pretty_pad=True):
    """Drop-in for ``render_code_line`` minus the ``' ' * padding`` suffix."""
    return f"{margin}{highlighted}"


def patch_termflow_code_padding() -> bool:
    """Strip trailing-space padding from termflow code lines (#505).

    termflow's ``render_code_line`` right-pads to render width, but
    termflow doesn't color code backgrounds -- so the padding is pure
    invisible filler that corrupts copy/paste. Must patch both
    ``termflow.render.code`` (the definition) AND
    ``termflow.render.renderer`` (did ``from … import render_code_line``,
    so it holds a stale reference).
    """
    try:
        import termflow.render.code as _termflow_code
        import termflow.render.renderer as _termflow_renderer
    except ImportError as exc:
        return _optional_lib_missing("patch_termflow_code_padding", exc)

    try:
        if not hasattr(_termflow_code, "render_code_line") or not hasattr(
            _termflow_renderer, "render_code_line"
        ):
            raise AttributeError("termflow render_code_line not found")
        _termflow_code.render_code_line = _no_pad_render_code_line
        _termflow_renderer.render_code_line = _no_pad_render_code_line
        return True
    except Exception as exc:
        return _patch_failed(
            "patch_termflow_code_padding",
            exc,
            "code lines keep invisible trailing-space padding (copy/paste corruption).",
            target="termflow",
        )


def patch_silence_anthropic_sampling_warnings() -> bool:
    """Silence pydantic-ai's unsupported-sampling-parameter UserWarning.

    Some Claude models (e.g. Fable 5) reject sampling params like
    ``temperature``; pydantic-ai already drops them before sending, then
    warns on every single request:

        Sampling parameters ['temperature'] are not supported by
        'claude-fable-5'. These settings will be ignored.

    We avoid sending those params in the first place (see
    ``make_model_settings``), so any residual warning is pure console noise
    in the TUI. The filter is scoped to this exact message shape — NOT a
    blanket UserWarning ignore. Module-based scoping is intentionally
    omitted: warnings' module matching keys off the stacklevel-adjusted
    frame and is unreliable here.
    """
    warnings.filterwarnings(
        "ignore",
        message=r"Sampling parameters .* are not supported by .*",
        category=UserWarning,
    )
    return True


_ALL_PATCHES = (
    patch_silence_anthropic_sampling_warnings,
    patch_user_agent,
    patch_message_history_cleaning,
    patch_tool_call_json_repair,
    patch_tool_call_callbacks,
    patch_prompt_toolkit_emoji_width,
    patch_termflow_clipboard,
    patch_termflow_code_padding,
)


def apply_all_patches() -> dict[str, bool]:
    """Apply all monkey patches.

    Call this at the very top of main.py, before any other imports.

    Returns a mapping of patch name -> whether it applied. Never raises:
    failures are logged (loudly for real breakage, quietly for missing
    optional dependencies) and reflected as ``False`` in the result.
    """
    _LOUD_FAILURES.clear()
    results: dict[str, bool] = {}
    for patch in _ALL_PATCHES:
        try:
            results[patch.__name__] = bool(patch())
        except Exception as exc:  # pragma: no cover - patches must not raise
            _LOUD_FAILURES.append(patch.__name__)
            logger.error(
                "pydantic_patches: %s raised unexpectedly: %r", patch.__name__, exc
            )
            results[patch.__name__] = False
    if _LOUD_FAILURES:
        logger.error(
            "pydantic_patches: %d patch(es) FAILED to apply: %s — "
            "behavior may be degraded.",
            len(_LOUD_FAILURES),
            ", ".join(_LOUD_FAILURES),
        )
    return results
