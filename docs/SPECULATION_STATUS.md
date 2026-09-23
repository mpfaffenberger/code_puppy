# Speculative Puppy status row

Speculative Puppy shows session counters in a pinned terminal row instead of
printing the streamed `run_code` source or a final code panel. Switching to
another agent hides the row; switching back keeps the session totals.

```
spec  29 hits · 0 misses · 0 wasted    saved ≥ 7.0s   spec 0.5s · eager 6.5s
```

The label uses the agent accent. Counts light up only when non-zero (hits
green, misses yellow, wasted red); the headline total is bold green once
anything has been saved, and the breakdown stays muted. Only palette slots
are used, so `/theme` recolors the row.

- **Hits:** sandbox calls that adopted a speculative launch.
- **Misses:** speculation-eligible calls that ran without a matching launch.
- **Wasted:** launches reported by the harness as discarded without a claim.
- **saved ≥:** spec plus eager, below. Both are lower bounds, so the sum is
  too.
- **spec:** the sum of fully hidden call durations, in seconds. This
  is a lower bound on summed call latency hidden by speculation, not elapsed
  wall-clock time saved. Concurrent calls can overlap. Partial hits still
  count as hits, but their timing is excluded because the harness does not
  expose how long the caller waited.
- **eager:** summed time spent in non-speculative sandbox tool calls
  while `run_code` arguments were still streaming. A call that extends past
  generation contributes only its overlapping portion. The counter updates
  when the snippet completes successfully, and excludes restarted, rejected,
  or cancelled snippets. Speculative launches are excluded to prevent
  double-counting. Like speculative savings, this is hidden tool latency,
  not wall-clock speedup; concurrent calls can overlap. Pure sandbox Python
  execution and direct filesystem access are not timed.

Eager timing uses the framework's execution and stream-event hooks, so no SDK
patch or dependency upgrade is needed.

## Requirements for any runway at all

- **Streamed tool names must be `run_code`.** Claude Code OAuth models call
  `cp_run_code` on the wire and Code Puppy only un-prefixes at dispatch, which
  is too late for the harness stream watchers. `StreamedToolNameNormalizer`
  (registered with the speculative capability) rewrites the streamed part
  events so the eager pump and speculation launcher engage.
- **Arguments must actually stream.** By default Anthropic buffers a tool
  call's whole input and flushes it in one burst at the end, leaving under
  100 ms of runway. `ClaudeCacheAsyncClient` sends the
  `fine-grained-tool-streaming-2025-05-14` beta on every Claude Code request
  so arguments stream as they are generated; measured on the same snippet it
  turns a 39 ms eager saving into the full 2 s a sleeping shell call spent
  under generation. Literal read-only calls normally add
to speculative savings. To exercise eager savings, use a non-speculative
sandbox tool, or a read whose arguments are computed inside the snippet.
The eager scanner needs a following complete statement before it releases
the previous one; a single final statement executes at normal dispatch.

Counters reflect the events the harness delivers. Launches cancelled after
its event stream closes are not reported as wasted by the released harness.
No live stats are printed to redirected output or headless transcripts.
