"""Learned token-per-character ratios for accurate token estimation.

When the API reports real prompt_tokens we can compute the actual
chars-per-token ratio for that model and store it keyed by the bare
model name (the part after ``:``).  Future ``count_tokens`` calls use the
stored ratio for that model, falling back to a hardcoded default.

The default (2.5) matches the classic char/token heuristic used across
most models.  Real tokenizers vary (GPT-4 ~3.5, Claude ~2.8), but 2.5
provides a reasonable middle ground.  The max clamp (3.5) prevents
absurdly high ratios from inflating token estimates.

Storage lives at ``~/.code_puppy/token_ratios.json``, overridable via
the env var ``CODE_PUPPY_TOKEN_RATIOS_PATH``.
"""

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default chars-per-token ratio when nothing has been learned yet.
# 2.5 is the classic heuristic — a reasonable baseline that leans slightly
# toward overestimating tokens (safer for compaction decisions).
_DEFAULT_RATIO = 2.5

# Bounds for chars-per-token ratios.  Real tokenizers produce roughly
# 2–3.5 chars/token.  Values below 1.5 imply absurdly many tokens per
# character (a single character = multiple tokens).  Values above 3.5
# would produce dangerously low token estimates, risking context overflow.
# We clamp to [1.5, 3.5] so that a poison value (e.g. 95.0 from a
# corrupted file) cannot silently collapse token estimates to near-zero.
_MIN_RATIO = 1.5
_MAX_RATIO = 3.5

# ---------------------------------------------------------------------------
# In-memory cache — populated lazily by ``_ensure_ratios_loaded()``.
# ---------------------------------------------------------------------------

_LEARNED_RATIOS: dict[str, float] = {}
_ratios_loaded: bool = False
_ratios_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Path to the learned-ratios store.
# ---------------------------------------------------------------------------

_TOKEN_RATIOS_PATH: Path = Path(
    os.path.expanduser(
        os.environ.get(
            "CODE_PUPPY_TOKEN_RATIOS_PATH",
            str(Path.home() / ".code_puppy" / "token_ratios.json"),
        )
    )
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_ratios_loaded() -> None:
    """Populate ``_LEARNED_RATIOS`` from disk on first call (idempotent)."""
    global _ratios_loaded
    with _ratios_lock:
        if _ratios_loaded:
            return
        _LEARNED_RATIOS.clear()
        _LEARNED_RATIOS.update(_load_learned_ratios())
        _ratios_loaded = True


def _load_learned_ratios() -> dict[str, float]:
    """Load learned token ratios from the on-disk JSON file.

    Returns an empty dict when the file doesn't exist or is corrupt —
    callers fall back to ``_DEFAULT_RATIO``.

    Each loaded value is clamped to ``[_MIN_RATIO, _MAX_RATIO]`` so that
    poisoned or corrupted values cannot cause token-count collapse.
    """
    try:
        if _TOKEN_RATIOS_PATH.is_file():
            data = json.loads(_TOKEN_RATIOS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                clamped: dict[str, float] = {}
                for k, v in data.items():
                    if isinstance(v, (int, float)) and v > 0:
                        # Lowercase keys for case-insensitive matching.
                        # Old files may have mixed-case keys.
                        clamped[k.lower()] = max(_MIN_RATIO, min(_MAX_RATIO, float(v)))
                return clamped
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {}


def _save_learned_ratios(ratios: dict[str, float]) -> None:
    """Persist learned token ratios to disk atomically (best-effort, never raises)."""
    try:
        parent = _TOKEN_RATIOS_PATH.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                json.dump(ratios, tmp, indent=2)
            os.replace(tmp_name, str(_TOKEN_RATIOS_PATH))
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError:
        pass  # Silently ignore write failures (permissions, disk full, etc.)


def _record_token_ratio(model: str, char_count: int, token_count: int) -> None:
    """Record an observed chars-per-token ratio for *model*.

    Called after a successful API response where we know both the input
    character count and the actual prompt token count.  Stores a running
    average keyed by the bare model name (the part after ``:``) so that
    the same model accessed through different providers shares the estimate.

    The running average uses a 70/30 blend: 70% old, 30% new.  This lets
    the estimate adapt to the real tokenizer without swinging wildly on
    every call.
    """
    if char_count <= 0 or token_count <= 0:
        return

    # Extract bare model name: "wafer:glm5.1" → "glm5.1",
    # "anthropic:Claude-Sonnet" → "claude-sonnet" (lowercased)
    model_name = model.split(":", 1)[1] if ":" in model else model
    model_name = model_name.lower()

    _ensure_ratios_loaded()

    new_ratio = char_count / token_count
    new_ratio = max(_MIN_RATIO, min(_MAX_RATIO, new_ratio))

    with _ratios_lock:
        old = _LEARNED_RATIOS.get(model_name)
        if old is not None:
            blended = 0.7 * old + 0.3 * new_ratio
        else:
            blended = new_ratio
        _LEARNED_RATIOS[model_name] = round(blended, 4)
        _save_learned_ratios(_LEARNED_RATIOS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def count_tokens(text: str, model: str | None = None) -> int:
    """Estimate token count using a character-based heuristic.

    If we have a *learned* chars-per-token ratio for *model*, use it.
    Otherwise fall back to ``_DEFAULT_RATIO`` (2.5).

    Args:
        text: The text content whose token count we need.
        model: Optional model identifier string (e.g.
               ``"anthropic:claude-sonnet"``).  The provider prefix is
               stripped before lookup, so ``"wafer:glm5.1"`` and bare
               ``"glm5.1"`` resolve to the same key.

    Returns:
        Estimated token count (always >= 1 for non-empty input).
    """
    _ensure_ratios_loaded()

    if not text:
        return 0

    # Look up by bare model name (strip provider prefix, lowercase).
    model_name = None
    if model:
        model_name = model.split(":", 1)[1] if ":" in model else model
        model_name = model_name.lower()

    raw_ratio = _LEARNED_RATIOS.get(model_name or "", _DEFAULT_RATIO)
    ratio = max(_MIN_RATIO, min(_MAX_RATIO, raw_ratio))

    result = round(len(text) / ratio)
    return result if result > 0 else 1


def get_ratio_for_model(model: str) -> float:
    """Return the current chars/token ratio for *model* (or default)."""
    _ensure_ratios_loaded()
    model_name = model.split(":", 1)[1] if ":" in model else model
    model_name = model_name.lower()
    raw = _LEARNED_RATIOS.get(model_name, _DEFAULT_RATIO)
    return max(_MIN_RATIO, min(_MAX_RATIO, raw))


def list_known_ratios() -> dict[str, float]:
    """Return a copy of all learned ratios (for debugging/stats)."""
    _ensure_ratios_loaded()
    with _ratios_lock:
        return dict(_LEARNED_RATIOS)


# ---------------------------------------------------------------------------
# Storage path override (for tests)
# ---------------------------------------------------------------------------


def set_ratios_path(path: str | Path) -> None:
    """Override the token ratios file path (mostly for testing)."""
    global _TOKEN_RATIOS_PATH, _ratios_loaded, _LEARNED_RATIOS
    _TOKEN_RATIOS_PATH = Path(path)
    with _ratios_lock:
        _LEARNED_RATIOS.clear()
        _ratios_loaded = False
