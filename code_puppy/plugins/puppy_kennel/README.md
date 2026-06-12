# Puppy Kennel

Local-first memory for Code Puppy. Inspired by [MemKennel](https://github.com/MemKennel/memkennel)'s
wings → rooms → drawers model, but backed by **SQLite + FTS5** instead of
ChromaDB. No daemon, no API key, no cloud, multi-process safe via WAL mode.

## Why not just use MemKennel / Mem0 / Chroma?

We looked. Hard. The summary:

- **MemKennel** — Beautiful concepts, but ChromaDB's embedded `PersistentClient`
  is not safe across multiple processes hitting the same kennel. Upstream issues
  #1581, #948, #1646 are all flavors of "we need a daemon to make this work."
  We run 20 puppies sometimes. A daemon is not in the cards.
- **Mem0** — Open issue #4892: "concurrent AsyncMemory writes corrupt Qdrant
  HNSW index." Same disease. Also requires an LLM API key just to *store*
  memories, and phones home to PostHog by default. No thanks.
- **ChromaDB / Qdrant / Faiss directly** — All ANN-index-backed; all multi-
  process-hostile in embedded mode. ANN is only worth the trouble at >100K
  vectors. We're nowhere near that.

SQLite has had production-grade full-text search (FTS5, BM25-ranked) since
2015 and has been multi-process safe via WAL since 2010. We do not need
anything fancier.

## Wing namespacing — compartmentalization without isolation walls

Three wing namespaces, all in one shared kennel:

| Wing | Example | Purpose |
|---|---|---|
| `repo:<path>` | `repo:/Users/mike/code/foo` | Project memory, shared across agents |
| `agent:<name>` | `agent:code-puppy` | Per-agent diary, private by convention |
| `user:default` | `user:default` | Cross-cutting user preferences |

Privacy is by convention, not encryption. If you need cryptographic
isolation for a sensitive-data agent, run that agent with
`PUPPY_KENNEL_ROOT` pointed at a private directory.

## What it does today

**Phase 1 — passive memory:**
- **`load_prompt`** — injects a tiered, budget-aware recall block (see
  [the packer](#the-packer) below) into the system prompt.
- **`agent_run_end`** — writes the agent's response to a single drawer
  in the current ``repo:<cwd>`` wing.

## Wing semantics (Phase 5)

The three wings model **who the memory is for**, not who wrote it:

| Wing | Active when... | Filled by... |
|---|---|---|
| ``user:default`` | always (cross-cutting) | explicit ``kennel_remember(wing="user")`` only |
| ``repo:<cwd>`` | cwd matches | autosave + ``kennel_remember(wing="repo")`` (default) |
| ``agent:<name>`` | selected agent matches | explicit ``kennel_remember(wing="agent")`` only |

Autosave goes **only** to the repo wing — every response is "a
conversation that happened in this project," which is genuinely
repo-scoped. The agent wing is reserved for deliberate cross-project
reflections; ``user:default`` is for facts about the human.

This kills the previous dual-write design (where each response wrote
twice, once per wing). Search-time dedup is still in place for any
legacy duplicates and for content the agent explicitly mirrors into a
second wing.

## The packer

The recall block is assembled by `packer.py` under a configurable token
budget. Three priority classes, no LLM, no embeddings:

| Tier | Source | Quota (default) | Why |
|---|---|---|---|
| **P0** User Preferences | `user:default` wing, any role | ~30% | Short, durable, pervasive ('Mike hates emojis') |
| **P1** Project Decisions | `repo:<cwd>` wing, `role='note'` | ~30% | Sticky writes from `kennel_remember` — highest signal-to-token ratio |
| **P2** Recent Context | `repo:<cwd>` wing, `role='assistant'` | remainder | Orientation, freshness |

Drawers below `PUPPY_KENNEL_MIN_DRAWER_CHARS` (default 80) are skipped
as noise. Token estimation uses the well-known 1-token ≈ 4-chars
heuristic — accurate to ±20%, zero deps.

**Config knobs:**

| Env var | Default | Effect |
|---|---|---|
| `PUPPY_KENNEL_PROMPT_BUDGET` | `1500` | Total token budget for the block |
| `PUPPY_KENNEL_USER_PREFS_QUOTA` | `0.30` | P0 fraction |
| `PUPPY_KENNEL_STICKY_QUOTA` | `0.30` | P1 fraction |
| `PUPPY_KENNEL_MIN_DRAWER_CHARS` | `80` | Noise filter |

**Phase 2 — active tooling:**

Five agent-callable tools registered via ``register_tools``:

| Tool | Purpose |
|---|---|
| `kennel_recall(query, wing?, top_k=5, scope=?)` | BM25 search across wings, deduplicated. |
| `kennel_remember(content, wing="repo", room="notes")` | Explicit verbatim write to a chosen wing. |
| `kennel_recent(wing?, top_k=5, scope=?)` | Time-ordered drawer browsing (no query needed). |
| `kennel_list_wings()` | Discover all wings + drawer counts. |
| `kennel_stats()` | Kennel-wide totals + on-disk size. |

Wing shortcuts accepted by every tool: ``"repo"`` (current project,
default for writes), ``"agent"`` (this agent's diary), ``"user"``
(cross-cutting preferences), or an explicit wing name like
``"team:platform"``.

Scope shortcuts for multi-wing reads: ``"default"`` (repo+agent+user),
``"repo"``, ``"agent"``, ``"user"``, ``"all"``.

Plus a **`/kennel`** slash command suite for humans:

| Command | What it does |
|---|---|
| `/kennel` | stats + recent context preview |
| `/kennel search <q>` | BM25 search across default scope |
| `/kennel wings` | list wings + drawer counts |
| `/kennel stats` | DB size, totals, current enabled state |
| `/kennel status` | is memory currently on or off? |
| `/kennel enable` (or `on`) | turn memory on at runtime |
| `/kennel disable` (or `off`) | turn memory off at runtime (drawers preserved) |
| `/kennel help` | usage hint |

## Enable / disable

The plugin is **enabled by default**. Flip it with the slash commands:

- ``/kennel disable`` (or ``/kennel off``) — turn memory off
- ``/kennel enable`` (or ``/kennel on``) — turn memory back on

State is persisted to ``puppy.cfg`` under ``kennel_enabled`` and read on
every callback, so the toggle is live — no restart needed, and the
front end can read or write the same value.

**When disabled:**

- ``load_prompt`` returns ``None`` (no recall block in system prompt)
- ``agent_run_end`` is a no-op (nothing recorded)
- Agent-facing tools return a friendly ``error`` field explaining memory is off
- **The ``/kennel`` slash suite stays available** — ``/kennel stats``,
  ``/kennel wings``, ``/kennel search`` all still work so the operator
  can see what's stored, and ``/kennel enable`` is always reachable to
  turn it back on.

## Known tech debt

- **Legacy duplicates.** Kennels that pre-date Phase 5 may contain
  dual-written drawers (same content in repo + agent wings).
  ``search_drawers_multi`` deduplicates by content so reads are sane;
  they'll age out naturally once retention/pruning ships.

## What's still coming

- `stream_event` hook to also capture user input (not just agent output).
- Optional `fastembed` semantic re-ranking on top of FTS5 BM25.
- `/kennel prune` retention policy.

## Environment

| Variable | Default | Effect |
|---|---|---|
| `PUPPY_KENNEL_ROOT` | `~/.code_puppy/kennel` | Where the SQLite file lives |
| `PUPPY_KENNEL_PASSIVE_LIMIT` | `5` | Drawers surfaced in passive recall |
| `PUPPY_KENNEL_MAX_DRAWER_CHARS` | `32000` | Cap on stored drawer size |

## puppy.cfg keys

| Key | Default | Effect |
|---|---|---|
| `kennel_enabled` | unset → enabled | Single source of truth for the on/off toggle. Set to `false`/`0`/`no`/`off` (case-insensitive) to disable. Anything else — missing, blank, or garbage — leaves the kennel on. Flipped live by `/kennel enable` and `/kennel disable`. |

## How tools reach the agent

Code Puppy agents expose a hardcoded ``get_available_tools()`` list. To get
plugin tools onto that list without editing every agent, this plugin uses
the ``register_agent_tools`` hook — a small piece of core architecture
added alongside this plugin specifically to avoid that pattern.

``register_tools`` defines tools and drops them into ``TOOL_REGISTRY``;
``register_agent_tools`` says *which* tools to advertise to *which* agent.
The puppy_kennel plugin always returns all five tool names regardless of
agent — memory is universally useful. Other plugins can scope per-agent by
branching on the ``agent_name`` argument.

## Files

```
puppy_kennel/
├── __init__.py
├── config.py              # paths, env vars, limits
├── schema.py              # CREATE TABLE + PRAGMA strings
├── kennel.py              # storage layer (wings, rooms, drawers)
├── wings.py               # wing-naming convention
├── recorder.py            # agent_run_end -> drawer
├── retriever.py           # load_prompt -> recall block
├── register_callbacks.py  # hook wiring (entry point)
└── README.md              # you are here
```

All files under 200 lines, every concern its own module, no SQL leaking
outside `kennel.py`. SOLID, DRY, Zen-of-Python-compatible. Cheers.
