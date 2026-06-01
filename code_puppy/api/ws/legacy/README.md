# Legacy WS Snapshot — Puppy Desk Gate 2

This directory is a reference/rollback copy of `code_puppy.api.ws` captured
before further puppy-desk migration/refactor work.

Rules:

- It is not registered by `setup_websocket()`.
- Existing `/ws/chat` behavior remains provided by `code_puppy.api.ws.chat_handler`.
- Same-route swap must not happen until parity and GUGI validation pass.
- Keep this snapshot until user explicitly approves cleanup.
