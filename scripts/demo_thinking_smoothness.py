"""Live demo of the THINKING-block smooth-stream renderer.

Pumps deliberately *bursty* thinking text (big lumps with pauses between)
through ``ThinkingStreamSmoother`` so you can watch it drain to the terminal
at a buttery, consistent rate -- the way real model thinking deltas do.

Run with::

    python scripts/demo_thinking_smoothness.py            # smoothed (default)
    python scripts/demo_thinking_smoothness.py --raw      # bursty / no smoothing
"""

import argparse
import asyncio
import sys

from rich.console import Console
from rich.markup import escape
from rich.text import Text

from code_puppy.agents.thinking_stream_smoother import ThinkingStreamSmoother

# A few chunky, complex "thoughts" -- delivered as uneven bursts on purpose.
THOUGHT_BURSTS = [
    "Okay, let me reason about this carefully. The user wants to refactor the ",
    "streaming pipeline so that thinking deltas don't stutter. ",
    "First I need to consider where the bottleneck actually is: the model emits "
    "tokens in lumpy bursts -- sometimes 200 chars at once, then a 400ms pause, "
    "then another burst. ",
    "If I print each burst immediately, the human eye perceives jank. ",
    "The fix is a producer/consumer split: feed() appends to a buffer, and a "
    "background task drains it at a steady cadence. ",
    "Now, what drain rate? A fixed chars-per-tick is naive -- if the model races "
    "ahead, latency balloons; if it trickles, we starve. ",
    "So: adaptive. Each tick, emit ceil(len(buffer) / catch_up_ticks), with a "
    "floor so it always creeps forward. That drains the current backlog over a "
    "short window (~0.4s) regardless of burst size. ",
    "Edge cases: markup characters like [bold] must NOT be interpreted -- escape "
    "each chunk. Stream ends abruptly? Flush on close() and on cancellation. ",
    "Multiple thinking parts? Key everything by part index. ",
    "I think that's a clean, DRY, YAGNI-respecting design. Ship it. ",
]

# Approximate inter-burst arrival gaps (seconds) -- intentionally uneven.
BURST_GAPS = [0.05, 0.45, 0.05, 0.6, 0.1, 0.5, 0.05, 0.4, 0.3, 0.0]


def _print_banner(console: Console) -> None:
    console.print()
    console.print(
        Text.from_markup(
            "[bold white on deep_sky_blue4] THINKING [/bold white on deep_sky_blue4] [dim]\u26a1 "
        ),
        end="",
    )


async def run_smoothed(console: Console) -> None:
    _print_banner(console)
    sm = ThinkingStreamSmoother(console)
    sm.start()
    for chunk, gap in zip(THOUGHT_BURSTS, BURST_GAPS):
        sm.feed(chunk)
        if gap:
            await asyncio.sleep(gap)
    await sm.close()
    console.print()


async def run_raw(console: Console) -> None:
    _print_banner(console)
    for chunk, gap in zip(THOUGHT_BURSTS, BURST_GAPS):
        console.print(f"[dim]{escape(chunk)}[/dim]", end="")
        if gap:
            await asyncio.sleep(gap)
    console.print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print bursts immediately (no smoothing) for comparison.",
    )
    args = parser.parse_args()

    console = Console()
    mode = "RAW / bursty" if args.raw else "SMOOTHED"
    console.print(f"\n[bold]Mode:[/bold] {mode}\n")
    runner = run_raw if args.raw else run_smoothed
    asyncio.run(runner(console))


if __name__ == "__main__":
    sys.exit(main())
