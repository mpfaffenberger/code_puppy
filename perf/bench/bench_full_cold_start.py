"""Realistic full-plugin cold-start bench with proper distribution reporting.

Runs plugin discovery in one Python process per subprocess invocation.
Discards warmup runs, does many measurement runs, and reports median +
stddev + min + max so cache-warmth artifacts stand out. Asserts both
trees loaded the same set of plugins on every run so silent plugin-load
failures cannot skew the comparison. Prints an explicit noise-floor
verdict so it's obvious when the delta is inside run-to-run jitter.

Usage
-----
Compare two checkouts (typically ``main`` vs a feature branch)::

    python perf/bench/bench_full_cold_start.py \\
        --before /path/to/checkout-before \\
        --after  /path/to/checkout-after

Optional flags:

    --runs N       measurement runs per tree (default 15)
    --warmup N     discarded warmup runs per tree (default 3)
    --python PATH  Python interpreter to spawn subprocesses with
                   (default: the interpreter running this script)

Exit codes:
    0  benchmark completed
    2  plugin-load parity violation between the two trees
    3  insufficient successful samples (see stderr)
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

SNIPPET = """
import os, sys, time, json
os.environ['NO_VERSION_UPDATE'] = '1'
sys.path.insert(0, {repo!r})
t0 = time.perf_counter()
sys.stdout = open(os.devnull, 'w')
from code_puppy.callbacks import register_callback  # noqa
from code_puppy import plugins as plugins_pkg  # noqa
from pathlib import Path
PLUGINS_DIR = Path({repo!r}) / 'code_puppy' / 'plugins'
loaded = []
failed = []
for p in sorted(PLUGINS_DIR.iterdir()):
    if not p.is_dir():
        continue
    if not (p / 'register_callbacks.py').exists():
        continue
    try:
        __import__(f'code_puppy.plugins.{{p.name}}.register_callbacks')
        loaded.append(p.name)
    except Exception as e:
        failed.append((p.name, type(e).__name__))
