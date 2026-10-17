"""Context totals anchored to completed API requests, with a heuristic delta.

A receipt identifies the unchanged measured prefix, response and request
model; new content and changed overhead remain estimates. Invalid receipts
fall back rather than reuse stale usage. Continuation-merged responses do
not anchor because cumulative billing is not a single measured prompt.

Design, provider limitations and rollout semantics are documented in
``docs/API_CONTEXT_ACCOUNTING.md``. The request hook owns continuation
observation; this module never alters provider usage or billing.
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


def record_anchor(
    messages, response, *, context_overhead=0, prefix=None, request_model=None
):
    """Stamp only a successfully completed response; usage is never fabricated.

    Trusts ``prefix`` and ``response.usage`` as given -- it has no way to
    tell a continuation-merged (cumulative) usage from an ordinary one on
    its own. The caller must not call this helper when a continuation was observed
    (see ``_ContinuationObserver`` in ``agents/_model_message_transform.py``).
    Here, ``prefix=None`` computes a fingerprint; it does not suppress stamping.
    """
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
        "request_models": sorted(
            request_model
            if isinstance(request_model, frozenset)
            else {request_model if request_model is not None else response.model_name}
        ),
    }


def invalidate_anchors(messages):
    """Conservatively decline anchors after an unsuccessful request.

    This is a deliberate failed-request policy, not proof the old measurement
    became invalid. An unchanged prefix could retain its previous receipt,
    and a retained partial response already forces fallback. We nevertheless
    choose full estimation until a fresh completion; changing that contract
    requires reconsidering the failure/cancellation regressions together.
    """
    for message in messages:
        if isinstance(message, ModelResponse) and message.metadata:
            message.metadata.pop(_ANCHOR, None)


def context_tokens(messages, model_name, context_overhead=0) -> int:
    """One total for compaction, the status bar, and context metadata.

    API input includes system/tool/cache tokens. Plain text output usage is
    an incremental approximation; it may include hidden reasoning when no
    ThinkingPart is exposed, conservatively overestimating replay. Visible
    reasoning/tool replay is estimated instead.
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
            and receipt.get("request_models") == sorted(names)
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
    """Use the request model identity, not an arbitrary config alias."""
    model = getattr(agent, "cur_model", None)
    if model is None:
        model = getattr(getattr(agent, "pydantic_agent", None), "model", None)
    return model_names(model) if model is not None else agent.get_model_name()


def model_names(model):
    """Identify a request model together with its routing candidates."""
    candidates = getattr(model, "models", ())
    if candidates:
        return frozenset({model.model_name, *(m.model_name for m in candidates)})
    return model.model_name
