"""Model-related utilities shared across agents and tools.

This module is intentionally model-agnostic. Anything model-family-specific
(e.g. claude-code OAuth prompt handling) lives in its own plugin and hooks
into the ``prepare_model_prompt`` or ``get_model_system_prompt`` callbacks.

Plugins can register:

- ``prepare_model_prompt``: fully take over prompt prep for a model family.
- ``get_model_system_prompt``: augment/override the system prompt for a model.
"""

import re
from dataclasses import dataclass

_GLM_VERSION_RE = re.compile(r"glm-(\d+(?:\.\d+)?)")


@dataclass
class PreparedPrompt:
    """Result of preparing a prompt for a specific model.

    Attributes:
        instructions: The system instructions to use for the agent
        user_prompt: The user prompt (possibly modified)
        is_claude_code: Whether this is a claude-code model (set by the
            claude_code_oauth plugin via the ``prepare_model_prompt`` hook).
    """

    instructions: str
    user_prompt: str
    is_claude_code: bool


def prepare_prompt_for_model(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    prepend_system_to_user: bool = True,
) -> PreparedPrompt:
    """Prepare instructions and prompt for a specific model.

    Core fires two hooks to let plugins customize prompt prep:

    1. ``prepare_model_prompt`` — first winner with ``handled=True`` takes
       over entirely (used by the claude_code_oauth plugin).
    2. ``get_model_system_prompt`` — legacy per-model system-prompt hook;
       still fired for compatibility with plugins (e.g. agent_skills) that
       rely on it.

    If no plugin handles the model, we return the original system/user prompt
    unchanged.

    Args:
        model_name: The name of the model being used.
        system_prompt: The default system prompt from the agent.
        user_prompt: The user's prompt/message.
        prepend_system_to_user: Whether to prepend the system prompt to the
            user prompt (only meaningful for plugins that opt into it).

    Returns:
        PreparedPrompt ready for the model.
    """
    from code_puppy import callbacks

    # 1) Give the dedicated prepare_model_prompt hook first crack. First
    #    plugin to claim ``handled=True`` wins.
    for result in callbacks.on_prepare_model_prompt(
        model_name, system_prompt, user_prompt, prepend_system_to_user
    ):
        if result and isinstance(result, dict) and result.get("handled"):
            return PreparedPrompt(
                instructions=result.get("instructions", system_prompt),
                user_prompt=result.get("user_prompt", user_prompt),
                is_claude_code=bool(result.get("is_claude_code", False)),
            )

    # 2) Fall back to the legacy per-model system-prompt hook. Two flavours
    #    of plugin live here:
    #      * "taker-over" plugins return ``handled=True`` — first one wins
    #        outright, exactly like ``prepare_model_prompt``.
    #      * "augmenter" plugins (e.g. agent_skills) return ``handled=False``
    #        with mutated ``instructions`` / ``user_prompt``. We thread those
    #        mutations forward so the caller actually sees them, instead of
    #        silently dropping every augmentation on the floor.
    augmented_instructions = system_prompt
    augmented_user_prompt = user_prompt
    for result in callbacks.on_get_model_system_prompt(
        model_name, system_prompt, user_prompt
    ):
        if not (result and isinstance(result, dict)):
            continue
        if result.get("handled"):
            return PreparedPrompt(
                instructions=result.get("instructions", system_prompt),
                user_prompt=result.get("user_prompt", user_prompt),
                is_claude_code=bool(result.get("is_claude_code", False)),
            )
        # Augmenter: carry its mutations forward. Last augmenter wins on
        # collisions (YAGNI: there's exactly one augmenter today).
        if "instructions" in result:
            augmented_instructions = result["instructions"]
        if "user_prompt" in result:
            augmented_user_prompt = result["user_prompt"]

    # 3) No taker-over plugin claimed it — return the (possibly augmented)
    #    prompts.
    return PreparedPrompt(
        instructions=augmented_instructions,
        user_prompt=augmented_user_prompt,
        is_claude_code=False,
    )


def _matches_model_tag(candidate: str, tag: str) -> bool:
    """Return True when ``tag`` appears as a model-name segment.

    Plain substring matching makes ``claude-3-5-sonnet`` and
    ``claude-4-5-sonnet`` both look like a hypothetical ``5-sonnet`` model.
    That is cute, but wrong: those are Sonnet 3.5 and Sonnet 4.5 respectively,
    NOT Sonnet 5. Treat tags as alphanumeric-delimited segments and reject
    any ``X-5-sonnet`` / ``X.5-sonnet`` (or ``-fable``) shape where ``X`` is
    any leading major-version digit.
    """
    start = 0
    while True:
        index = candidate.find(tag, start)
        if index == -1:
            return False

        end = index + len(tag)
        left_is_boundary = index == 0 or not candidate[index - 1].isalnum()
        right_is_boundary = end == len(candidate) or not candidate[end].isalnum()
        old_minor_version_shape = (
            tag in {"5-sonnet", "5-fable"}
            and index >= 2
            and candidate[index - 1] in "-."
            and candidate[index - 2].isdigit()
        )
        if left_is_boundary and right_is_boundary and not old_minor_version_shape:
            return True
        start = index + 1