dt = time.perf_counter() - t0
n_mod = len(sys.modules)
sys.stdout = sys.__stdout__
print(json.dumps({{
    'wall_ms': round(dt * 1000, 2),
    'n_modules': n_mod,
    'loaded': loaded,
    'failed': failed,
}}))
"""


def run(python: str, repo: str, n: int) -> list[dict]:
    results: list[dict] = []
    for _ in range(n):
        r = subprocess.run(
            [python, "-c", SNIPPET.format(repo=repo)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            print(
                f"[bench] subprocess failed (repo={repo}): {r.stderr[-300:]}",
                file=sys.stderr,
            )
            continue
        for line in reversed(r.stdout.strip().splitlines()):
            try:
                results.append(json.loads(line))
                break
            except json.JSONDecodeError:
                continue
    return results


def stats(rows: list[dict]) -> dict:
    t = [r["wall_ms"] for r in rows]
    m = [r["n_modules"] for r in rows]
    return {
        "mean_ms": statistics.mean(t),
        "median_ms": statistics.median(t),
        "stdev_ms": statistics.stdev(t),
        "min_ms": min(t),
        "max_ms": max(t),
        "modules": statistics.median(m),
    }


def fmt(s: dict) -> str:
    return (
        f"mean {s['mean_ms']:>7.1f}ms  "
        f"median {s['median_ms']:>7.1f}ms  "
        f"stdev {s['stdev_ms']:>5.1f}ms  "
        f"min {s['min_ms']:>7.1f}ms  "
        f"max {s['max_ms']:>7.1f}ms  "
        f"modules {s['modules']:>6.0f}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--before",
        required=True,
        type=Path,
        help="path to the baseline code_puppy checkout",
    )
    p.add_argument(
        "--after",
        required=True,
        type=Path,
        help="path to the candidate code_puppy checkout",
    )
    p.add_argument("--runs", type=int, default=15, help="measurement runs per tree")
    p.add_argument(
        "--warmup", type=int, default=3, help="warmup runs per tree (discarded)"
    )
    p.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to spawn subprocesses (default: sys.executable)",
    )
    args = p.parse_args()

    before = args.before.resolve()
    after = args.after.resolve()
    for label, path in (("--before", before), ("--after", after)):
        if not (path / "code_puppy").is_dir():
            print(
                f"[bench] {label}: {path} does not look like a code_puppy checkout "
                "(no code_puppy/ subdir)",
                file=sys.stderr,
            )
            return 2

    print(f"[bench] python:  {args.python}")
    print(f"[bench] before:  {before}")
    print(f"[bench] after:   {after}")
    print(f"[bench] warmup={args.warmup}, runs={args.runs}\n")

    print(f"Warmup: {args.warmup} runs per repo (discarded)")
    run(args.python, str(before), n=args.warmup)
    run(args.python, str(after), n=args.warmup)

    print(f"Measuring: {args.runs} runs per repo\n")
    before_rows = run(args.python, str(before), n=args.runs)
    after_rows = run(args.python, str(after), n=args.runs)

    # --- Sample-count guard: fail loud if too many subprocesses errored ---
    if len(before_rows) < 2 or len(after_rows) < 2:
        print(
            f"[bench] insufficient samples "
            f"(before={len(before_rows)}, after={len(after_rows)}); "
            f"stddev is undefined with <2 runs and the noise-floor verdict "
            f"would be meaningless.",
            file=sys.stderr,
        )
        return 3

    # --- Parity assertion (fail loud if plugin-load sets differ) ---
    before_loaded = set(before_rows[0]["loaded"])
    after_loaded = set(after_rows[0]["loaded"])
    before_only = before_loaded - after_loaded
    after_only = after_loaded - before_loaded
    if before_only or after_only:
        print("!!! PLUGIN-LOAD PARITY VIOLATION !!!", file=sys.stderr)
        print(f"  loaded only in BEFORE: {sorted(before_only)}", file=sys.stderr)
        print(f"  loaded only in AFTER:  {sorted(after_only)}", file=sys.stderr)
        return 2

    # Intra-tree drift check: every run must load the same set as run 0.
    for label, rows in (("BEFORE", before_rows), ("AFTER", after_rows)):
        baseline = set(rows[0]["loaded"])
        for i, r in enumerate(rows):
            if set(r["loaded"]) != baseline:
                print(
                    f"!!! {label} run {i} loaded a different plugin set than run 0",
                    file=sys.stderr,
                )
                return 2

    n_loaded = len(before_loaded)
    print(
        f"Plugin-load parity: both trees loaded the SAME {n_loaded} plugins "
        f"on every run\n"
    )

    bs = stats(before_rows)
    as_ = stats(after_rows)

    print(f"BEFORE : {fmt(bs)}")
    print(f"AFTER  : {fmt(as_)}")

    d_mean = as_["mean_ms"] - bs["mean_ms"]
    d_median = as_["median_ms"] - bs["median_ms"]
    d_min = as_["min_ms"] - bs["min_ms"]

    print(f"\nDelta mean   : {d_mean:+.1f}ms  ({100 * d_mean / bs['mean_ms']:+.2f}%)")
    print(
        f"Delta median : {d_median:+.1f}ms  ({100 * d_median / bs['median_ms']:+.2f}%)"
    )
    print(f"Delta min    : {d_min:+.1f}ms  ({100 * d_min / bs['min_ms']:+.2f}%)")

    combined_stdev = (bs["stdev_ms"] ** 2 + as_["stdev_ms"] ** 2) ** 0.5
    print(f"\nCombined stdev: {combined_stdev:.1f}ms")
    if abs(d_median) < combined_stdev:
        print(
            "VERDICT: |delta| < combined stdev  --> "
            "delta is INSIDE the noise floor. Do not headline this number."
        )
    else:
        print(
            "VERDICT: |delta| >= combined stdev  --> "
            "delta is above the noise floor. Report it with the stddev."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
