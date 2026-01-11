"""Code Puppy REST API module.

This module provides a FastAPI-based REST API for Code Puppy configuration,
sessions, commands, and real-time WebSocket communication.

Exports:
    create_app: Factory function to create the FastAPI application
    main: Entry point to run the server
"""

from code_puppy.api.app import create_app

__all__ = ["create_app"]