def _model_matches_any_tag(
    model_name: str, actual_model_id: str | None, tags: tuple[str, ...]
) -> bool:
    """Return True when ``model_name`` OR ``actual_model_id`` matches any tag.

    Shared classifier body for the various ``supports_*`` / ``should_use_*``
    predicates. Checks both the alias/key and the real model ID so
    Bedrock-style names like ``us.anthropic.claude-opus-4-7`` still route
    correctly when only the wrapper alias is passed in.
    """
    candidates = [model_name.lower()]
    if actual_model_id:
        candidates.append(actual_model_id.lower())
    return any(
        _matches_model_tag(candidate, tag) for candidate in candidates for tag in tags
    )


_ADAPTIVE_TAGS: tuple[str, ...] = (
    "opus-4-6",
    "4-6-opus",
    "opus-4-7",
    "4-7-opus",
    "opus-4-8",
    "4-8-opus",
    "sonnet-4-6",
    "4-6-sonnet",
    "sonnet-5",
    "5-sonnet",
    "fable-5",
    "5-fable",
)

_SUMMARY_TAGS: tuple[str, ...] = (
    "opus-4-7",
    "4-7-opus",
    "opus-4-8",
    "4-8-opus",
    "sonnet-5",
    "5-sonnet",
    "fable-5",
    "5-fable",
)


def supports_adaptive_thinking(
    model_name: str, actual_model_id: str | None = None
) -> bool:
    """Return whether a model supports adaptive extended-thinking.

    Opus 4-6/4-7/4-8, Sonnet 4-6, Sonnet 5, and Fable 5 accept (and require)
    ``thinking={"type": "adaptive"}`` at the wire level. Every other Claude
    variant wants the classic ``type: "enabled"`` shape.

    Args:
        model_name: The model alias/key (e.g. ``"bedrock-opus-4-7"``).
        actual_model_id: The real model ID from config (e.g.
            ``"us.anthropic.claude-opus-4-7"``).
    """
    return _model_matches_any_tag(model_name, actual_model_id, _ADAPTIVE_TAGS)


def get_default_extended_thinking(
    model_name: str, actual_model_id: str | None = None
) -> str:
    """Return the default extended_thinking mode for an Anthropic model.

    Opus 4-6, Opus 4-7, Opus 4-8, Sonnet 4-6, Sonnet 5, and Fable 5 models
    default to ``"adaptive"`` thinking; all other Anthropic models default to
    ``"enabled"``.

    Args:
        model_name: The model alias/key (e.g. ``"bedrock-opus-4-7"``).
        actual_model_id: The real model ID from config (e.g.
            ``"us.anthropic.claude-opus-4-7"``).

    Returns:
        ``"adaptive"`` for supported variants, ``"enabled"`` otherwise.
    """
    if supports_adaptive_thinking(model_name, actual_model_id):
        return "adaptive"
    return "enabled"


def should_use_anthropic_thinking_summary(
    model_name: str, actual_model_id: str | None = None
) -> bool:
    """Return whether Anthropic adaptive thinking should request summary display.

    Anthropic's newer Opus 4.7+, Opus 4.8, Sonnet 5, and Fable 5 models accept
    ``display: \"summarized\"`` alongside ``thinking={"type": "adaptive"}`` to
    surface a condensed reasoning trace instead of the full block.
    """
    return _model_matches_any_tag(model_name, actual_model_id, _SUMMARY_TAGS)


