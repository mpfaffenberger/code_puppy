# Cold-start perf benchmarks

Scripts used to measure the impact of PR #681 (messaging↔tools decoupling).
Kept in-repo so future perf work has a starting point and so cited numbers
are verifiably reproducible.

## Common invocation

Both scripts compare two Code Puppy checkouts and take the same core args:

```bash
python perf/bench/<script>.py \
    --before /path/to/baseline-checkout \
    --after  /path/to/candidate-checkout
```

Optional:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--runs N` | script-specific | measurement runs per tree |
| `--warmup N` | script-specific | warmup runs per tree (discarded) |
| `--python PATH` | `sys.executable` | Python used for subprocesses |

Whichever Python you point at (or `sys.executable` by default) needs to
be able to `import code_puppy` from *each* of the two trees — usually
a venv with Code Puppy's dependencies installed. The scripts don't
install anything and don't modify the checkouts.

## Scripts

### `bench_messaging_only.py`

Measures the cost of a single `import code_puppy.messaging` in a fresh
subprocess. Tightest, most honest number for the messaging package's
own transitive-import cost.

Defaults: `--runs 7`, `--warmup 1`.

```bash
python perf/bench/bench_messaging_only.py \
    --before ../code_puppy-oss \
    --after  .
```

Output format:

```
import code_puppy.messaging  (7 fresh subprocesses each)

           wall (mean)     wall (min)    new_modules
-------------------------------------------------------
BEFORE          386.0ms        384.5ms         1017
AFTER           147.1ms        146.7ms          392

Delta wall (mean): -238.9ms  (-61.9%)
Delta modules:     -625  (-61.5%)
```

### `bench_full_cold_start.py`

Simulates the plugin-discovery phase of a real Code Puppy launch:
registers all built-in plugins in one Python process per subprocess,
reports the wall-time **distribution** across warmup + measurement
runs, and asserts plugin-load parity between the two trees.

Defaults: `--runs 15`, `--warmup 3`.

```bash
python perf/bench/bench_full_cold_start.py \
    --before ../code_puppy-oss \
    --after  .
```

Prints a per-tree median / stdev / min / max table and a
**noise-floor verdict**: if `|Δmedian| < combined stdev`, the delta is
inside run-to-run jitter and should NOT be headlined. This is how the
adversarial round-2 review of PR #681 caught the (retracted) −12.4%
cache-warmth artifact.

Exit codes:

- `0` — benchmark completed
- `2` — plugin-load parity violation (different plugins loaded across trees,
  or plugins loaded inconsistently within a tree)
- `3` — insufficient successful samples (see stderr)

## Adding new benchmarks

Prefer the same shape as `bench_full_cold_start.py`:

1. **Warmup runs discarded** — page cache, JIT caches, filesystem caches.
2. **N ≥ 7 measurement runs**, ideally 15+, in fresh subprocesses.
3. **Report the distribution** (median + stdev + min + max), not just the mean.
4. **Compute a noise-floor verdict** when comparing two trees. If the delta
   is smaller than the combined stddev, say so out loud — don't headline
   noise as a win.
5. **Parity assertions** where relevant (same plugin set loaded, same test
   set executed, same subprocess exit codes, etc).
6. **No hardcoded paths.** Take repo paths as `--before` / `--after` CLI
   args; take the Python interpreter as `--python` with `sys.executable`
   as the default.
