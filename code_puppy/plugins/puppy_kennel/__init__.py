"""Mist Memory — local-first memory for Mist.

Inspired by MemKennel's wings → rooms → drawers model, but backed by
SQLite + FTS5 instead of ChromaDB. No daemon, no API key, no cloud,
multi-process safe via WAL mode.
"""
