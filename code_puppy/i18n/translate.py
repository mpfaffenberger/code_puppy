"""The translation runtime: active-locale state, ``t()``, and ``ngettext()``.

This is the module call sites actually touch. Everything else in the package
feeds into the :class:`Translator` singleton exposed here.

Design notes:

* A **missing key never raises.** It falls through the locale chain, then to
  the key itself (so you always get *something* renderable, and the raw key
  is an obvious "this string was never translated" signal on screen).
* **Interpolation is safe.** We use :meth:`str.format_map` with a forgiving
  mapping, so a missing ``{param}`` leaves the placeholder intact instead of
  blowing up mid-render.
* ``lazy()`` defers resolution to ``str()`` time, so a string emitted before
  the user switches locale still renders in the *new* locale.
"""

from __future__ import annotations

import re
import threading
from typing import Any, Optional

from . import catalog
from .locale import DEFAULT_LOCALE, detect_locale, normalize_locale
from .plurals import plural_category
from .pseudo import is_pseudo_locale, pseudolocalize

# Safe interpolation grammar. We intentionally do NOT use str.format/format_map
# on catalog strings: catalogs are untrusted input (add_catalog_dir is the
# plugin/community/private-fork seam), and str.format honors attribute/index
# access in the *template* (e.g. {x.__class__.__globals__}) plus format specs
# (e.g. {n:99999999} memory bombs). This grammar matches ONLY {{ / }} escapes
# and {identifier} fields -- no dots, no indexing, no format specs, no
# conversions -- so a malicious or careless translation can neither reach
# object internals nor blow up rendering.
_FIELD_RE = re.compile(r"\{\{|\}\}|\{(\w+)\}")


def _interpolate(text: str, params: dict) -> str:
    """Substitute {name} fields from params, safely and forgivingly.

    - ``{{`` / ``}}`` render as literal braces.
    - A known ``{name}`` becomes ``str(params[name])``.
    - An unknown ``{name}`` is left intact (forgiving; never raises).
    - Anything that is not a bare ``{identifier}`` (``{x.y}``, ``{0}``,
      ``{n:spec}``) is left untouched as a literal -- no attribute walking,
      no format-spec DoS.
    """

    def _replace(match: "re.Match[str]") -> str:
        token = match.group(0)
        if token == "{{":
            return "{"
        if token == "}}":
            return "}"
        name = match.group(1)
        if name in params:
            return str(params[name])
        return token  # unknown field: leave placeholder intact

    return _FIELD_RE.sub(_replace, text)


class Translator:
    """Holds the active locale and resolves translation keys against it."""

    def __init__(
        self, locale: Optional[str] = None, default_locale: str = DEFAULT_LOCALE
    ) -> None:
        self._default = normalize_locale(default_locale) or DEFAULT_LOCALE
        self._lock = threading.RLock()
        self._locale = normalize_locale(locale) or self._default
        # True once the locale has been set explicitly (set_locale /
        # use_detected_locale). Lets ensure_detected() seed exactly once from
        # env+config without clobbering a later runtime override.
        self._explicit = locale is not None

    # -- locale management -------------------------------------------------
    @property
    def locale(self) -> str:
        with self._lock:
            return self._locale

    def set_locale(self, locale: str) -> str:
        """Set the active locale, returning the normalized value applied."""
        normalized = normalize_locale(locale) or self._default
        with self._lock:
            self._locale = normalized
            self._explicit = True
        return normalized

    def use_detected_locale(self, config_value: Optional[str] = None) -> str:
        """Resolve via the env/config/default chain and apply it."""
        return self.set_locale(detect_locale(config_value, self._default))

    def ensure_detected(self, config_value: Optional[str] = None) -> str:
        """Seed the locale from env+config once, if not already set explicitly.

        Idempotent: after any explicit set_locale/use_detected_locale (or a
        prior ensure_detected), this is a no-op and simply returns the active
        locale. This makes the translator the single source of truth for the
        active locale while still honoring a runtime override.
        """
        with self._lock:
            if self._explicit:
                return self._locale
        return self.use_detected_locale(config_value)

    # -- core lookup -------------------------------------------------------
    def _select_text(self, key: str, count: Optional[int]) -> str:
        entry = catalog.lookup(key, self._locale, self._default)
        if entry is None:
            # Unknown key: echo the key back so it's visible + never crashes.
            return key
        if isinstance(entry, str):
            return entry
        # Plural dict: pick the category, degrade gracefully to "other".
        category = plural_category(self._locale, count or 0)
        return entry.get(category) or entry.get("other") or key

    def gettext(self, key: str, /, **params: Any) -> str:
        """Translate ``key`` and interpolate ``**params``. Alias: ``t``."""
        return self._render(self._select_text(key, None), params)

    def ngettext(self, key: str, count: int, /, **params: Any) -> str:
        """Translate ``key`` choosing a plural form based on ``count``.

        ``count`` is auto-injected as a ``{count}`` param if not supplied.
        """
        params.setdefault("count", count)
        return self._render(self._select_text(key, count), params)

    def _render(self, text: str, params: dict) -> str:
        if params:
            text = _interpolate(text, params)
        if is_pseudo_locale(self._locale):
            text = pseudolocalize(text)
        return text


# -- module-level singleton + convenience API ------------------------------
_translator = Translator()


def get_translator() -> Translator:
    return _translator


def set_locale(locale: str) -> str:
    return _translator.set_locale(locale)


def get_locale() -> str:
    return _translator.locale


def use_detected_locale(config_value: Optional[str] = None) -> str:
    return _translator.use_detected_locale(config_value)


def ensure_detected(config_value: Optional[str] = None) -> str:
    return _translator.ensure_detected(config_value)


def t(key: str, /, **params: Any) -> str:
    """Translate ``key`` now. The workhorse call site helper."""
    return _translator.gettext(key, **params)


def ngettext(key: str, count: int, /, **params: Any) -> str:
    """Plural-aware translate. See :meth:`Translator.ngettext`."""
    return _translator.ngettext(key, count, **params)


class LazyTranslation:
    """A translation whose resolution is deferred until ``str()``.

    Emit this instead of ``t(...)`` when a string may be produced *before*
    the user's locale is finalized (e.g. buffered startup messages). The
    message bus resolves it at render time via ``str()``.
    """

    __slots__ = ("_key", "_count", "_params")

    def __init__(self, key: str, count: Optional[int] = None, **params: Any):
        self._key = key
        self._count = count
        self._params = params

    def __str__(self) -> str:
        if self._count is None:
            return _translator.gettext(self._key, **self._params)
        return _translator.ngettext(self._key, self._count, **self._params)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"LazyTranslation({self._key!r})"


def lazy(key: str, count: Optional[int] = None, **params: Any) -> LazyTranslation:
    """Create a :class:`LazyTranslation` (resolved at ``str()`` time)."""
    return LazyTranslation(key, count, **params)
