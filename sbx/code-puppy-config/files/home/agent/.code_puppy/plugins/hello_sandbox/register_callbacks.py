"""Example user plugin seeded by the code-puppy-config sandbox kit.

Demonstrates the one-file plugin pattern: register callbacks at module
scope. Safe to delete.
"""

from code_puppy.callbacks import register_callback


def _on_startup() -> None:
    print("hello_sandbox: Code Puppy running in a Docker sandbox")


register_callback("startup", _on_startup)
