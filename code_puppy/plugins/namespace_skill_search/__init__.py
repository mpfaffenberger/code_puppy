"""namespace_skill_search — OpenAI-style namespace + on-demand search for skills.

Model-agnostic reimplementation of the pattern OpenAI ships as its
`tool_search` + namespaces feature. OpenAI's version relies on a
model-provider-specific `defer_loading` API flag; this plugin gets the same
effect — one grouping layer + on-demand search instead of a flat, unranked
skill list baked into every system prompt — using only Code Puppy's
model-agnostic plugin hooks, so it behaves identically on Claude, GPT,
Gemini, or any custom endpoint wired through `ModelFactory`.

See README.md in this directory for the full design rationale, including
what frontier labs (Anthropic, OpenAI, Google) actually ship in production
vs. what's academic-only, and why this plugin copies OpenAI's shape
specifically.
"""
