"""Serve the Textual TUI to a browser via ``textual-serve``.

``textual-serve`` runs the *same* CooperApp in a subprocess and bridges it to
a browser over a websocket -- one codebase, no rewrite. The server itself runs
a blocking aiohttp loop, so it MUST be started from the synchronous entrypoint
(``main_entry``) rather than inside ``asyncio.run(main())`` -- nesting event
loops would crash.

The subprocess command re-launches Code Puppy with ``--tui``, which forces the
Textual UI regardless of the configured ``ui_mode`` (and works without a TTY,
since textual-serve supplies the web driver).
"""

from __future__ import annotations

import shlex
import sys
from typing import List, Optional


def _build_command() -> str:
    """Shell command textual-serve runs (once per browser session).

    Re-invokes this interpreter as ``python -m code_puppy --tui`` so the child
    boots straight into the Textual app. Paths are quoted to survive spaces.
    """
    return f"{shlex.quote(sys.executable)} -m code_puppy --tui"


def run_web_server(
    host: str = "localhost",
    port: int = 8000,
    public_url: Optional[str] = None,
    *,
    debug: bool = False,
) -> int:
    """Start the web server. Blocks until interrupted. Returns an exit code."""
    try:
        from textual_serve.server import Server
    except ImportError:
        sys.stderr.write(
            "Web serve requires 'textual-serve'. Install it with:\n"
            "    pip install textual-serve\n"
        )
        return 1

    command = _build_command()
    server = Server(
        command,
        host=host,
        port=port,
        title="Code Puppy",
        public_url=public_url,
    )
    url = public_url or f"http://{host}:{port}"
    sys.stderr.write(f"Serving Code Puppy at {url}  (Ctrl+C to stop)\n")
    try:
        server.serve(debug=debug)
    except KeyboardInterrupt:
        return 0
    return 0


def run_web_server_from_args(argv: List[str]) -> int:
    """Parse the serve-mode flags out of ``argv`` and start the server.

    Called from ``main_entry`` when ``--serve`` is present, BEFORE the async
    main() runs, so the blocking aiohttp loop owns the process.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="code-puppy --serve",
        description="Serve the Code Puppy TUI to a web browser.",
    )
    parser.add_argument("--serve", action="store_true", help="Serve the TUI on the web")
    parser.add_argument(
        "--host", default="localhost", help="Bind host (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Bind port (default: 8000)"
    )
    parser.add_argument(
        "--public-url",
        default=None,
        help="Public URL to advertise (e.g. behind a reverse proxy)",
    )
    parser.add_argument(
        "--serve-debug",
        action="store_true",
        help="Run textual-serve in debug mode",
    )
    args, _unknown = parser.parse_known_args(argv)
    return run_web_server(
        host=args.host,
        port=args.port,
        public_url=args.public_url,
        debug=args.serve_debug,
    )
