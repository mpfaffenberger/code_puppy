# Skills System

> Part of the `code-puppy-agent` skill. Read this when working with
> skill discovery/activation, or extending how skills are presented to
> the model. See `SKILL.md` for the overview and the full reference map.

---

## How skills work

A skill is a directory containing a `SKILL.md` with YAML frontmatter
(`name`, `description`, optional `version`, `author`, `tags`) and
markdown body. The body is the instruction set loaded into context when
the skill is activated.

## Skill discovery (`plugins/agent_skills/discovery.py`)

Scans these directories (first-discovered wins on name collision):
1. `~/.code_puppy/skills/`
2. `<CWD>/.code_puppy/skills/`
3. `<CWD>/skills/`
4. Plugin-registered skills (via `register_skills` callback)

## Skill activation flow

1. The model calls `activate_skill("skill-name")` or the user types
   `/<skill-name>`
2. The tool reads the full `SKILL.md` from disk
3. Content is injected into the model's context as a tool result
4. The model follows the instructions in its next response

Skills are **opt-in** — by default the model sees a one-line summary in
its system prompt (name + description) and must explicitly activate to
get full instructions. At small catalog sizes (a handful to a few dozen
skills) this flat list is fine. It stops scaling well before a few
hundred skills — see "Skill namespaces" below.

### Bundled resource files: filesystem skills vs. plugin-registered skills

`activate_skill` returns a `resources: List[str]` field listing files
bundled alongside `SKILL.md` (via `get_skill_resources()`), which the
model can then `read_file()` on demand instead of everything being
force-loaded on activation. This works cleanly for a **filesystem**
skill (a real directory under one of the scanned paths above) — any
sibling file just shows up.

It does **not** work the same way for a skill registered via the
`register_skills` callback with `skill_md_path` (like this skill,
`code-puppy-agent`, and `namespace_skill_search` originally considered
before dropping the idea): the discovery loader materializes only
`SKILL.md` itself into a cache directory (plus an optional `scripts_dir`
entry, and even that isn't surfaced through `get_skill_resources` since
it lands as a subdirectory, not a file). **If you want a plugin-owned
skill to reference sibling docs, put real repo paths in the SKILL.md
prose and let the model `read_file()` them directly** — don't rely on
the `resources` field to surface them. This document you're reading
right now is exactly that pattern: `SKILL.md` names this file by its
real path in the repo rather than expecting it to appear as a
`resources` entry.

## Managing skills

| Command | Effect |
|---------|--------|
| `/skills` | Interactive TUI menu |
| `/skills list` | Text list of all skills |
| `/skills enable` / `disable` | Toggle skills globally |
| `/skills frontmatter on/off` | Toggle skill summaries in system prompt |
| `/skills install` | Browse & install from remote catalog |

---

## Skill namespaces (large catalogs)

The **`namespace_skill_search`** builtin plugin
(`code_puppy/plugins/namespace_skill_search/`) addresses the
flat-list-doesn't-scale problem above. It's the reference
implementation to look at if you're extending how skills are surfaced
to the model, or building something in the same spirit for another
large catalog (tools, MCP servers, etc.).

**Shape:** groups skills into **namespaces** — each skill's namespace is
its first `tags:` entry (untagged skills fall back to a `General`
namespace) — and replaces the flat per-skill system-prompt list with a
compact namespace directory, plus a new `browse_skill_namespace` tool
with three modes (no-args directory listing, `namespace=` drill-down,
`query=` keyword search across everything). This mirrors OpenAI's
shipped `tool_search` + namespace-grouping pattern and Anthropic's
shipped Tool Search Tool, reimplemented in a model-agnostic way (no
provider-specific request fields) using only Code Puppy's existing
plugin hooks.

**User-facing docs:** `docs/AGENT_SKILLS.md` → "Skill Namespaces (Large
Catalogs)" section — what changes automatically, the tool's three
modes with examples, and how to opt back out
(`/plugins disable namespace_skill_search` + `/skills frontmatter on`).

**Design rationale + what was deliberately not built:**
`code_puppy/plugins/namespace_skill_search/README.md` — full writeup of
what was copied from OpenAI/Anthropic, why namespace-per-first-tag was
chosen over a vector DB or a deep multi-level tree, and the two hook-
system gotchas it was built to avoid (see `PLUGINS_AND_CALLBACKS.md` in
this reference set for those gotchas explained in general terms, not
tied to this one plugin).

**Implementation details worth knowing if you're extending it:**
- Namespace grouping is **case-insensitive at build time** — skills
  tagged `finance`/`Finance`/`FINANCE` merge into one namespace, keyed
  by first-seen casing. This isn't optional; the tool's `namespace=`
  lookup is case-insensitive, so case-sensitive grouping would let two
  namespaces silently fragment while looking like a single one from the
  tool's perspective.
- A blank/whitespace-only `query` means "no filter," not "match
  nothing" — a naive `any(term in haystack for term in
  query.lower().split())` degrades to `any([])` (`False`) for every
  skill on an empty query, which is a genuinely easy trap to fall into
  with keyword-filter code in general, not specific to this plugin.
- Duplicate skill names across namespaces are flagged in the directory
  output (not deduped or resolved) — `activate_skill(name)` has no way
  to disambiguate between two skills sharing a name, and that's an
  `agent_skills`-level gap this plugin surfaces more visibly rather than
  causes.

## When to reach for `list_or_search_skills` / `activate_skill` vs. `browse_skill_namespace`

Both exist simultaneously and are not mutually exclusive:
- `list_or_search_skills` — the original, flat, always-available tool.
  Fine for small catalogs or when you already roughly know the skill
  name.
- `browse_skill_namespace` — better when the catalog is large enough
  that `namespace_skill_search` has replaced the flat prompt block with
  a namespace directory, and you want to browse by domain or search
  across everything without scanning a huge flat list yourself.

Either way, the terminal step is the same: `activate_skill(name)` to
load the full instructions.
