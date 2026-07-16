"""Hide whitespace-only HTML comments from streamed thinking display.

The filter is stateful because model deltas may split ``<!-- -->`` at any
character boundary. It changes presentation only; model history and response
content remain untouched.
"""

from __future__ import annotations

from threading import Lock

from code_puppy.callbacks import register_callback

_OPEN = "<!--"
_CLOSE = "-->"
_pending: dict[tuple[object, int], str] = {}
_lock = Lock()


def _prefix_suffix_length(text: str, marker: str) -> int:
    """Return the longest suffix of ``text`` that prefixes ``marker``."""
    limit = min(len(text), len(marker) - 1)
    for length in range(limit, 0, -1):
        if text.endswith(marker[:length]):
            return length
    return 0


def _could_complete_empty_comment(body: str) -> bool:
    """Whether an unfinished body is whitespace plus a closing-prefix."""
    return body.lstrip() in ("", "-", "--")


def _pop_trailing_newline(parts: list[str]) -> str:
    """Remove and return one trailing newline from accumulated output."""
    for index in range(len(parts) - 1, -1, -1):
        part = parts[index]
        if not part:
            continue
        if part.endswith("\r\n"):
            parts[index] = part[:-2]
            return "\r\n"
        if part.endswith("\n"):
            parts[index] = part[:-1]
            return "\n"
        break
    return ""


def _held_suffix_length(text: str) -> int:
    """Retain a possible opener and its immediately preceding newline."""
    length = _prefix_suffix_length(text, _OPEN)
    start = len(text) - length
    if start > 0 and text[start - 1] == "\n":
        length += 1
        if start > 1 and text[start - 2] == "\r":
            length += 1
    return length


def _filter_chunk(buffered: str, text: str, *, final: bool) -> tuple[str, str]:
    """Return display-safe output and an incomplete candidate to retain."""
    data = buffered + text
    output: list[str] = []
    position = 0

    while position < len(data):
        opening = data.find(_OPEN, position)
        if opening < 0:
            remainder = data[position:]
            held_length = 0 if final else _held_suffix_length(remainder)
            if held_length:
                output.append(remainder[:-held_length])
                return "".join(output), remainder[-held_length:]
            output.append(remainder)
            break

        output.append(data[position:opening])
        closing = data.find(_CLOSE, opening + len(_OPEN))
        if closing < 0:
            candidate = data[opening:]
            body = candidate[len(_OPEN) :]
            if not final and _could_complete_empty_comment(body):
                newline = _pop_trailing_newline(output)
                return "".join(output), newline + candidate
            output.append(candidate)
            return "".join(output), ""

        body = data[opening + len(_OPEN) : closing]
        if body.strip():
            output.append(data[opening : closing + len(_CLOSE)])
        else:
            _pop_trailing_newline(output)
        position = closing + len(_CLOSE)

    return "".join(output), ""


def _filter_thinking_display(
    text: str,
    *,
    stream_id: object,
    part_index: int,
    final: bool = False,
) -> str:
    """Remove empty comments while retaining incomplete markers across deltas."""
    key = (stream_id, part_index)
    with _lock:
        buffered = _pending.pop(key, "")
        output, remainder = _filter_chunk(buffered, text, final=final)
        if remainder and not final:
            _pending[key] = remainder
        return output


register_callback("thinking_display_filter", _filter_thinking_display)
