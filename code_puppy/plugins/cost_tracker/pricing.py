"""Offline pricing lookup for the cost_tracker plugin.

Resolves a Code Puppy model-config name (e.g. ``gpt-5``, ``qwen1``) to
per-million-token prices using the **bundled** ``models_dev_api.json``
database that ships with Code Puppy for the ``/add_model`` offline
fallback.

Design constraints:

* **Never touches the network.** The project has a hard privacy
  commitment; pricing lookups read only the bundled JSON that is already
  on disk. If a model isn't in the bundle, its cost is simply reported
  as *unknown* (tokens are still tracked).
* **Deterministic.** The same model name always resolves to the same
  price. When one model id exists under several providers with
  different prices, the provider inferred from the model config's
  ``type`` wins; otherwise the alphabetically-first provider id is used
  and the result is (like everything here) labeled an estimate.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# models.dev prices are USD per **million** tokens.
_TOKENS_PER_PRICE_UNIT = 1_000_000

# Model-config ``type`` values whose providers report usage
# Anthropic-style: ``input_tokens`` EXCLUDES cache reads/writes (they are
# billed separately at their own rates). Everything else is treated
# OpenAI-style, where ``input_tokens`` INCLUDES the cached portion and the
# cached portion is billed at the (discounted) cache-read rate instead of
# the full input rate. Mirrors the semantics split already used by
# ``model_factory`` for cache accounting.
ANTHROPIC_STYLE_TYPES = frozenset(
    {
        "anthropic",
        "custom_anthropic",
        "claude_code",
        "aws_bedrock",
        "azure_foundry",
    }
)

# Map Code Puppy model-config ``type`` -> models.dev provider id, used to
# disambiguate when the same model id is listed under several providers.
_TYPE_TO_PROVIDER: Dict[str, str] = {
    "anthropic": "anthropic",
    "custom_anthropic": "anthropic",
    "claude_code": "anthropic",
    "openai": "openai",
    "chatgpt_oauth": "openai",
    "azure_openai": "azure",
    "gemini": "google",
    "custom_gemini": "google",
    "gemini_oauth": "google",
    "cerebras": "cerebras",
    "openrouter": "openrouter",
    "copilot": "github-copilot",
    "aws_bedrock": "amazon-bedrock",
    "groq": "groq",
    "mistral": "mistral",
    "deepseek": "deepseek",
}

# Strip trailing date/version noise when an exact id match fails, e.g.
# ``claude-sonnet-4-20250514`` -> ``claude-sonnet-4``.
_DATE_SUFFIX_RE = re.compile(r"-(20\d{6}|latest|v\d+)$")


@dataclass(frozen=True)
class ModelPricing:
    """Per-million-token USD prices for one (provider, model) pair."""

    provider_id: str
    model_id: str
    input: Optional[float] = None
    output: Optional[float] = None
    cache_read: Optional[float] = None
    cache_write: Optional[float] = None

    @property
    def has_any_price(self) -> bool:
        return any(v is not None for v in (self.input, self.output, self.cache_read))


# ---------------------------------------------------------------------------
# Bundled DB loading + indexing (lazy, cached, offline-only)
# ---------------------------------------------------------------------------
_INDEX: Optional[Dict[str, List[Tuple[str, ModelPricing]]]] = None


def _bundled_db_path() -> pathlib.Path:
    import code_puppy

    return pathlib.Path(code_puppy.__file__).parent / "models_dev_api.json"


def _coerce_price(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        price = float(value)
        return price if price >= 0 else None
    except (TypeError, ValueError):
        return None


def _build_index() -> Dict[str, List[Tuple[str, ModelPricing]]]:
    """Flatten the bundled models.dev DB into ``model_id -> candidates``.

    Candidate lists are sorted by provider id so resolution is
    deterministic regardless of JSON key order.
    """
    index: Dict[str, List[Tuple[str, ModelPricing]]] = {}
    try:
        with open(_bundled_db_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:  # pragma: no cover - missing bundle is unusual
        logger.warning(f"cost_tracker: could not load bundled pricing DB: {exc}")
        return index

    if not isinstance(raw, dict):
        return index

    for provider_id, provider_data in raw.items():
        if not isinstance(provider_data, dict):
            continue
        models = provider_data.get("models", {})
        if not isinstance(models, dict):
            continue
        for model_id, model_data in models.items():
            if not isinstance(model_data, dict):
                continue
            cost = model_data.get("cost", {})
            if not isinstance(cost, dict):
                cost = {}
            pricing = ModelPricing(
                provider_id=str(provider_id),
                model_id=str(model_id),
                input=_coerce_price(cost.get("input")),
                output=_coerce_price(cost.get("output")),
                cache_read=_coerce_price(cost.get("cache_read")),
                cache_write=_coerce_price(cost.get("cache_write")),
            )
            index.setdefault(str(model_id).lower(), []).append(
                (str(provider_id), pricing)
            )

    for candidates in index.values():
        candidates.sort(key=lambda pair: pair[0])
    return index


def _get_index() -> Dict[str, List[Tuple[str, ModelPricing]]]:
    global _INDEX
    if _INDEX is None:
        _INDEX = _build_index()
    return _INDEX


def clear_pricing_cache() -> None:
    """Testing hook: drop the cached index so it rebuilds on next use."""
    global _INDEX
    _INDEX = None


# ---------------------------------------------------------------------------
# Resolution: config name -> ModelPricing
# ---------------------------------------------------------------------------
def _lookup_candidates(model_id: str) -> List[Tuple[str, ModelPricing]]:
    index = _get_index()
    key = model_id.lower()
    if key in index:
        return index[key]
    stripped = _DATE_SUFFIX_RE.sub("", key)
    if stripped != key and stripped in index:
        return index[stripped]
    return []


def _pick_candidate(
    candidates: List[Tuple[str, ModelPricing]], model_type: str
) -> Optional[ModelPricing]:
    if not candidates:
        return None
    preferred_provider = _TYPE_TO_PROVIDER.get(model_type)
    if preferred_provider:
        for provider_id, pricing in candidates:
            if provider_id == preferred_provider:
                return pricing
    # Deterministic fallback: alphabetically-first provider (list is sorted).
    return candidates[0][1]


def resolve_pricing(
    model_name: str,
    config: Optional[Dict[str, Any]] = None,
    _depth: int = 0,
) -> Tuple[Optional[ModelPricing], bool]:
    """Resolve pricing for a Code Puppy model-config name.

    Args:
        model_name: The config key as reported by ``agent.get_model_name()``
            (e.g. ``gpt-5``, ``qwen1``, ``my-round-robin``).
        config: The full models config dict. When ``None`` it is loaded via
            ``ModelFactory.load_config()``.
        _depth: Internal recursion guard for round-robin indirection.

    Returns:
        ``(pricing, anthropic_style)``. ``pricing`` is ``None`` when the
        model can't be found in the bundled DB (cost then reports as
        unknown, tokens still tracked). ``anthropic_style`` describes how
        cache tokens relate to input tokens for this model's provider.
    """
    if _depth > 3:
        return None, False

    if config is None:
        try:
            from code_puppy.model_factory import ModelFactory

            config = ModelFactory.load_config()
        except Exception as exc:
            logger.debug(f"cost_tracker: could not load model config: {exc}")
            config = {}

    entry = config.get(model_name) if isinstance(config, dict) else None
    entry = entry if isinstance(entry, dict) else {}
    model_type = str(entry.get("type", "") or "")
    anthropic_style = model_type in ANTHROPIC_STYLE_TYPES

    # Round-robin models front several concrete models (typically the same
    # underlying model split across API keys) - price via the first member.
    if model_type == "round_robin":
        members = entry.get("models") or []
        if isinstance(members, list) and members:
            return resolve_pricing(str(members[0]), config, _depth + 1)
        return None, False

    underlying = str(entry.get("name") or model_name)
    candidates = _lookup_candidates(underlying)
    if not candidates and underlying != model_name:
        candidates = _lookup_candidates(model_name)

    pricing = _pick_candidate(candidates, model_type)
    if pricing is not None and not pricing.has_any_price:
        pricing = None
    return pricing, anthropic_style


def estimate_cost_usd(
    pricing: ModelPricing,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    anthropic_style: bool = False,
) -> float:
    """Estimate USD cost for one run's billed token counts.

    Two accounting styles:

    * ``anthropic_style=True``: ``input_tokens`` excludes cache traffic, so
      every bucket is billed at its own rate and simply summed.
    * ``anthropic_style=False`` (OpenAI-style): ``input_tokens`` includes the
      cached portion. The cached portion is billed at the cache-read rate
      (when known) and subtracted from full-rate input; without a cache-read
      rate the whole input bills at the input rate.

    Reasoning/"thought" tokens are intentionally NOT billed separately:
    every major provider already includes them in the billed output count,
    so adding them again would double-charge.
    """
    input_tokens = max(int(input_tokens or 0), 0)
    output_tokens = max(int(output_tokens or 0), 0)
    cache_read_tokens = max(int(cache_read_tokens or 0), 0)
    cache_write_tokens = max(int(cache_write_tokens or 0), 0)

    in_rate = pricing.input or 0.0
    out_rate = pricing.output or 0.0
    cr_rate = pricing.cache_read
    cw_rate = pricing.cache_write

    if anthropic_style:
        full_rate_input = input_tokens
        cached_read_billed = cache_read_tokens
    else:
        if cr_rate is not None and cache_read_tokens:
            full_rate_input = max(input_tokens - cache_read_tokens, 0)
            cached_read_billed = min(cache_read_tokens, input_tokens)
        else:
            full_rate_input = input_tokens
            cached_read_billed = 0

    cost = full_rate_input * in_rate + output_tokens * out_rate
    if cr_rate is not None:
        cost += cached_read_billed * cr_rate
    if cw_rate is not None:
        cost += cache_write_tokens * cw_rate
    return cost / _TOKENS_PER_PRICE_UNIT
