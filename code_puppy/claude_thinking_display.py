"""Thinking ``display`` / off-switch normalization for Anthropic request bodies.

The API only accepts ``display`` while thinking runs (``adaptive`` /
``enabled``). Which "thinking off" shape a model accepts differs per model, so
nothing here names a model: the client learns it from the provider's own 400.

Called by: claude_cache_client :: ClaudeCacheAsyncClient.send()
"""


def _model_requires_thinking_summary(model_name):
    if not model_name:
        return False
    from code_puppy.model_utils import should_use_anthropic_thinking_summary

    return should_use_anthropic_thinking_summary(model_name)


def _model_supports_thinking_updates(model_name):
    if not model_name:
        return False
    from code_puppy.model_utils import should_use_anthropic_thinking_updates

    return should_use_anthropic_thinking_updates(model_name)


# The API only accepts ``thinking.display`` while thinking actually runs.
_DISPLAY_THINKING_TYPES = frozenset({"adaptive", "enabled"})
_OFF_THINKING_TYPES = frozenset({"disabled", "between_tools"})

# (endpoint, model) pairs whose API refused an "off" thinking shape and then
# accepted the request without it (see ``_retry_without_thinking_after_400``).
# Never listed by name: each family accepts a different off-switch, and the
# same model ID can sit behind providers that disagree, hence the endpoint.
_THINKING_OMITTED_WHEN_OFF: set[tuple] = set()


def _thinking_endpoint(url):
    return (url.host, url.port, url.path)


def _normalize_thinking_off(payload, thinking, endpoint):
    modified = thinking.pop("display", None) is not None
    if (
        thinking.get("type") in _OFF_THINKING_TYPES
        and (endpoint, payload.get("model")) in _THINKING_OMITTED_WHEN_OFF
    ):
        del payload["thinking"]
        return True
    return modified


def _enforce_thinking_display_summary(payload, endpoint=None):
    if not isinstance(payload, dict):
        return False
    thinking = payload.get("thinking")
    if not isinstance(thinking, dict):
        return False
    if thinking.get("type") not in _DISPLAY_THINKING_TYPES:
        return _normalize_thinking_off(payload, thinking, endpoint)
    if not _model_requires_thinking_summary(payload.get("model")):
        return False
    display = thinking.get("display")
    if display == "summarized":
        return False
    if display == "updates" and _model_supports_thinking_updates(payload.get("model")):
        # Fable 5.1 legitimately asked for progress updates; don't clobber
        # it back to summarized (which would drown status lines in reasoning).
        return False
    thinking["display"] = "summarized"
    return True