def resolve_anthropic_thinking_payload(
    extended_thinking: str,
    *,
    budget_tokens: int,
    model_name: str,
    actual_model_id: str | None,
) -> dict | None:
    """Map Code Puppy's internal thinking mode to the shape THIS model accepts.

    Anthropic-family models split into two camps that reject each other's shape:

    * **Classic** (Sonnet 4.5 and earlier, Haiku, etc.): only ``type: "enabled"``
      (with ``budget_tokens``) or ``type: "disabled"``. Sending ``"adaptive"``
      yields the reporter's error:
      ``Input tag 'adaptive' does not match any of the expected tags: 'disabled', 'enabled'``.
    * **Adaptive** (Opus 4.6/4.7/4.8, Sonnet 4.6, Sonnet 5, Fable 5): the
      opposite — rejects ``type: "enabled"`` with
      ``"thinking.type.enabled" is not supported for this model. Use adaptive."``.
      These models want ``type: "adaptive"`` and optionally ``display: "summarized"``.

    This helper picks the right shape based on ``supports_adaptive_thinking``
    so a user's choice of ``"enabled"`` / ``"adaptive"`` (from the settings
    menu, from defaults, or from legacy booleans) always translates to a
    wire payload the specific target model actually accepts.

    Args:
        extended_thinking: The internal mode. Any of ``"enabled"`` /
            ``"adaptive"`` produces a payload (coerced to the model's shape).
            Anything else (``"off"``, ``"disabled"``, unknown, ``None``)
            returns ``None`` so the caller omits ``anthropic_thinking``.
        budget_tokens: Token budget for classic ``type: "enabled"`` mode.
            Ignored on adaptive-supporting models (they compute their own).
        model_name: The model alias/key (drives adaptive/summary detection).
        actual_model_id: The real model ID from config (also checked so
            Bedrock-style aliases like ``us.anthropic.claude-opus-4-7`` still
            route correctly).

    Returns:
        Dict suitable for ``AnthropicModelSettings.anthropic_thinking``,
        or ``None`` when thinking should be omitted entirely.
    """
    if extended_thinking not in ("enabled", "adaptive"):
        return None
    if supports_adaptive_thinking(model_name, actual_model_id):
        payload: dict = {"type": "adaptive"}
        if should_use_anthropic_thinking_summary(model_name, actual_model_id):
            payload["display"] = "summarized"
        return payload
    return {"type": "enabled", "budget_tokens": budget_tokens}


def get_glm_version(model_name: str) -> float | None:
    """Extract the numeric GLM/Zhipu version embedded in a model name.

    Model aliases are messy (``zai-glm-5.1-api``, ``GLM-4.5-AIR-CODING``,
    ``lilac-zai-org-glm-5.1``) so we pattern-match ``glm-<digits>`` wherever
    it shows up rather than relying on prefix/suffix assumptions.

    Returns:
        The version as a float (e.g. ``5.1``), or ``None`` if the name
        doesn't look like a GLM model at all.
    """
    match = _GLM_VERSION_RE.search(model_name.lower())
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def supports_glm_thinking(model_name: str) -> bool:
    """GLM-4.5 and newer expose the ``thinking.type`` deep-thinking toggle.

    Per Zhipu's docs: GLM-5.2/5.1/5/5-Turbo/5V-Turbo/4.6/4.5 auto-decide
    whether to think, while GLM-4.7 and GLM-4.5V use forced thinking (the
    setting still round-trips, the server just won't honor "disabled").
    """
    version = get_glm_version(model_name)
    return version is not None and version >= 4.5


def supports_glm_reasoning_effort(model_name: str) -> bool:
    """Only GLM-5.2 and newer support the ``reasoning_effort`` parameter."""
    version = get_glm_version(model_name)
    return version is not None and version >= 5.2


def get_thinking_tags(
    model_name: str, model_config: dict | None = None
) -> tuple[str, str] | None:
    """Return the (start, end) tag pair a model wraps reasoning output in.

    pydantic-ai defaults every model's ``ModelProfile.thinking_tags`` to
    ``('<think>', '</think>')``, which covers the vast majority of
    reasoning models (DeepSeek-R1, Qwen, GLM, etc). This only needs to
    return something when a model deviates from that default. Two ways
    to opt in, checked in order:

    1. Explicit ``"thinking_tags": [start, end]`` in the model's config
       entry - lets anyone fix a quirky endpoint via extra_models.json
       without touching code.
    2. Known proxy-specific quirks hardcoded here. Lilac's hosted
       MiniMax-M3 proxy remaps reasoning into ``<mm:think>...</mm:think>``
       instead of forwarding the model's native ``<think>`` tags -- this
       is a lilac-the-proxy quirk, NOT a MiniMax-the-model one, so it's
       scoped to ``provider == "lilac"`` and must not fire for MiniMax
       served directly or through any other provider.

    Returns ``None`` when the pydantic-ai default should be left alone.
    """
    if model_config:
        override = model_config.get("thinking_tags")
        if override and len(override) == 2:
            return (str(override[0]), str(override[1]))

    is_lilac = bool(model_config) and model_config.get("provider") == "lilac"
    if is_lilac:
        candidates = [model_name.lower()]
        actual_id = (model_config or {}).get("name")
        if actual_id:
            candidates.append(actual_id.lower())

        if any("minimax" in c for c in candidates):
            return ("<mm:think>", "</mm:think>")

    return None
