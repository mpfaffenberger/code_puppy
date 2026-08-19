"""Version-independent unpickling of legacy session files.

Old session ``.pkl`` files contain pickled pydantic-ai v1 objects. After the
pydantic-ai 2.x upgrade those class paths may not import (or may import with
incompatible shapes), so migration must NEVER unpickle the real classes.
Instead, :class:`SurrogateUnpickler` substitutes a generated *surrogate* type
for every non-allowlisted class: a dumb attribute bag that records the
original module, qualname, and captured state. :func:`normalize_history` then
maps that surrogate graph onto plain JSON dicts matching the
``ModelMessagesTypeAdapter`` schema.

HARD RULE: this module must stay stdlib-only. It must never import
``pydantic_ai`` (directly or transitively) -- there is a guard test for this.
Validation against the real schema happens in the caller layer
(``session_format_migration``), not here.
"""

from __future__ import annotations

import base64
import io
import logging
import pickle
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Dict, List, Tuple

logger = logging.getLogger(__name__)

# find_class resolves ONLY these ``module -> {names}`` pairs to the real
# object; every other global becomes a surrogate. An allowlist, not a denylist
# -- mirroring how the normalizer allowlists known message classes and degrades
# the rest. Two threats a module-level denylist could not close:
#   * re-exported submodules (``collections._sys``, ``uuid.os``) resolved to
#     live module objects, and a following BUILD opcode wrote into their
#     ``__dict__`` (e.g. ``sys.path``) -- in-process code execution.
#   * ``builtins.exit``/``quit``/``help`` resolved to real callables raising
#     ``SystemExit`` (a BaseException) past the migration's ``except Exception``,
#     killing the process.
# Security invariant: no entry resolves to a module or to shared mutable global
# state. BUILD cannot be intercepted -- pickle binds ``load_build`` in a
# dispatch table at class-definition time and the C unpickler exposes only
# ``find_class`` as an override -- so every value BUILD can reach must be made
# safe here: a surrogate, or a leaf constructor whose instances carry no shared
# state.
_ALLOWED_GLOBALS: Dict[str, frozenset] = {
    "builtins": frozenset(
        {"set", "frozenset", "bytearray", "complex", "list", "dict", "tuple"}
    ),
    "collections": frozenset({"OrderedDict", "defaultdict"}),
    "datetime": frozenset({"datetime", "date", "time", "timedelta", "timezone"}),
    "decimal": frozenset({"Decimal"}),
    "fractions": frozenset({"Fraction"}),
    "uuid": frozenset({"UUID"}),
    "zoneinfo": frozenset({"ZoneInfo"}),
    # ``_codecs.encode`` is a function, not a class: it rebuilds bytes/bytearray
    # pickled under protocol 2. Kept for legacy sessions -- a safe codec call.
    "_codecs": frozenset({"encode"}),
}


# Known third-party tzinfo classes rebuilt as stdlib equivalents WITHOUT
# importing their home module. A surrogated tzinfo makes datetime's C
# constructor raise ``TypeError: bad tzinfo state arg``, quarantining the
# whole session. pydantic-core's ``TzInfo`` pickles as ``TzInfo(seconds)``,
# which maps 1:1 onto ``timezone(timedelta(seconds=...))``.
def _tz_from_utc_offset(seconds: float) -> timezone:
    return timezone(timedelta(seconds=seconds))


_TZINFO_EQUIVALENTS: Dict[Tuple[str, str], Callable[..., Any]] = {
    ("pydantic_core._pydantic_core", "TzInfo"): _tz_from_utc_offset,
    ("pydantic_core", "TzInfo"): _tz_from_utc_offset,
}

# Genuine timezone libraries: unpickle their classes for real when the
# library is installed; otherwise fall back to surrogates as usual.
_TZ_LIBRARY_PREFIXES = ("pytz", "dateutil.tz")


