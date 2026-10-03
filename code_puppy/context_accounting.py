"""Context totals anchored to completed API requests, with a heuristic delta.

Compaction, the status bar, and the context indicator all used to sum a
char/2.5 estimate over the whole message history. That heuristic drifts from
what the provider actually billed -- especially once caching is involved
(Anthropic cache read/write, OpenAI cached tokens) -- and the drift compounds
every turn.

Every completed model response already carries the provider's own prompt
token count (``response.usage.input_tokens``), which is ground truth for
every message that came before it. This module anchors the running total to
the latest such response and only estimates the *delta* since then: messages
added after the anchor, plus any change in accounting overhead (system
prompt, tool schemas, MCP tool definitions). The anchor travels with the
response through session JSON as a receipt; a receipt is valid only for the
exact prompt prefix and response that produced it, so any rewrite (manual
edit, compaction, tool-output clamping, a plugin transform, a model switch)
falls back to the full estimate rather than risk a stale number.
"""

import hashlib
import json

from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, TextPart


def estimate_tokens_for_message(message, model_name):
    """Import lazily so the shared entry point has no agent-package cycle."""
    from code_puppy.agents._history import estimate_tokens_for_message as estimate

    return estimate(message, model_name)


_ANCHOR = "context_anchor"


def fingerprint(messages) -> str:
    """Include arguments, signatures and binary payloads, excluding receipts.

    Receipts live under ``metadata`` so stamping one does not change the
    fingerprint of the message it rides on -- otherwise a receipt would
    invalidate itself the instant it was written.
    """
    clean = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    payload = [
        {
            key: value
            for key, value in message.items()
            if key in {"parts", "instructions", "kind"}
        }
        for message in clean
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def record_anchor(messages, response, *, context_overhead=0, prefix=None):
    """Stamp only a successfully completed response; usage is never fabricated."""
    if (
        response.usage.input_tokens <= 0
        or not response.model_name
        or response.state != "complete"
    ):
        return
    response.metadata = dict(response.metadata or {})
    response.metadata[_ANCHOR] = {
        "prefix": prefix if prefix is not None else fingerprint(messages),
        "response": fingerprint([response]),
        "overhead": context_overhead,
    }


def invalidate_anchors(messages):
    """A failed/cancelled request cannot leave a previously trusted anchor."""
    for message in messages:
        if isinstance(message, ModelResponse) and message.metadata:
            message.metadata.pop(_ANCHOR, None)


def context_tokens(messages, model_name, context_overhead=0) -> int:
    """One total for compaction, the status bar, and context metadata.

    API input includes system/tool/cache tokens. Plain text output usage is
    an incremental approximation; reasoning/tool replay is estimated instead.
    Only the latest response may anchor: partial/zero usage must not cause a
    silent rewind to an older observation.
    """
    names = model_name if isinstance(model_name, frozenset) else {model_name}
    estimate_model = next(iter(names)) if len(names) == 1 else None
    for index in range(len(messages) - 1, -1, -1):
        response = messages[index]
        if not isinstance(response, ModelResponse):
            continue
        receipt = (response.metadata or {}).get(_ANCHOR)
        if (
            isinstance(receipt, dict)
            and response.usage.input_tokens > 0
            and response.state == "complete"
            and response.model_name in names
            and receipt.get("prefix") == fingerprint(messages[:index])
            and receipt.get("response") == fingerprint([response])
            and isinstance(receipt.get("overhead"), (int, float))
        ):
            replay = (
                response.usage.output_tokens
                if response.parts
                and all(isinstance(p, TextPart) for p in response.parts)
                and response.usage.output_tokens > 0
                else estimate_tokens_for_message(response, response.model_name)
            )
            return (
                response.usage.input_tokens
                + replay
                + context_overhead
                - receipt["overhead"]
                + sum(
                    estimate_tokens_for_message(m, estimate_model)
                    for m in messages[index + 1 :]
                )
            )
        break
    return context_overhead + sum(
        estimate_tokens_for_message(m, estimate_model) for m in messages
    )


def active_model_name(agent):
    """Use the actual provider identity, not a config alias, when available."""
    model = getattr(agent, "cur_model", None)
    if model is None:
        model = getattr(getattr(agent, "pydantic_agent", None), "model", None)
    return model_names(model) if model is not None else agent.get_model_name()


def model_names(model):
    """A routing model's responses use concrete candidate identities."""
    candidates = getattr(model, "models", ())
    if candidates:
        return frozenset({model.model_name, *(m.model_name for m in candidates)})
    return model.model_name
