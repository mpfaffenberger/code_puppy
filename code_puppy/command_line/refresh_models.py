"""Backfill ``extra_models.json`` limits from the models.dev catalog.

``/add_model`` stamps ``max_output_tokens`` (and ``context_length``) on new
entries, but anything added before that -- or written by hand -- carries no
output cap. Model resolution itself consults models.dev before falling back to
the 15% heuristic, so this command is no longer load-bearing for correctness --
it just writes the limits down so they survive offline. ``/refresh_models``
re-reads models.dev and patches those limits in place.

Rules -- the guiding one being *never blast anything models.dev can't vouch
for*:

* Entries with no models.dev match (or an ambiguous one) are not touched.
  Every other key on every entry is preserved verbatim.
* Exact ``/add_model`` key match: models.dev is authoritative, so
  ``max_output_tokens`` is **overwritten** (it's an auto-populated default;
  the user's knob is the per-model override in ``/model_settings``).
* Name-only match (hand-written entry): we're guessing, so limits are only
  **filled when missing**, never overwritten.
* ``context_length`` is only ever filled when missing -- people hand-tune it.
* A name match only counts when every provider offering that model id
  agrees on the output cap; otherwise the entry is reported as ambiguous.
* The file is not rewritten at all when nothing changed.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from code_puppy import atomic_json
from code_puppy.config import EXTRA_MODELS_FILE, MAX_OUTPUT_TOKENS_SETTING
from code_puppy.models_dev_parser import (
    LimitMatchKind,
    ModelLimits,
    ModelsDevRegistry,
    index_limits,
    match_limits,
)


@dataclass
class RefreshReport:
    """What ``refresh_extra_models`` did, for the command to narrate."""

    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    unmatched: List[str] = field(default_factory=list)
    ambiguous: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Match:
    limits: ModelLimits
    exact: bool  # True = /add_model key match, False = name-only guess


class _NothingToWrite(Exception):
    """Abort the locked transaction without rewriting the file."""


def _resolve_match(
    key: str,
    entry: dict,
    by_key: Dict[str, ModelLimits],
    by_name: Dict[str, List[ModelLimits]],
    report: RefreshReport,
) -> Optional[_Match]:
    """Find the models.dev match for one entry, recording misses on ``report``."""
    match = match_limits(by_key, by_name, key, str(entry.get("name", "")))
    if match.limits is None:
        if match.kind is LimitMatchKind.AMBIGUOUS:
            report.ambiguous.append(key)
        else:
            report.unmatched.append(key)
        return None
    return _Match(match.limits, exact=match.kind is LimitMatchKind.EXACT)


def _apply_match(entry: dict, match: _Match) -> bool:
    """Patch ``entry`` in place; True when anything actually changed."""
    limits = match.limits
    changed = False
    if limits.max_output > 0:
        current = entry.get(MAX_OUTPUT_TOKENS_SETTING)
        may_write = current is None or match.exact
        if may_write and current != limits.max_output:
            entry[MAX_OUTPUT_TOKENS_SETTING] = limits.max_output
            changed = True
    if limits.context_length > 0 and "context_length" not in entry:
        entry["context_length"] = limits.context_length
        changed = True
    return changed


def refresh_extra_models(
    registry: Optional[ModelsDevRegistry] = None,
    path: str = EXTRA_MODELS_FILE,
) -> RefreshReport:
    """Backfill output/context limits in ``extra_models.json`` from models.dev.

    Raises whatever ``atomic_json.mutate_json`` raises on a corrupt file;
    the command layer turns that into a user-facing error.
    """
    by_key, by_name = index_limits((registry or ModelsDevRegistry()).get_models())
    report = RefreshReport()

    def _mutate(current):
        if not isinstance(current, dict):
            raise ValueError("extra_models.json must be a dictionary")
        for key, entry in current.items():
            if not isinstance(entry, dict):
                continue
            match = _resolve_match(key, entry, by_key, by_name, report)
            if match is None:
                continue
            bucket = report.updated if _apply_match(entry, match) else report.unchanged
            bucket.append(key)
        if not report.updated:
            raise _NothingToWrite()
        return current

    try:
        atomic_json.mutate_json(path, _mutate, default={})
    except _NothingToWrite:
        pass
    return report
