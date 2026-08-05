"""Yantrik Memory — a YantrikDB-backed semantic/learning memory for Code Puppy.

Where the ``puppy_kennel`` plugin stores *verbatim* drawers in SQLite + FTS5,
this plugin layers a **learning** memory on top of YantrikDB:

* Every user turn is logged verbatim as an ``episodic`` memory.
* A local distiller (Ollama) reads the turn and extracts the durable facts /
  preferences worth keeping, writing them as ``semantic`` memories.
* When a new turn *updates* a prior fact, the old fact is superseded via
  ``correct()`` so only the authoritative value surfaces in recall.

Recall is **banded**: a "current" band of authoritative facts/prefs (always
surfaced into the system prompt) and a "history" band of query-relevant
episodic context.

The plugin is **opt-in** — disabled by default. Run ``/yantrik enable`` to
turn it on. If YantrikDB (or its ONNX embedder) isn't installed, the plugin
silently disables itself and never touches the host app.
"""
