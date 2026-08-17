"""Behavior of ``SurrogateUnpickler`` on globals whose name is dotted.

Protocol 4+ pickles reference globals with a STACK_GLOBAL opcode carrying a
(module, name) pair, and the stdlib unpickler resolves a dotted ``name`` by
walking attributes from the module. ``uuid`` re-exports ``os``, so a name like
``os.system`` reachable from an allowlisted module must not resolve to the real
callable.
"""

import pickle

from code_puppy.session_surrogate_unpickler import (
    is_surrogate,
    load_surrogate_pickle,
)


def _short_binunicode(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return pickle.SHORT_BINUNICODE + bytes([len(encoded)]) + encoded


def _dotted_global_call_pickle(module: str, name: str, argument: str) -> bytes:
    """A protocol-4 pickle that calls ``module.name(argument)`` on load."""
    return (
        pickle.PROTO
        + bytes([4])
        + _short_binunicode(module)
        + _short_binunicode(name)
        + pickle.STACK_GLOBAL
        + _short_binunicode(argument)
        + pickle.TUPLE1
        + pickle.REDUCE
        + pickle.STOP
    )


def test_surrogate_unpickler_does_not_resolve_dotted_names(tmp_path):
    marker = tmp_path / "marker.txt"
    payload = _dotted_global_call_pickle("uuid", "os.system", f"touch {marker}")

    result = None
    try:
        result, _had_surrogates = load_surrogate_pickle(payload)
    except Exception:
        result = None

    assert not marker.exists()
    if result is not None:
        assert is_surrogate(result)
