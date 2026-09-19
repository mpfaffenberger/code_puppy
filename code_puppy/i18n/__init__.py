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

from .catalog import (
    add_catalog_dir,
    available_locales,
    load_catalog,
    lookup,
    register_plugin_catalog,
    reset,
)
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
    "DEFAULT_LOCALE",
    "PSEUDO_LOCALE",
    "LazyTranslation",
    "Translator",
    "_",
    "add_catalog_dir",
    "available_locales",
    "detect_locale",
    "ensure_detected",
    "fallback_chain",
    "format_datetime",
    "format_number",
    "get_locale",
    "get_translator",
    "is_pseudo_locale",
    "language_of",
    "lazy",
    "load_catalog",
    "lookup",
    "ngettext",
    "normalize_locale",
    "plural_category",
    "pseudolocalize",
    "register_plugin_catalog",
    "reset",
    "set_locale",
    "t",
    "use_detected_locale",
]
