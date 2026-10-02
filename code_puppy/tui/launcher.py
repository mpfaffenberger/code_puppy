"""Entry point that boots the Textual UI.

Called from ``cli_runner`` when the resolved UI mode is ``"textual"``. Kept
separate from ``app.py`` so importing the app (e.g. in tests) never triggers
a real terminal session.
"""

from __future__ import annotations

from .app import build_app


async def run_textual_ui(initial_command: str | None = None) -> None:
    """Build and run CooperApp until the user quits.

    Uses Textual's async runner so it cooperates with the existing asyncio
    event loop in ``cli_runner.main``.
    """
    app = build_app(initial_command=initial_command)
    await app.run_async()
