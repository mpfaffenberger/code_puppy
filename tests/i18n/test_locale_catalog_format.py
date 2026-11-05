"""Shipped locale catalogs stay in one canonical on-disk format.

Hand edits and ad-hoc ``json.dump`` calls drift easily (unsorted keys,
``\\uXXXX`` escapes for emoji). Pinning the format keeps catalog diffs
reviewable and free of unrelated churn.
"""

import json
from pathlib import Path

import pytest

from code_puppy.i18n import catalog

_LOCALE_DIR = Path(catalog.__file__).parent / "locales"


@pytest.mark.parametrize(
    "path", sorted(_LOCALE_DIR.glob("*.json")), ids=lambda path: path.stem
)
def test_catalog_is_canonically_formatted(path):
    raw = path.read_text(encoding="utf-8")
    canonical = (
        json.dumps(json.loads(raw), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    assert raw == canonical, (
        f"{path.name} is not canonical; rewrite it with "
        "json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + '\\n'"
    )
