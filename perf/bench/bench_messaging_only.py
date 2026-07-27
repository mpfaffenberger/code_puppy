"""Measure the cost of ``import code_puppy.messaging`` in isolation.

This is the tightest, most honest number: how many modules and how much
wall time does a caller pay JUST to bring in the messaging package?

Usage
-----
Compare two checkouts (typically ``main`` vs a feature branch)::

    python perf/bench/bench_messaging_only.py \\
        --before /path/to/checkout-before \\
        --after  /path/to/checkout-after

Optional flags:

    --runs N       measurement runs per tree (default 7)
    --warmup N     discarded warmup runs per tree (default 1)
    --python PATH  Python interpreter to spawn subprocesses with
                   (default: the interpreter running this script)

The script only reads from the two checkouts; it doesn't modify them,
doesn't install anything, and doesn't need them to share a venv --
whatever ``--python`` points at (``sys.executable`` by default) needs
to be able to import ``code_puppy`` from each of the two trees.
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
sys.stdout = open(os.devnull, 'w')
before = set(sys.modules)
t0 = time.perf_counter()
import code_puppy.messaging  # noqa
dt = time.perf_counter() - t0
new = set(sys.modules) - before
sys.stdout = sys.__stdout__
print(json.dumps({{'wall_ms': round(dt * 1000, 2), 'new_modules': len(new)}}))
"""


def run(python: str, repo: str, n: int) -> tuple[list[float], list[int]]:
    times: list[float] = []
    mods: list[int] = []
    for _ in range(n):
        r = subprocess.run(
            [python, "-c", SNIPPET.format(repo=repo)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            print(
                f"[bench] subprocess failed (repo={repo}): {r.stderr[-300:]}",
                file=sys.stderr,
            )
            continue
        for line in reversed(r.stdout.strip().splitlines()):
            try:
                d = json.loads(line)
                times.append(d["wall_ms"])
                mods.append(d["new_modules"])
                break
            except json.JSONDecodeError:
                continue
    return times, mods


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
    p.add_argument("--runs", type=int, default=7, help="measurement runs per tree")
    p.add_argument(
        "--warmup", type=int, default=1, help="warmup runs per tree (discarded)"
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
    print(f"[bench] runs={args.runs}, warmup={args.warmup}\n")

    # discard warmup
    run(args.python, str(before), n=args.warmup)
    run(args.python, str(after), n=args.warmup)

    bt, bm = run(args.python, str(before), n=args.runs)
    at, am = run(args.python, str(after), n=args.runs)

    if len(bt) < 1 or len(at) < 1:
        print(
            f"[bench] insufficient samples (before={len(bt)}, after={len(at)})",
            file=sys.stderr,
        )
        return 3

    print(f"import code_puppy.messaging  ({args.runs} fresh subprocesses each)\n")
    print(f"{'':<10} {'wall (mean)':>14} {'wall (min)':>14} {'new_modules':>14}")
    print("-" * 55)
    print(
        f"{'BEFORE':<10} {statistics.mean(bt):>12.1f}ms "
        f"{min(bt):>12.1f}ms {statistics.mean(bm):>12.0f}"
    )
    print(
        f"{'AFTER':<10} {statistics.mean(at):>12.1f}ms "
        f"{min(at):>12.1f}ms {statistics.mean(am):>12.0f}"
    )

    d_wall = statistics.mean(at) - statistics.mean(bt)
    d_mods = statistics.mean(am) - statistics.mean(bm)
    print(
        f"\nDelta wall (mean): {d_wall:+.1f}ms  "
        f"({100 * (statistics.mean(at) / statistics.mean(bt) - 1):+.1f}%)"
    )
    print(
        f"Delta modules:     {d_mods:+.0f}  "
        f"({100 * (statistics.mean(am) / statistics.mean(bm) - 1):+.1f}%)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
