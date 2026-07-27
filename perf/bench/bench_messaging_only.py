"""Measure the cost of `import code_puppy.messaging` in isolation.

This is the tightest, most honest number: how many modules and how much
wall time does a plugin pay JUST to bring in the messaging package?
"""

import json
import statistics
import subprocess

VENV = "/Users/t0w0oqh/projects/code_puppy-oss/.venv/bin/python"

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


def run(repo, n=7):
    times, mods = [], []
    for _ in range(n):
        r = subprocess.run(
            [VENV, "-c", SNIPPET.format(repo=repo)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        for line in reversed(r.stdout.strip().splitlines()):
            try:
                d = json.loads(line)
                times.append(d["wall_ms"])
                mods.append(d["new_modules"])
                break
            except json.JSONDecodeError:
                pass
    return times, mods


MAIN = "/Users/t0w0oqh/projects/code_puppy-oss"
WORK = "/Users/t0w0oqh/projects/code_puppy-oss/.worktrees/perf-messaging-tools-decouple"

# discard warmup
run(MAIN, n=1)
run(WORK, n=1)
mt, mm = run(MAIN, n=7)
wt, wm = run(WORK, n=7)

print("import code_puppy.messaging  (7 fresh subprocesses each)\n")
print(f"{'':<10} {'wall (mean)':>14} {'wall (min)':>14} {'new_modules':>14}")
print("-" * 55)
print(
    f"{'MAIN':<10} {statistics.mean(mt):>12.1f}ms {min(mt):>12.1f}ms {statistics.mean(mm):>12.0f}"
)
print(
    f"{'WORKTREE':<10} {statistics.mean(wt):>12.1f}ms {min(wt):>12.1f}ms {statistics.mean(wm):>12.0f}"
)
print(
    f"\nDelta wall (mean): {statistics.mean(wt) - statistics.mean(mt):+.1f}ms  ({100 * (statistics.mean(wt) / statistics.mean(mt) - 1):+.1f}%)"
)
print(
    f"Delta modules:     {statistics.mean(wm) - statistics.mean(mm):+.0f}  ({100 * (statistics.mean(wm) / statistics.mean(mm) - 1):+.1f}%)"
)
