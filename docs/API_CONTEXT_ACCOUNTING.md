# API-anchored context accounting

Completed model responses carry API-reported input usage, including cache
read/write tokens already normalized by pydantic-ai. Context counting starts
from that observation, then adds the replayed response and new messages.
Plain-text output usage approximates the replay increment; reasoning and tool
responses use the existing message estimator because generated/hidden thinking
is not an exact count of its next-request replay representation. Text-only
responses can still include hidden reasoning in output usage when the provider
exposes no thinking part, conservatively overestimating replay.

Fallback and delta estimates use the request model ID, not arbitrary user
configuration aliases. A custom alias containing a calibration substring
(e.g. `opus-4-7`) no longer applies that multiplier to an unrelated provider
model. For multi-candidate routing there is no single estimator model, so
fallback and new-message estimates omit model-specific calibration. Where a
candidate normally has an upward multiplier, this can undercount and delay
compaction; a valid API anchor still accounts for its measured prefix.
This keeps display and compaction aligned. Prefix checks serialize and
hash the full message payload, including binary data; very large attachment
histories can therefore add CPU and allocation overhead.

One `context_tokens` function drives compaction, the status bar and context
metadata. Detailed `/context` overhead buckets are still estimates, not an
exact billed-token partition; their displayed sum remains the Overhead value.
API input already includes system/tools. Only the difference between current
overhead and recorded overhead is added, so evolving overhead (system prompt,
tool schemas, MCP tool definitions) does not discard an otherwise valid
anchor.

## Validity and sessions

The outbound request transform stamps successful, complete responses with a
SHA-256 fingerprint of their measured message prefix and response, plus the
overhead estimate and request model identity used for that same request.
Provider-returned model IDs may be dated aliases; they need not match the
configured request ID. Receipts instead require the same request identity,
including the complete candidate set for routing models. Legacy receipts
without that identity fall back until a new request establishes an anchor.
Fingerprints include arguments,
signatures and binary data but omit framework bookkeeping and anchor
metadata. The receipt survives session JSON serialization (it rides in
`ModelResponse.metadata`). Only the latest response can anchor. Routing
models (e.g. `RoundRobinModel`) retain anchoring while routing among their
unchanged candidates; changing the router or candidate set invalidates it.

A model-name mismatch, rewritten prefix/response, missing/zero usage,
interrupted response or missing receipt falls back to the existing
full-history estimator. A failed/cancelled request deliberately invalidates
previous receipts until a fresh completion. This is a conservative policy,
not evidence an unchanged earlier prefix became wrong. It sacrifices accuracy
on interrupted turns even when no partial response was retained; a retained
partial response already forces fallback through newest-response selection.
Pre-existing sessions without receipts remain valid but initially use
estimates until a completed request establishes a new anchor.

Compaction retains tail messages verbatim, including old usage. Prefix
validation rejects those stale receipts so the next request does not compact
again solely because of pre-compaction usage -- fingerprinting the *shorter*
post-compaction prefix can never match a receipt stamped against the longer
pre-compaction one, so the fallback estimator naturally takes over instead of
a special case. Pruning, sanitizing tool-call IDs, response clamping and the
built-in foreign-thinking strip similarly invalidate modified prefixes.
Request-only plugin transforms that differ from persisted history
deliberately do not establish an anchor. Accounting is an observed prefix
plus an approximate delta, not an exact prediction of the next wire request.

## Continuations and billing

In pydantic-ai 2.51.0 one logical request can include multiple HTTP segments,
including Anthropic `pause_turn` and OpenAI background responses. Accumulated
or fresh-generation replacement segments can produce cumulative usage; same-ID
polling replaces rather than sums usage. Final response fields do not reliably
identify every continued chain. A later appended message does not invalidate
an unchanged receipt prefix, so mistaking cumulative billing for one measured
prompt could keep overstating context until a fresh response replaces it.

The request hook wraps the model in `_ContinuationObserver`, observing
`continuation_delay` on suspended responses before the framework merges them.
It declines to stamp any continued response, including same-ID polling, while
preserving provider usage and billing. This uses the request-model swap seam
also used by framework durable-execution capabilities; no usage is fabricated.
See `_model_message_transform.py` for the local mechanism and continuation
regression tests for the framework paths.

## Rollout

No feature flag: the shared number corrects accounting for every provider.
Expect reported context usage to rise for conversations where the previous
character-based heuristic undercounted the active model's tokenizer (for
example, cache-heavy requests where cached tokens still count toward the
window). This change does not itself alter any model's configured context
length -- it only measures what's actually being spent against it.

Draft release note:

> Context indicators now use the API's reported prompt tokens for unchanged
> conversation history, estimating only newly added content. Counts may look
> higher than before: the previous character heuristic undercounted some
> models, especially with heavy prompt caching. Compaction and the context
> indicator now share the same total, so they can't disagree with each other.

## Retired plugin follow-up

The in-tree token-ratio learner plugin is unnecessary once accounting anchors
to real API usage, so it has no replacement here. An older installed
`code_puppy_core_plugins` bundle may still advertise that plugin's entry
point; the plugin loader blocks it unconditionally so its startup
monkeypatches can't override the shared fallback estimator. The installed
package itself is left untouched by this change -- removing the plugin
source, its tests and its docs is tracked as a separate, independently
reviewable change to `code_puppy_core_plugins`. No stored cross-session
learned ratios are consumed by this change.
