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

import threading
from typing import Any, Optional

from . import catalog
from .locale import DEFAULT_LOCALE, detect_locale, normalize_locale
from .plurals import plural_category
from .pseudo import is_pseudo_locale, pseudolocalize


class _SafeDict(dict):
    """dict that leaves unknown ``{keys}`` untouched during format_map."""

    def __missing__(self, key: str) -> str:  # noqa: D401 - trivial
        return "{" + key + "}"


class Translator:
    """Holds the active locale and resolves translation keys against it."""

    def __init__(
        self, locale: Optional[str] = None, default_locale: str = DEFAULT_LOCALE
    ) -> None:
        self._default = normalize_locale(default_locale) or DEFAULT_LOCALE
        self._lock = threading.RLock()
        self._locale = normalize_locale(locale) or self._default

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
        return normalized

    def use_detected_locale(self, config_value: Optional[str] = None) -> str:
        """Resolve via the env/config/default chain and apply it."""
        return self.set_locale(detect_locale(config_value, self._default))

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
            try:
                text = text.format_map(_SafeDict(params))
            except (IndexError, ValueError):
                # Malformed template — surface the raw string rather than die.
                pass
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
