"""Code Puppy internationalization (i18n) foundation.

Day-one localization framework: message catalogs with a fallback chain,
locale detection/override, plural-aware translation, locale-aware formatting,
and pseudolocalization for coverage testing. Stdlib-only by design.

Typical call-site usage::

    from code_puppy.i18n import t, ngettext

    emit_info(t("startup.welcome", name=owner))
    emit_info(ngettext("files.deleted", count=n))

To resolve the active locale from the environment/config at boot::

    from code_puppy.i18n import use_detected_locale
    from code_puppy.config import get_value

    use_detected_locale(get_value("locale"))

See ``PUP-473`` (epic) and ``PUP-475`` (this foundation story) for scope.
"""

from .catalog import add_catalog_dir, available_locales, load_catalog, lookup, reset
from .formats import format_datetime, format_number
from .locale import (
    DEFAULT_LOCALE,
    detect_locale,
    fallback_chain,
    language_of,
    normalize_locale,
)
from .plurals import plural_category
from .pseudo import PSEUDO_LOCALE, is_pseudo_locale, pseudolocalize
from .translate import (
    LazyTranslation,
    Translator,
    ensure_detected,
    get_locale,
    get_translator,
    lazy,
    ngettext,
    set_locale,
    t,
    use_detected_locale,
)

# Common gettext-style alias so call sites can `from code_puppy.i18n import _`.
_ = t

__all__ = [
    "_",
    "t",
    "ngettext",
    "lazy",
    "LazyTranslation",
    "Translator",
    "get_translator",
    "get_locale",
    "set_locale",
    "use_detected_locale",
    "ensure_detected",
    "detect_locale",
    "normalize_locale",
    "fallback_chain",
    "language_of",
    "DEFAULT_LOCALE",
    "plural_category",
    "format_number",
    "format_datetime",
    "add_catalog_dir",
    "available_locales",
    "load_catalog",
    "lookup",
    "reset",
    "pseudolocalize",
    "is_pseudo_locale",
    "PSEUDO_LOCALE",
]
