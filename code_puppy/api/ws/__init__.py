"""WebSocket endpoint handlers package.

Keep package imports lightweight: this module intentionally avoids importing the
large chat handler at package import time so helper submodules such as
``response_frames`` can be imported independently in tests and tooling.
"""

from __future__ import annotations


def register_chat_endpoint(app):
    from code_puppy.api.ws.chat_handler import register_chat_endpoint as _impl

    return _impl(app)


def register_events_endpoint(app):
    from code_puppy.api.ws.events_handler import register_events_endpoint as _impl

    return _impl(app)


def register_health_endpoint(app):
    from code_puppy.api.ws.health_handler import register_health_endpoint as _impl

    return _impl(app)


def __getattr__(name: str):
    if name == "connection_manager":
        from code_puppy.api.ws.connection_manager import connection_manager

        return connection_manager
    raise AttributeError(name)


__all__ = [
    "register_chat_endpoint",
    "register_events_endpoint",
    "register_health_endpoint",
    "connection_manager",
]
