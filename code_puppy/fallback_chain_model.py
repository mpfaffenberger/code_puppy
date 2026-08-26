"""A model that permanently degrades to the next model in a chain once the
current one's *budget* is exhausted (provider quota used up, or the prompt
no longer fits the model's context window).

This is deliberately **not** the same problem ``RoundRobinModel`` solves.
Round-robin distributes load across equivalent models; this class assumes
an ordered preference list (e.g. a large model, then a medium model, then a
free/unmetered one) and only moves down the list when the current model can
no longer serve requests *at all* -- not on ordinary transient hiccups like
a 429 rate-limit or a 5xx blip, which ``code_puppy.agents._runtime``'s
streaming-retry mechanism already handles by retrying the *same* model with
backoff. Retrying the same model on a genuine quota-exhausted or
context-length error is pointless: it will fail identically every time
until the quota window resets, so the only useful move is to switch models.

The switch is one-directional and "sticky" -- once model N is marked
exhausted we never try it again for the lifetime of this instance, we just
keep moving forward through the chain. This mirrors how a human would work
around the same problem: drop to a cheaper model and stay there, rather
than re-poking the expensive one every request and eating the failure
latency each time.
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, List, Optional, Sequence

from pydantic_ai._run_context import RunContext
from pydantic_ai.models import (
    Model,
    ModelMessage,
    ModelRequestParameters,
    ModelResponse,
    ModelSettings,
    StreamedResponse,
    merge_model_settings,
)

from code_puppy.messaging import emit_warning

# Substring signatures (matched lowercase) that indicate a request failed
# because the model's *budget* is used up -- not because of a transient
# network/server hiccup. Kept deliberately separate from
# ``code_puppy.agents._runtime._RETRYABLE_SNIPPETS``: those are "try the
# same model again in a few seconds", these are "this model is done, move
# on". A plain "rate limit"/"too many requests" phrase is intentionally
# NOT included here -- ordinary per-minute rate limits are already handled
# by the same-model retry path and should not trigger a permanent downgrade.
DEFAULT_BUDGET_EXHAUSTED_SNIPPETS: tuple = (
    # OpenAI-style structured error codes
    "insufficient_quota",
    "context_length_exceeded",
    "rate_limit_exceeded_quota",  # some gateways append _quota to disambiguate
    # Common provider/gateway wording for hard quota exhaustion
    "quota exceeded",
    "quota has been exceeded",
    "exceeded your current quota",
    "monthly quota",
    "budget exhausted",
    "token budget",
    "usage limit exceeded",
    "exceeded token limit",
    "quota exhausted",
    "quota depleted",
    "quota reached",
    "exhausted quota",
    "no quota remaining",
    "tokens exhausted",
    "token limit exceeded",
    "daily limit exceeded",
    "monthly limit exceeded",
    "model quota",
    "llm quota",
    # Context-window overflow phrasing (OpenAI, Anthropic, Gemini, generic)
    "maximum context length",
    "context window",
    "context_length",
    "prompt is too long",
    "input is too long",
    "exceeds the model's maximum",
    "too many tokens",
)


DEFAULT_FALLBACK_CHAIN_NAME = "default-fallback-chain"
DEFAULT_FALLBACK_CHAIN_MODELS: tuple[str, ...] = (
    "claude-4-8-opus-long",
    "claude-5-sonnet",
    "gpt-5.6-luna",
)


def add_default_fallback_chain(config: dict[str, Any]) -> bool:
    """Add the requested default chain when all three model keys exist.

    The model entries themselves come from the active catalog/plugins; the
    public project must not ship Walmart-specific endpoints or credentials.
    Returning False when any entry is absent keeps vanilla upstream installs
    unchanged while making the chain automatic for catalogs that provide the
    requested Opus Long -> Sonnet -> Luna sequence.
    """
    if DEFAULT_FALLBACK_CHAIN_NAME in config:
        return False
    if not all(
        isinstance(config.get(name), dict) for name in DEFAULT_FALLBACK_CHAIN_MODELS
    ):
        return False

    context_lengths = [
        config[name].get("context_length", 128000)
        for name in DEFAULT_FALLBACK_CHAIN_MODELS
    ]
    config[DEFAULT_FALLBACK_CHAIN_NAME] = {
        "type": "fallback_chain",
        "models": list(DEFAULT_FALLBACK_CHAIN_MODELS),
        # Use the smallest child window for conservative compaction before
        # the chain has to degrade. This prevents Sonnet from receiving a
        # history that only Opus Long could accommodate.
        "context_length": min(context_lengths or [128000]),
    }
    return True


class FallbackChainExhausted(RuntimeError):
    """Every model in a ``FallbackChainModel`` has had its budget exhausted."""


def is_budget_exhausted_error(
    exc: BaseException, extra_snippets: Sequence[str] = ()
) -> bool:
    """True if ``exc`` (or anything in its cause/context chain) looks like a
    hard budget-exhaustion failure rather than a transient one.

    Checks both the plain ``str(exc)`` and, for ``ModelHTTPError``, the
    structured ``.body`` payload (providers often bury the real error code
    a level deeper than the top-level message, e.g. OpenAI's
    ``{"error": {"code": "insufficient_quota", ...}}``).
    """
    snippets = tuple(s.lower() for s in DEFAULT_BUDGET_EXHAUSTED_SNIPPETS) + tuple(
        s.lower() for s in extra_snippets
    )

    seen: set = set()
    node: Optional[BaseException] = exc
    depth = 0
    while node is not None and id(node) not in seen and depth < 5:
        seen.add(id(node))
        depth += 1

        haystacks = [str(node)]
        body = getattr(node, "body", None)
        if body:
            haystacks.append(str(body))

        for text in haystacks:
            lowered = text.lower()
            if any(s in lowered for s in snippets):
                return True

        node = node.__cause__ or node.__context__

    return False


@dataclass(init=False)
class FallbackChainModel(Model):
    """Try ``models[0]``; on a budget-exhaustion error, permanently advance
    to ``models[1]``, and so on. Any other exception propagates immediately
    -- this class only ever reacts to "this model's budget is spent", never
    to ordinary errors (auth failures, bad requests, bugs, etc.), which
    should surface normally rather than being masked by silently trying a
    different model.

    Raises :class:`FallbackChainExhausted` if every model in the chain has
    been exhausted.
    """

    models: List[Model]
    fallback_on: Callable[[BaseException], bool]
    _child_settings: List[ModelSettings | None] = field(
        default_factory=list, repr=False
    )
    _current_index: int = field(default=0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __init__(
        self,
        *models: Model,
        fallback_on: Optional[Callable[[BaseException], bool]] = None,
        budget_exhausted_patterns: Sequence[str] = (),
        child_settings: Optional[Sequence[ModelSettings | None]] = None,
        settings: ModelSettings | None = None,
    ):
        """
        Args:
            models: Ordered preference chain, e.g. (large, medium, free).
            fallback_on: Optional custom predicate deciding whether an
                exception should trigger a permanent switch to the next
                model. Defaults to :func:`is_budget_exhausted_error`.
            budget_exhausted_patterns: Extra lowercase substrings to treat
                as budget-exhaustion signals, merged with the built-in
                defaults. Ignored if ``fallback_on`` is supplied explicitly.
            child_settings: Optional model-specific defaults, in the same
                order as ``models``. These preserve provider-specific options
                such as adaptive thinking after a switch.
            settings: Model settings used as defaults for this model.
        """
        super().__init__(settings=settings)
        if not models:
            raise ValueError("At least one model must be provided")
        self.models = list(models)
        self._current_index = 0
        self._lock = threading.Lock()
        if child_settings is None:
            self._child_settings = [None] * len(self.models)
        elif len(child_settings) != len(self.models):
            raise ValueError("child_settings must match the number of models")
        else:
            self._child_settings = list(child_settings)
        if fallback_on is not None:
            self.fallback_on = fallback_on
        else:
            self.fallback_on = lambda exc: is_budget_exhausted_error(
                exc, budget_exhausted_patterns
            )

    @property
    def model_name(self) -> str:
        """Full configured chain, plus which model is currently active --
        so status displays (``/model``, ``/usage``) show both the fallback
        plan and the live degradation state at a glance.
        """
        chain = ",".join(m.model_name for m in self.models)
        active = self.models[self._current_index].model_name
        return f"fallback_chain:{chain}:active={active}"

    @property
    def system(self) -> str:
        return self.models[self._current_index].system

    @property
    def base_url(self) -> str | None:
        return self.models[self._current_index].base_url

    def _advance_past_exhausted(self, exhausted_index: int, exc: BaseException) -> bool:
        """Permanently move past ``exhausted_index``. Returns True if a next
        model exists, False if the whole chain is now exhausted.

        Guarded so two concurrent requests hitting the same exhaustion don't
        both emit a warning or both advance the index twice.
        """
        with self._lock:
            if self._current_index != exhausted_index:
                # Another caller already advanced past this one -- nothing
                # left for us to do.
                return self._current_index < len(self.models)
            if exhausted_index + 1 >= len(self.models):
                return False
            exhausted_name = self.models[exhausted_index].model_name
            next_name = self.models[exhausted_index + 1].model_name
            self._current_index = exhausted_index + 1
            emit_warning(
                f"Model '{exhausted_name}' hit a budget/context limit "
                f"({exc}); switching to '{next_name}' for the rest of this "
                "session. Restart code_puppy or reselect a model with "
                "/model to reset back to the top of the chain."
            )
            return True

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        while True:
            index = self._current_index
            current_model = self.models[index]
            model_defaults = self._child_settings[index]
            request_settings = merge_model_settings(model_settings, model_defaults)
            merged_settings, prepared_params = current_model.prepare_request(
                request_settings, model_request_parameters
            )
            try:
                return await current_model.request(
                    messages, merged_settings, prepared_params
                )
            except Exception as exc:
                if not self.fallback_on(exc):
                    raise
                if not self._advance_past_exhausted(index, exc):
                    raise FallbackChainExhausted(
                        f"All {len(self.models)} model(s) in the fallback "
                        f"chain are exhausted. Last error from "
                        f"'{current_model.model_name}': {exc}"
                    ) from exc
                # Loop and retry the same request against the new model.

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncIterator[StreamedResponse]:
        while True:
            index = self._current_index
            current_model = self.models[index]
            model_defaults = self._child_settings[index]
            request_settings = merge_model_settings(model_settings, model_defaults)
            merged_settings, prepared_params = current_model.prepare_request(
                request_settings, model_request_parameters
            )
            try:
                async with current_model.request_stream(
                    messages, merged_settings, prepared_params, run_context
                ) as response:
                    yield response
                    return
            except Exception as exc:
                if not self.fallback_on(exc):
                    raise
                if not self._advance_past_exhausted(index, exc):
                    raise FallbackChainExhausted(
                        f"All {len(self.models)} model(s) in the fallback "
                        f"chain are exhausted. Last error from "
                        f"'{current_model.model_name}': {exc}"
                    ) from exc
                # Loop and retry the same stream request against the new model.
