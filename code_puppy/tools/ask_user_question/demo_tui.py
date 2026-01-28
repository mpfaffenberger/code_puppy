#!/usr/bin/env python
"""Manual demo script for the ask_user_question TUI.

This is NOT an automated test - it's for interactive visual testing.
Run this script directly to demo the TUI:
    python -m code_puppy.tools.ask_user_question.demo_tui
"""

from .handler import ask_user_question


def main():
    """Run a test of the ask_user_question TUI."""
    print("Testing ask_user_question TUI...")
    print("=" * 50)

    # Test single question, single select
    result = ask_user_question(
        [
            {
                "question": "Which database should we use for this project?",
                "header": "Database",
                "multi_select": False,
                "options": [
                    {
                        "label": "PostgreSQL",
                        "description": "Relational database, ACID compliant, great for complex queries",
                    },
                    {
                        "label": "MongoDB",
                        "description": "Document store, flexible schema, good for rapid iteration",
                    },
                    {
                        "label": "Redis",
                        "description": "In-memory store, ultra-fast, best for caching",
                    },
                    {
                        "label": "SQLite",
                        "description": "Lightweight, file-based, perfect for local development",
                    },
                ],
            }
        ]
    )

    print("\n" + "=" * 50)
    print("Result:")
    print(f"  Answers: {result.answers}")
    print(f"  Cancelled: {result.cancelled}")
    print(f"  Error: {result.error}")
    print(f"  Timed out: {result.timed_out}")


if __name__ == "__main__":
    main()
