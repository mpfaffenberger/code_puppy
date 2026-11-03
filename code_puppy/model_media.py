"""Binary document media types a model accepts as embedded files.

Derived only from models.dev ``input_modalities``. Anything unresolved or
ambiguous yields ``[]`` so callers fall back to plain text rather than
sending a document the model cannot read.
"""

from __future__ import annotations

from typing import Optional

from code_puppy.error_logging import log_error
from code_puppy.model_factory import ModelFactory
from code_puppy.models_dev_parser import (
    ModelInfo,
    ModelsDevRegistry,
    extra_model_key,
    get_registry,
)

_PDF_MODALITY = "pdf"
_PDF_MEDIA_TYPE = "application/pdf"

# Keyed on the registry object itself; a different (or absent) registry
# rebuilds the index. Holding the reference keeps the identity check sound.
_index_cache: Optional[
    tuple[ModelsDevRegistry, dict[str, list[ModelInfo]], dict[str, list[ModelInfo]]]
] = None


def supported_binary_media_types(model_name: str | None) -> list[str]:
    """Binary document media types ``model_name`` accepts, or ``[]`` if unknown.

    Never raises: any failure resolves to "unknown" and is logged once.
    Control-flow exceptions (``BaseException``) propagate unlogged.
    """
    try:
        return _resolve(model_name)
    except Exception as exc:
        _report(exc, "model_media::supported_binary_media_types: lookup failed")
        return []


def _report(exc: Exception, context: str) -> None:
    # A failing logger must never change the fail-soft result.
    try:
        log_error(exc, context=context)
    except Exception:
        pass


def _resolve(model_name: str | None) -> list[str]:
    if not model_name:
        return []
    registry = get_registry()
    if registry is None:
        return []
    by_key, by_name = _index(registry)

    # Mirrors extra_model_key() over a "provider/model" alias.
    key = model_name.replace("/", "-").replace(":", "-")
    exact = by_key.get(key, [])
    if len(exact) == 1:
        return _media_types(exact[0])

    entry = _catalog_entry(model_name)
    name = entry.get("name") if entry else None
    if not isinstance(name, str) or not name:
        return []
    candidates = by_name.get(name, [])
    answers = {tuple(_media_types(candidate)) for candidate in candidates}
    if len(answers) != 1:
        return []
    return list(answers.pop())


def _index(
    registry: ModelsDevRegistry,
) -> tuple[dict[str, list[ModelInfo]], dict[str, list[ModelInfo]]]:
    global _index_cache
    if _index_cache is not None and _index_cache[0] is registry:
        return _index_cache[1], _index_cache[2]
    by_key: dict[str, list[ModelInfo]] = {}
    by_name: dict[str, list[ModelInfo]] = {}
    for model in registry.get_models():
        by_key.setdefault(
            extra_model_key(model.provider_id, model.model_id), []
        ).append(model)
        by_name.setdefault(model.model_id, []).append(model)
    _index_cache = (registry, by_key, by_name)
    return by_key, by_name


def _catalog_entry(model_name: str) -> Optional[dict]:
    try:
        entry = ModelFactory.load_config().get(model_name)
    except Exception as exc:
        # Swallowed here, so the outer handler never sees it: one record.
        _report(exc, "model_media::_catalog_entry: catalog load failed")
        return None
    return entry if isinstance(entry, dict) else None


def _media_types(model: ModelInfo) -> list[str]:
    return [_PDF_MEDIA_TYPE] if _PDF_MODALITY in model.input_modalities else []
