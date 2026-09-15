"""Shared i18n test isolation.

Every i18n test file previously duplicated the same autouse fixture
(reset catalog + force en-US, optionally clearing locale env vars). One
autouse fixture here replaces all nine per-file copies.
"""

import pytest

from code_puppy.i18n import catalog, translate

_LOCALE_ENV_VARS = ("CODE_PUPPY_LOCALE", "LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")


@pytest.fixture(autouse=True)
def _i18n_isolate(monkeypatch):
    for var in _LOCALE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    catalog.reset()
    translate.get_translator().set_locale("en-US")
    yield
    catalog.reset()
    translate.get_translator().set_locale("en-US")
