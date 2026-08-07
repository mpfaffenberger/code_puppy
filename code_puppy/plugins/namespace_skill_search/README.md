# namespace_skill_search

Model-agnostic reimplementation of OpenAI's namespace + `tool_search`
pattern, applied to Code Puppy's skill catalog.

## Why this exists

Frontier labs converge on one shape for large tool/skill catalogs:
**one grouping layer + on-demand search**, instead of a flat list of
every item injected into the system prompt upfront.

- Anthropic's shipped Tool Search Tool: flat on-demand search,
  `defer_loading: true`, results injected at end of context to preserve
  prompt caching. ~85% token reduction, measurable accuracy gains on
  internal MCP evals ([Anthropic engineering blog, Nov 2025](https://www.anthropic.com/engineering/advanced-tool-use)).
  Note: our `load_prompt` fragment lands earlier in the assembled prompt
  (layer 2 of `base_agent.py::get_full_system_prompt`) than the built-in
  flat skill list it replaces did (layer 6, dead last). We prioritized
  additive-safety (`load_prompt` can't collide with another plugin's
  fragment; `get_model_system_prompt` can) over exactly matching
  Anthropic's end-of-context caching position. If cache-hit rate on the
  namespace block ever matters in practice, moving it later is a
  follow-up, not a redesign.
- OpenAI's shipped `tool_search`: same on-demand mechanic, PLUS an
  explicit **namespace** grouping layer above it
  (`{"type": "namespace", "name": "crm", "tools": [...]}`), because
  "our models have primarily been trained to search those surfaces" —
  namespaces outperform bare deferred functions in their own docs
  ([OpenAI tool-search guide](https://developers.openai.com/api/docs/guides/tools-tool-search)).
  They recommend keeping each namespace under 10 functions.
- Neither ships a deep multi-level tree. One grouping layer is the norm;
  true hierarchical (server -> tool) routing exists mainly in academic
  work (e.g. MCP-Zero, arXiv:2506.01056), not shipped production
  features.

## What we copied, and why

We copied OpenAI's shape (namespace + search) rather than Anthropic's
(flat search only), because the namespace layer is a genuine win once a
catalog gets into the hundreds of items. But OpenAI's mechanism depends
on a model-specific API flag (`defer_loading`) that only exists for
their own models. This plugin gets the same effect through Code Puppy's
model-agnostic plugin hooks instead, so it behaves identically on
Claude, GPT, Gemini, or any custom endpoint wired through
`ModelFactory` — no provider-specific request fields required.

## How it works

1. **Namespace derivation** (`namespaces.py`) — a skill's namespace is
   its first `tags:` entry (untagged skills land in `General`). No new
   frontmatter field, no migration of existing `SKILL.md` files required.
2. **Compact directory injection** (`load_prompt` hook) — instead of one
   line per skill (the built-in behavior when
   `frontmatter_in_system_prompt` is on), the system prompt gets one
   line per *namespace* with a 3-item preview and a count. `load_prompt`
   fragments from every plugin are newline-joined by `base_agent.py`, so
   this is safely additive — it cannot collide with or overwrite another
   plugin's fragment the way `get_model_system_prompt` callbacks can
   (see "What we deliberately avoided" below).
3. **Drill-down tool** (`browse_skill_namespace`) — one tool, three modes:
   - no args -> namespace directory (same content as the prompt block)
   - `namespace="X"` -> every skill in that namespace
   - `query="..."` -> keyword search across all namespaces
4. **Flat list turned off** — the first time this plugin ever starts up
   (via a `startup` callback, not an import-time side effect — see
   "What we deliberately avoided" below), it calls
   `set_frontmatter_in_system_prompt(False)` via the public config API
   (`code_puppy.plugins.agent_skills.config`) so the built-in per-skill
   flat list doesn't also render alongside the namespace directory.

   **This is a real, persisted config write, not an in-memory toggle.**
   Enabling this plugin once permanently sets
   `frontmatter_in_system_prompt=false` in `puppy.cfg`. A dedicated
   marker key (`namespace_skill_search_frontmatter_migrated`) records
   that the flip already happened, so if you re-enable it afterwards
   with `/skills frontmatter on`, we never touch the flag again — your
   choice sticks across restarts. But if you disable or remove this
   plugin entirely, the flag stays `false`; nothing restores the flat
   list automatically. Run `/skills frontmatter on` yourself if you want
   it back.

## What we deliberately avoided

- **No config mutation at import time.** The `frontmatter_in_system_prompt`
  flip runs inside a `register_callback("startup", ...)` handler (matching
  the same pattern as `code_puppy/plugins/theme`'s
  `_apply_default_theme_on_first_run`), not as top-level code in
  `register_callbacks.py`. Import-time disk writes are a landmine: they
  fire on every import (including test collection), can't be unit-tested
  without `importlib.reload` gymnastics, and race with plugin load order
  in ways a callback doesn't. A dedicated migration marker (see above)
  makes the one-time-ness explicit and testable instead of relying on
  "only flip it when the shared flag is currently True" as the sole
  signal.
- **No `get_model_system_prompt` callback.** That phase is
  last-write-wins across plugins — `model_utils.prepare_prompt_for_model`
  threads augmenter results sequentially and the *last* callback
  processed wins on any key both callbacks set. A second plugin
  registering on that phase risks silently clobbering the built-in
  `agent_skills` plugin's contribution. `load_prompt` avoids that
  failure mode entirely by design (simple concatenation, no merge
  conflicts possible).
- **No vector DB / embeddings.** Namespace + substring search is enough
  at this scale; see Anthropic's own `tool_search_with_embeddings.ipynb`
  cookbook, which only recommends embeddings above ~100 tools with high
  semantic overlap between items.
- **No deep multi-level tree** (namespace -> subnamespace -> skill). No
  frontier lab ships that in production; one grouping layer is the norm.
- **No new tool duplicating `list_or_search_skills`.** That tool still
  exists and still works for flat queries; `browse_skill_namespace` is
  additive, not a replacement.

## Sizing signal

OpenAI's own docs recommend keeping each namespace under 10 functions
for best token efficiency. We don't enforce this (skills aren't ours to
re-tag), but the directory block flags any namespace over that
threshold as `oversized namespace` so it's visible instead of silent.
