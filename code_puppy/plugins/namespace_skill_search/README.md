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
4. **Flat list turned off** — on first load, the plugin calls
   `set_frontmatter_in_system_prompt(False)` via the public config API
   (`code_puppy.plugins.agent_skills.config`) so the built-in per-skill
   flat list doesn't also render alongside the namespace directory. This
   is a one-time flip; if a user re-enables it later with
   `/skills frontmatter on`, we don't fight that choice on next launch.

## What we deliberately avoided

- **No `get_model_system_prompt` callback.** That phase is
  last-write-wins across plugins — `model_utils.prepare_prompt_for_model`
  threads augmenter results through sequentially and the *last* callback
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
