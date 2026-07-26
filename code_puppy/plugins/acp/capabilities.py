"""ACP capability negotiation, expressed in the official SDK models.

Both sides of an ACP connection describe what they can do. The client sends its
``ClientCapabilities`` (can it read/write files? run terminals?) and expects
our ``AgentCapabilities`` back. The SDK provides typed models for both, so
this module is a thin, declarative mapping — no hand-rolled JSON.

Keeping the shapes here means ``agent.py`` stays about lifecycle, and the one
place we decide "what does Code Puppy advertise" is obvious and reviewable.
"""

from __future__ import annotations

from typing import Tuple

from acp.schema import (
    AgentCapabilities,
    ClientCapabilities,
    PromptCapabilities,
    SessionAdditionalDirectoriesCapabilities,
    SessionCapabilities,
    SessionCloseCapabilities,
    SessionForkCapabilities,
    SessionListCapabilities,
    SessionResumeCapabilities,
)


def agent_capabilities() -> AgentCapabilities:
    """Describe what Code Puppy can do, for the ``initialize`` response.

    * ``prompt_capabilities.embedded_context`` — we splice embedded text
      resources into the prompt (see ``content.py``), so this is honestly
      ``True``. ``image`` is also ``True``: image blocks are decoded into
      ``BinaryContent`` / ``ImageUrl`` attachments (see ``content.py``). Audio
      input is not consumed yet, so ``audio`` stays ``False``.
    * ``load_session`` — we accept ``session/load`` and rehydrate the
      session's persisted history into a fresh agent, so re-opened threads
      continue the real conversation.
    * ``session_capabilities`` — we support ``list``, ``close``, ``fork``
      (in-memory history duplication), ``resume`` (persisted rehydration), and
      ``additional_directories`` (multi-root), all advertised via the SDK's
      marker sub-models.
    """
    return AgentCapabilities(
        prompt_capabilities=PromptCapabilities(
            image=True, audio=False, embedded_context=True
        ),
        load_session=True,
        session_capabilities=SessionCapabilities(
            list=SessionListCapabilities(),
            close=SessionCloseCapabilities(),
            fork=SessionForkCapabilities(),
            resume=SessionResumeCapabilities(),
            additional_directories=SessionAdditionalDirectoriesCapabilities(),
        ),
    )


def client_io_caps(caps: ClientCapabilities | None) -> Tuple[bool, bool, bool]:
    """Return ``(fs_read, fs_write, terminal)`` from the client's capabilities.

    Drives which I/O edges we delegate to the client vs run locally. Defensive: a
    ``None`` blob or a newer client that omits fields degrades to "run
    locally", never to a crash.
    """
    if caps is None:
        return False, False, False
    fs = getattr(caps, "fs", None)
    fs_read = bool(getattr(fs, "read_text_file", False)) if fs else False
    fs_write = bool(getattr(fs, "write_text_file", False)) if fs else False
    terminal = bool(getattr(caps, "terminal", False))
    return fs_read, fs_write, terminal
