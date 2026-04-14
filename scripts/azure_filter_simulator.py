#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  🛡️  Azure Content Filter Simulator™  🛡️                    ║
║                                                              ║
║  A fake OpenAI-compatible server that simulates Azure's      ║
║  hilariously aggressive content filter.  First request?      ║
║  DENIED.  Second request (the retry)?  Oh sure, here you go! ║
║                                                              ║
║  Use with Code Puppy to verify the content_filter_retry      ║
║  plugin actually works end-to-end.                           ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    # Terminal 1: Start the simulator
    uv run python scripts/azure_filter_simulator.py

    # Terminal 2: In Code Puppy, /model azure-filter-sim, then chat!
    # Watch Terminal 1 — you'll see the filter trigger, then the retry succeed.

    # Cleanup when done:
    uv run python scripts/azure_filter_simulator.py --uninstall
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
import uuid
from collections import defaultdict
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL_KEY = "azure-filter-sim"
MODEL_NAME = "content-filter-simulator-3000"
DEFAULT_PORT = 11444

REFUSAL = "I'm sorry, but I cannot assist with that request."
SUCCESS = (
    "Here's your answer! 🎉  The content filter simulator let this one "
    "through because it was a *retry*.  If you're seeing this, the "
    "`agent_run_result` hook + `content_filter_retry` plugin worked "
    "end-to-end.  Good dog! 🐶"
)

BANNER = r"""
  ╭──────────────────────────────────────────────╮
  │  🛡️  Azure Content Filter Simulator™  🛡️     │
  │                                              │
  │  Every FIRST message  → BLOCKED 🚫           │
  │  Every RETRY message  → ALLOWED ✅           │
  │                                              │
  │  Just like the real thing, except on purpose │
  ╰──────────────────────────────────────────────╯
"""

# ---------------------------------------------------------------------------
# extra_models.json helpers
# ---------------------------------------------------------------------------

EXTRA_MODELS_PATH = pathlib.Path.home() / ".code_puppy" / "extra_models.json"


def _load_extra_models() -> dict:
    if EXTRA_MODELS_PATH.exists():
        with open(EXTRA_MODELS_PATH) as f:
            return json.load(f)
    return {}


def _save_extra_models(models: dict) -> None:
    EXTRA_MODELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXTRA_MODELS_PATH, "w") as f:
        json.dump(models, f, indent=2)


def _model_config(port: int) -> dict:
    return {
        "type": "custom_openai",
        "provider": "content-filter-sim",
        "name": MODEL_NAME,
        "custom_endpoint": {
            "url": f"http://127.0.0.1:{port}/v1/",
            "api_key": "sk-fake-lol-no-auth-needed",
            "ca_certs_path": False,
        },
        "context_length": 8000,
        "supported_settings": ["temperature"],
    }


def install_model(port: int) -> None:
    models = _load_extra_models()
    models[MODEL_KEY] = _model_config(port)
    _save_extra_models(models)
    print(f"✅  Installed '{MODEL_KEY}' → http://127.0.0.1:{port}/v1/")
    print(f"    Config: {EXTRA_MODELS_PATH}")
    print(f"    In Code Puppy:  /model {MODEL_KEY}")


def uninstall_model() -> None:
    models = _load_extra_models()
    if MODEL_KEY in models:
        del models[MODEL_KEY]
        _save_extra_models(models)
        print(f"🗑️   Removed '{MODEL_KEY}' from {EXTRA_MODELS_PATH}")
    else:
        print(f"ℹ️   '{MODEL_KEY}' not found in {EXTRA_MODELS_PATH}")


# ---------------------------------------------------------------------------
# Server helpers (no framework imports at module scope for fast --uninstall)
# ---------------------------------------------------------------------------

_hit_count: dict[str, int] = defaultdict(int)


def _make_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _non_streaming_response(content: str, finish_reason: str = "stop") -> dict:
    return {
        "id": _make_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": len(content.split()),
            "total_tokens": 42 + len(content.split()),
        },
    }


def _sse_line(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _streaming_chunks(content: str, finish_reason: str = "stop"):
    """Yield SSE chunks in OpenAI streaming format."""
    chat_id = _make_id()
    ts = int(time.time())

    # Role chunk
    yield _sse_line({
        "id": chat_id, "object": "chat.completion.chunk", "created": ts,
        "model": MODEL_NAME,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
    })

    # Stream word by word for maximum realism ✨
    for i, word in enumerate(content.split(" ")):
        token = word if i == 0 else f" {word}"
        yield _sse_line({
            "id": chat_id, "object": "chat.completion.chunk", "created": ts,
            "model": MODEL_NAME,
            "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
        })

    # Finish chunk
    yield _sse_line({
        "id": chat_id, "object": "chat.completion.chunk", "created": ts,
        "model": MODEL_NAME,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
    })
    yield "data: [DONE]\n\n"


def _should_block(messages: list[dict[str, Any]]) -> bool:
    """Block the FIRST user turn; allow retries (longer history = retry)."""
    key = str(len(messages))
    _hit_count[key] += 1
    count = _hit_count[key]

    user_msgs = [m for m in messages if m.get("role") == "user"]
    is_retry = len(user_msgs) > 1

    if is_retry:
        print(f"  ✅  ALLOWING  (retry detected — {len(user_msgs)} user msgs, hit #{count})")
        return False
    print(f"  🚫  BLOCKING  (first attempt — {len(user_msgs)} user msg(s), hit #{count})")
    return True


# ---------------------------------------------------------------------------
# ASGI app (raw Starlette — no FastAPI query-param shenanigans)
# ---------------------------------------------------------------------------

def create_app():
    """Build a Starlette ASGI app. No Pydantic model magic, just raw JSON."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, StreamingResponse
    from starlette.routing import Route

    async def chat_completions(request: Request):
        body = await request.json()
        messages = body.get("messages", [])
        stream = body.get("stream", False)

        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "<no user message>",
        )
        print(f"\n📨  Request: \"{last_user[:80]}{'…' if len(last_user) > 80 else ''}\"")

        blocked = _should_block(messages)
        content = REFUSAL if blocked else SUCCESS
        finish = "content_filter" if blocked else "stop"

        if stream:
            return StreamingResponse(
                _streaming_chunks(content, finish),
                media_type="text/event-stream",
            )
        return JSONResponse(_non_streaming_response(content, finish))

    async def list_models(request: Request):
        return JSONResponse({
            "object": "list",
            "data": [{
                "id": MODEL_NAME,
                "object": "model",
                "owned_by": "azure-content-filter-simulator",
            }],
        })

    return Starlette(routes=[
        Route("/v1/chat/completions", chat_completions, methods=["POST"]),
        Route("/v1/models", list_models),
    ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Azure Content Filter Simulator™ — a fake OpenAI server for testing",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--uninstall", action="store_true",
        help=f"Remove '{MODEL_KEY}' from extra_models.json and exit",
    )
    parser.add_argument(
        "--install-only", action="store_true",
        help="Write model config to extra_models.json and exit (don't start server)",
    )
    args = parser.parse_args()

    if args.uninstall:
        uninstall_model()
        return

    if args.install_only:
        install_model(args.port)
        return

    # Install model config + start server
    print(BANNER)
    install_model(args.port)
    print(f"\n🚀  Starting server on http://127.0.0.1:{args.port}/v1/")
    print(f"    Switch model:  /model {MODEL_KEY}")
    print(f"    Then just chat — watch the filter trigger + retry!\n")

    import uvicorn
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
