# Cold-start perf benchmarks

Scripts used to measure the impact of PR #681 (messaging↔tools decoupling).
Kept in-repo so future perf work has a starting point and so cited numbers
are verifiably reproducible.

## Scripts

### `bench_messaging_only.py`

Measures the cost of a single `import code_puppy.messaging` in a fresh
subprocess. This is the tightest, most honest number for the messaging
package's own transitive-import cost.

```bash
python perf/bench/bench_messaging_only.py
```

**Baseline (main, commit 25266787):** ~386ms wall, 1017 new modules.
**After PR #681:** ~147ms wall, 392 new modules.
**Delta: −239ms (−62%), −625 modules (−61%).** Reproducible run-to-run.

### `bench_full_cold_start.py`

Simulates the plugin-discovery phase of a real Code Puppy launch: registers
all 51 built-in plugins in one Python process, reports wall-time
distribution across 3 warmup + 15 measurement runs per repo, and asserts
plugin-load parity between the two trees.

```bash
python perf/bench/bench_full_cold_start.py
```

Prints a per-tree median / stdev / min / max table and a **noise-floor
verdict**: if `|Δmedian| < combined stdev`, the delta is inside run-to-run
jitter and should NOT be headlined. This is how the round-2 review caught
the (retracted) −12.4% cache-warmth artifact in PR #681.

## Editing before running

Both scripts hard-code `MAIN` / `WORK` repo paths and the venv Python at
the top of the file. Adjust for your machine before running against your
own before/after pair.

## Adding new benchmarks

Prefer the same shape as `bench_full_cold_start.py`:

1. **Warmup runs discarded** (page cache, JIT caches).
2. **N ≥ 7 measurement runs**, ideally 15+, in fresh subprocesses.
3. **Report the distribution** (median + stdev + min + max), not just the mean.
4. **Compute a noise-floor verdict** when comparing two trees. If the delta
   is smaller than the combined stddev, say so out loud — don't headline
   noise as a win.
5. **Parity assertions** where relevant (e.g. same plugin set loaded).
