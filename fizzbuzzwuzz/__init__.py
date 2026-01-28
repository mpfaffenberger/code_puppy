"""FizzBuzzWuzz - The Ultimate Extensible Number Transformer.

A SOLID-compliant, generator-based FizzBuzzWuzz that makes interview
questions look like child's play.

Quick Start:
    >>> from fizzbuzzwuzz import fizzbuzzwuzz
    >>> for result in fizzbuzzwuzz(1, 15):
    ...     print(result)

Custom Rules:
    >>> from fizzbuzzwuzz import fizzbuzzwuzz, DivisibilityRule
    >>> my_rules = [
    ...     DivisibilityRule(2, 'Even'),
    ...     DivisibilityRule(3, 'Thrice'),
    ... ]
    >>> list(fizzbuzzwuzz(1, 6, rules=my_rules))
    ['1', 'Even', 'Thrice', 'Even', '5', 'EvenThrice']
"""

from .fizzbuzzwuzz import (
    CLASSIC_FIZZBUZZ,
    FIZZBUZZWUZZ,
    FIZZBUZZWUZZBAZZ,
    ContainsDigitRule,
    DivisibilityRule,
    TransformRule,
    all_of,
    analyze_sequence,
    any_of,
    create_rules_from_spec,
    fizzbuzzwuzz,
    fizzbuzzwuzz_list,
    transform_number,
)

__all__ = [
    # Core function
    "fizzbuzzwuzz",
    "fizzbuzzwuzz_list",
    "transform_number",
    # Rules
    "TransformRule",
    "DivisibilityRule",
    "ContainsDigitRule",
    # Presets
    "CLASSIC_FIZZBUZZ",
    "FIZZBUZZWUZZ",
    "FIZZBUZZWUZZBAZZ",
    # Utilities
    "create_rules_from_spec",
    "analyze_sequence",
    "any_of",
    "all_of",
]

__version__ = "1.0.0"