class SurrogateBase:
    """Attribute bag standing in for an unimportable pickled class."""

    __cp_module__: str = ""
    __cp_qualname__: str = ""

    def __new__(cls, *args: Any, **kwargs: Any) -> "SurrogateBase":
        # Swallow constructor args from NEWOBJ/NEWOBJ_EX opcodes.
        return object.__new__(cls)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if args:
            self.__dict__["__cp_args__"] = args
        if kwargs:
            self.__dict__.update(kwargs)

    def __setstate__(self, state: Any) -> None:
        if isinstance(state, dict):
            self.__dict__.update(state)
        elif isinstance(state, tuple) and len(state) == 2:
            plain, slots = state
            if isinstance(plain, dict):
                self.__dict__.update(plain)
            if isinstance(slots, dict):
                self.__dict__.update(slots)
        else:
            self.__dict__["__cp_state__"] = state

    def attributes(self) -> Dict[str, Any]:
        """Captured attributes, minus surrogate bookkeeping keys."""
        return {
            key: value
            for key, value in self.__dict__.items()
            if not key.startswith("__cp_")
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Surrogate {self.__cp_module__}.{self.__cp_qualname__}>"


def is_surrogate(obj: Any) -> bool:
    return isinstance(obj, SurrogateBase)


def surrogate_class_name(obj: SurrogateBase) -> str:
    """Bare class name (qualname tail) of the original pickled class."""
    return obj.__cp_qualname__.rsplit(".", 1)[-1]


class SurrogateUnpickler(pickle.Unpickler):
    """``pickle.Unpickler`` that substitutes surrogates for unknown classes."""

    def __init__(self, file: io.IOBase) -> None:
        super().__init__(file)
        self._surrogate_cache: Dict[Tuple[str, str], type] = {}
        self.created_surrogates = False

    def find_class(self, module: str, name: str) -> Any:  # noqa: D102
        # A dotted ``name`` makes the base unpickler (protocol 4+ STACK_GLOBAL)
        # walk attributes from the module, which can reach objects the allowlist
        # never names. Route these to a surrogate.
        if "." in name:
            return self._surrogate_for(module, name)
        if name in _ALLOWED_GLOBALS.get(module, frozenset()):
            return self._tz_tolerant(super().find_class(module, name))
        equivalent = _TZINFO_EQUIVALENTS.get((module, name))
        if equivalent is not None:
            return equivalent
        if any(
            module == prefix or module.startswith(prefix + ".")
            for prefix in _TZ_LIBRARY_PREFIXES
        ):
            try:
                return super().find_class(module, name)
            except Exception:  # noqa: BLE001 - library absent/renamed
                pass
        return self._surrogate_for(module, name)

    def _tz_tolerant(self, obj: Any) -> Any:
        """Belt and braces for tzinfo-bearing constructors.

        If an unknown tzinfo class still slips through as a surrogate,
        constructing the real ``datetime``/``time`` raises ``TypeError``.
        Retry without the tzinfo: a lossy naive timestamp beats losing the
        whole session to quarantine.
        """
        if obj is not datetime and obj is not time:
            return obj

        def construct(*args: Any) -> Any:
            try:
                return obj(*args)
            except TypeError:
                if args and is_surrogate(args[-1]):
                    logger.debug(
                        "Stripped surrogate tzinfo %s.%s from pickled %s",
                        args[-1].__cp_module__,
                        args[-1].__cp_qualname__,
                        obj.__name__,
                    )
                    return obj(*args[:-1])
                raise

        return construct

    def _surrogate_for(self, module: str, name: str) -> type:
        key = (module, name)
        cached = self._surrogate_cache.get(key)
        if cached is None:
            cached = type(
                f"Surrogate_{name.rsplit('.', 1)[-1]}",
                (SurrogateBase,),
                {"__cp_module__": module, "__cp_qualname__": name},
            )
            self._surrogate_cache[key] = cached
        self.created_surrogates = True
        return cached


def load_surrogate_pickle(payload: bytes) -> Tuple[Any, bool]:
    """Unpickle ``payload`` with surrogates. Returns ``(obj, had_surrogates)``."""
    unpickler = SurrogateUnpickler(io.BytesIO(payload))
    obj = unpickler.load()
    return obj, unpickler.created_surrogates


# ---------------------------------------------------------------------------
# Normalizer: surrogate graph -> ModelMessagesTypeAdapter-shaped JSON dicts
# ---------------------------------------------------------------------------


def to_jsonable(value: Any) -> Any:
    """Best-effort conversion of any captured value to plain JSON types."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]
    if is_surrogate(value):
        payload = {"__class__": f"{value.__cp_module__}.{value.__cp_qualname__}"}
        payload.update(
            {key: to_jsonable(item) for key, item in value.attributes().items()}
        )
        return payload
    return str(value)


def _iso_or_none(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    return None


def _with_timestamp(part: Dict[str, Any], attrs: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = _iso_or_none(attrs.get("timestamp"))
    if timestamp is not None:
        part["timestamp"] = timestamp
    return part


def _note_part(note: str, *, response_context: bool) -> Dict[str, Any]:
    """Degrade an unmigratable part to a visible-but-harmless text note."""
    if response_context:
        return {"part_kind": "text", "content": note}
    return {"part_kind": "user-prompt", "content": note}


def _user_content(value: Any) -> Any:
    """Normalize UserPromptPart content: str, or list of str/attachment dicts."""
    if isinstance(value, str):
        return value
    if not isinstance(value, (list, tuple)):
        return str(value)
    items: List[Any] = []
    for item in value:
        if isinstance(item, str):
            items.append(item)
        elif is_surrogate(item):
            items.append(_attachment(item))
        else:
            items.append(str(item))
    return items


_URL_KINDS = {
    "ImageUrl": "image-url",
    "AudioUrl": "audio-url",
    "VideoUrl": "video-url",
    "DocumentUrl": "document-url",
}


def _attachment(item: SurrogateBase) -> Any:
    """Map attachment surrogates (BinaryContent, *Url) to schema dicts."""
    name = surrogate_class_name(item)
    attrs = item.attributes()
    if name == "BinaryContent":
        data = attrs.get("data", b"")
        payload: Dict[str, Any] = {
            "kind": "binary",
            "data": base64.b64encode(bytes(data)).decode("ascii")
            if isinstance(data, (bytes, bytearray))
            else str(data),
            "media_type": str(attrs.get("media_type", "application/octet-stream")),
        }
        identifier = attrs.get("identifier")
        if isinstance(identifier, str):
            payload["identifier"] = identifier
        return payload
    if name in _URL_KINDS and isinstance(attrs.get("url"), str):
        return {"kind": _URL_KINDS[name], "url": attrs["url"]}
    return f"[unmigratable attachment {name} omitted]"


def _normalize_part(part: Any, *, response_context: bool) -> Dict[str, Any]:
    if not is_surrogate(part):
        return _note_part(
            f"[unmigratable part {type(part).__name__} omitted]",
            response_context=response_context,
        )

    name = surrogate_class_name(part)
    attrs = part.attributes()

    if name == "SystemPromptPart":
        return _with_timestamp(
            {"part_kind": "system-prompt", "content": str(attrs.get("content", ""))},
            attrs,
        )
    if name == "UserPromptPart":
        return _with_timestamp(
            {
                "part_kind": "user-prompt",
                "content": _user_content(attrs.get("content")),
            },
            attrs,
        )
    if name == "TextPart":
        return {"part_kind": "text", "content": str(attrs.get("content", ""))}
    if name == "ThinkingPart":
        part_dict: Dict[str, Any] = {
            "part_kind": "thinking",
            "content": str(attrs.get("content", "")),
        }
        if isinstance(attrs.get("signature"), str):
            part_dict["signature"] = attrs["signature"]
        if isinstance(attrs.get("provider_name"), str):
            part_dict["provider_name"] = attrs["provider_name"]
        return part_dict
    if name == "ToolCallPart":
        return {
            "part_kind": "tool-call",
            "tool_name": str(attrs.get("tool_name", "")),
            "args": to_jsonable(attrs.get("args")),
            "tool_call_id": str(attrs.get("tool_call_id", "")),
        }
    if name == "ToolReturnPart":
        return _with_timestamp(
            {
                "part_kind": "tool-return",
                "tool_name": str(attrs.get("tool_name", "")),
                "content": to_jsonable(attrs.get("content")),
                "tool_call_id": str(attrs.get("tool_call_id", "")),
            },
            attrs,
        )
    if name == "RetryPromptPart":
        part_dict = {
            "part_kind": "retry-prompt",
            "content": to_jsonable(attrs.get("content")),
            "tool_call_id": str(attrs.get("tool_call_id", "")),
        }
        if isinstance(attrs.get("tool_name"), str):
            part_dict["tool_name"] = attrs["tool_name"]
        return _with_timestamp(part_dict, attrs)

    return _note_part(
        f"[unmigratable part {name} omitted]", response_context=response_context
    )


def _normalize_request(msg: SurrogateBase) -> Dict[str, Any]:
    attrs = msg.attributes()
    parts = attrs.get("parts") or []
    message: Dict[str, Any] = {
        "kind": "request",
        "parts": [_normalize_part(p, response_context=False) for p in parts],
    }
    if isinstance(attrs.get("instructions"), str):
        message["instructions"] = attrs["instructions"]
    return message


def _normalize_response(msg: SurrogateBase) -> Dict[str, Any]:
    attrs = msg.attributes()
    parts = attrs.get("parts") or []
    message: Dict[str, Any] = {
        "kind": "response",
        "parts": [_normalize_part(p, response_context=True) for p in parts],
    }
    if isinstance(attrs.get("model_name"), str):
        message["model_name"] = attrs["model_name"]
    timestamp = _iso_or_none(attrs.get("timestamp"))
    if timestamp is not None:
        message["timestamp"] = timestamp
    if isinstance(attrs.get("provider_name"), str):
        message["provider_name"] = attrs["provider_name"]
    return message


def normalize_history(history: Any) -> List[Dict[str, Any]]:
    """Map a surrogate message graph to adapter-schema JSON message dicts.

    Unknown messages/parts degrade to visible text notes rather than failing
    the whole session -- losing one exotic part beats losing the transcript.
    """
    if not isinstance(history, (list, tuple)):
        raise TypeError(
            f"Session payload is {type(history).__name__}, expected a message list"
        )
    messages: List[Dict[str, Any]] = []
    for item in history:
        if is_surrogate(item):
            name = surrogate_class_name(item)
            if name == "ModelRequest":
                messages.append(_normalize_request(item))
                continue
            if name == "ModelResponse":
                messages.append(_normalize_response(item))
                continue
            note = f"[unmigratable message {name} omitted]"
        else:
            note = f"[unmigratable entry {type(item).__name__} omitted]"
        messages.append(
            {
                "kind": "request",
                "parts": [{"part_kind": "user-prompt", "content": note}],
            }
        )
    return messages
