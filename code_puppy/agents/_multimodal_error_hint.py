"""Actionable guidance for llama.cpp multimodal processing failures.

This is diagnostic only: replaying an unchanged request or dropping screenshots
cannot safely repair a server-side decoder failure.
"""

from __future__ import annotations

from code_puppy.i18n import t

_SIGNATURE = "failed to process mtmd chunk"
_MAX_NODES = 32


def multimodal_error_hint(exc: BaseException) -> str | None:
    """Find the known server signature in bounded exception/provider trees.

    Provider errors can arrive inside task groups, wrapper causes, or structured
    SSE bodies. Never interpolate the body (which may contain private input) in
    the hint. Diagnostic inspection must not itself raise.
    """
    pending: list[object] = [exc]
    seen: set[int] = set()
    for _ in range(_MAX_NODES):
        if not pending:
            break
        node = pending.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        try:
            if isinstance(node, str):
                if _SIGNATURE in node.lower():
                    return t("agent.error.multimodal_processing_hint")
            elif isinstance(node, BaseException):
                try:
                    pending.append(str(node))
                except Exception:
                    pass
                for attr in ("__cause__", "__context__", "exceptions", "body"):
                    try:
                        value = getattr(node, attr, None)
                        if value is not None:
                            pending.append(value)
                    except Exception:
                        pass
            elif isinstance(node, dict):
                for key in ("error", "message", "detail"):
                    if key in node:
                        pending.append(node[key])
            elif isinstance(node, (tuple, list)):
                pending.extend(node[:_MAX_NODES])
        except Exception:
            continue
    return None
