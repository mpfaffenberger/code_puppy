"""Realistic cold-start bench — round 2 with proper distribution reporting.

Runs plugin discovery in one Python process per subprocess invocation.
Discards warmup runs, does many measurement runs, and reports median +
stddev + min + max so cache-warmth artifacts stand out. Also asserts
that both trees loaded the same set of plugins so silent plugin-load
failures cannot skew the comparison.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys

VENV = "/Users/t0w0oqh/projects/code_puppy-oss/.venv/bin/python"

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


def run(repo: str, n: int) -> list[dict]:
    results = []
    for _ in range(n):
        r = subprocess.run(
            [VENV, "-c", SNIPPET.format(repo=repo)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            print(f"FAIL: {r.stderr[-300:]}", file=sys.stderr)
            continue
        for line in reversed(r.stdout.strip().splitlines()):
            try:
                results.append(json.loads(line))
                break
            except json.JSONDecodeError:
                continue
    return results


MAIN = "/Users/t0w0oqh/projects/code_puppy-oss"
WORK = "/Users/t0w0oqh/projects/code_puppy-oss/.worktrees/perf-messaging-tools-decouple"

WARMUPS = 3
N = 15

print(f"Warmup: {WARMUPS} runs per repo (discarded)")
run(MAIN, n=WARMUPS)
run(WORK, n=WARMUPS)

print(f"Measuring: {N} runs per repo\n")
main = run(MAIN, n=N)
work = run(WORK, n=N)

# --- Sample-count guard: fail loud if too many subprocesses errored ---
if len(main) < 2 or len(work) < 2:
    print(
        f"insufficient samples (main={len(main)}, work={len(work)}); "
        f"stddev is undefined with <2 runs and the noise-floor verdict "
        f"would be meaningless.",
        file=sys.stderr,
    )
    sys.exit(3)

# --- Parity assertion (fail loud if plugin-load sets differ) ---
main_loaded = set(main[0]["loaded"])
work_loaded = set(work[0]["loaded"])
main_only = main_loaded - work_loaded
work_only = work_loaded - main_loaded
if main_only or work_only:
    print("!!! PLUGIN-LOAD PARITY VIOLATION !!!", file=sys.stderr)
    print(f"  loaded only on MAIN:     {sorted(main_only)}", file=sys.stderr)
    print(f"  loaded only on WORKTREE: {sorted(work_only)}", file=sys.stderr)
    sys.exit(2)

# Also assert every run loaded the same set as its first
for label, rows in (("MAIN", main), ("WORKTREE", work)):
    baseline = set(rows[0]["loaded"])
    for i, r in enumerate(rows):
        if set(r["loaded"]) != baseline:
            print(
                f"!!! {label} run {i} loaded a different plugin set than run 0",
                file=sys.stderr,
            )
            sys.exit(2)

n_loaded = len(main_loaded)
print(
    f"Plugin-load parity: both trees loaded the SAME {n_loaded} plugins on every run\n"
)


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


ms = stats(main)
ws = stats(work)


def fmt(s: dict) -> str:
    return (
        f"mean {s['mean_ms']:>7.1f}ms  "
        f"median {s['median_ms']:>7.1f}ms  "
        f"stdev {s['stdev_ms']:>5.1f}ms  "
        f"min {s['min_ms']:>7.1f}ms  "
        f"max {s['max_ms']:>7.1f}ms  "
        f"modules {s['modules']:>6.0f}"
    )


print(f"MAIN     : {fmt(ms)}")
print(f"WORKTREE : {fmt(ws)}")

d_mean = ws["mean_ms"] - ms["mean_ms"]
d_median = ws["median_ms"] - ms["median_ms"]
d_min = ws["min_ms"] - ms["min_ms"]

print(f"\nDelta mean   : {d_mean:+.1f}ms  ({100 * d_mean / ms['mean_ms']:+.2f}%)")
print(f"Delta median : {d_median:+.1f}ms  ({100 * d_median / ms['median_ms']:+.2f}%)")
print(f"Delta min    : {d_min:+.1f}ms  ({100 * d_min / ms['min_ms']:+.2f}%)")

# Noise-floor check: is the delta larger than the combined stddev?
combined_stdev = (ms["stdev_ms"] ** 2 + ws["stdev_ms"] ** 2) ** 0.5
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
