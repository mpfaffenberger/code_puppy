#!/usr/bin/env python3
"""CLI entry point for FizzBuzzWuzz.

Usage:
    python -m fizzbuzzwuzz [OPTIONS]

Options:
    --start INT     Starting number (default: 1)
    --end INT       Ending number (default: 100)
    --rules STR     Custom rules like "3:Fizz,5:Buzz,7:Wuzz"
    --analyze       Show frequency analysis instead of sequence
    --one-line      Print all results on one line (comma-separated)
    --help          Show this message

Examples:
    python -m fizzbuzzwuzz
    python -m fizzbuzzwuzz --end 50
    python -m fizzbuzzwuzz --rules "2:Even,3:Odd" --end 20
    python -m fizzbuzzwuzz --analyze --end 1000
"""

import argparse
import sys

from .fizzbuzzwuzz import (
    FIZZBUZZWUZZ,
    analyze_sequence,
    create_rules_from_spec,
    fizzbuzzwuzz,
)


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="fizzbuzzwuzz",
        description="🎵 FizzBuzzWuzz - The Ultimate Number Transformer 🎵",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --end 50              # Classic FizzBuzzWuzz to 50
  %(prog)s --rules "2:Yo,5:Lo"   # Custom rules
  %(prog)s --analyze --end 1000  # Frequency analysis

Made with 🐕 by Code Puppy
        """,
    )

    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="Starting number (default: 1)",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=100,
        help="Ending number (default: 100)",
    )
    parser.add_argument(
        "--rules",
        type=str,
        default=None,
        help='Custom rules in format "divisor:label,..." (default: 3:Fizz,5:Buzz,7:Wuzz)',
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Show frequency analysis instead of sequence",
    )
    parser.add_argument(
        "--one-line",
        action="store_true",
        help="Print all results on one line (comma-separated)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for CLI."""
    parser = create_parser()
    args = parser.parse_args(argv)

    # Parse rules
    if args.rules:
        try:
            rules = create_rules_from_spec(args.rules)
        except (ValueError, IndexError) as e:
            print(f"Error parsing rules: {e}", file=sys.stderr)
            print('Expected format: "3:Fizz,5:Buzz,7:Wuzz"', file=sys.stderr)
            return 1
    else:
        rules = FIZZBUZZWUZZ

    # Analyze mode
    if args.analyze:
        print(f"📊 FizzBuzzWuzz Analysis ({args.start} to {args.end})")
        print("=" * 50)
        stats = analyze_sequence(args.start, args.end, rules)

        # Sort by frequency (most common first)
        sorted_stats = sorted(stats.items(), key=lambda x: -x[1])

        # Separate numeric from non-numeric
        specials = [(k, v) for k, v in sorted_stats if not k.isdigit()]
        numbers = [(k, v) for k, v in sorted_stats if k.isdigit()]

        print("\n🏆 Special Values:")
        for label, count in specials:
            pct = (count / (args.end - args.start + 1)) * 100
            print(f"  {label:20s} : {count:6d} ({pct:5.1f}%)")

        print(f"\n🔢 Plain Numbers: {sum(v for _, v in numbers)} total")
        print(f"\n📈 Total range: {args.end - args.start + 1} numbers")
        return 0

    # Normal output mode
    if args.one_line:
        print(", ".join(fizzbuzzwuzz(args.start, args.end, rules)))
    else:
        for result in fizzbuzzwuzz(args.start, args.end, rules):
            print(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
