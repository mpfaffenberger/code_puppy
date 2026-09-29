"""Resolve tool implementations only when an agent registers them."""

from importlib import import_module


def lazy_registration(module: str, name: str):
    def register(*args, **kwargs):
        return getattr(import_module(module), name)(*args, **kwargs)

    register.__name__ = name
    register.__qualname__ = name
    return register
