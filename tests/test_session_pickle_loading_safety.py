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


def test_blocked_builtins_namespace_accessors():
    """builtins accessors that expose module namespaces resolve to surrogates.

    ``find_class`` returns the surrogate class (a ``SurrogateBase``
    subclass), never the real builtin — a pickle calling ``globals()`` on
    load would otherwise reach the unpickler's own module namespace.
    """
    import builtins
    import io

    from code_puppy.session_surrogate_unpickler import SurrogateBase, SurrogateUnpickler

    for name in ("globals", "locals", "vars", "getattr"):
        unpickler = SurrogateUnpickler(io.BytesIO(b""))
        resolved = unpickler.find_class("builtins", name)
        assert resolved is not getattr(builtins, name), name
        assert issubclass(resolved, SurrogateBase), name


def test_build_into_module_namespace_is_refused():
    """A re-exported submodule must resolve to a surrogate, never a live module.

    ``collections._sys`` is the real ``sys`` module. If it resolved to that live
    object, a following BUILD opcode could write into its ``__dict__`` (here
    ``_cp_pwn``) — in-process poisoning. The allowlist routes it to a surrogate,
    so BUILD can only touch that inert bag, and a hostile payload that raises
    must still never mutate ``sys``.
    """
    import sys

    payload = (
        pickle.PROTO
        + bytes([2])
        + b"ccollections\n_sys\n"
        + b"}"
        + b"X"
        + (7).to_bytes(4, "little")
        + b"_cp_pwn"
        + b"\x88"
        + b"s"
        + b"b"
        + b"."
    )

    assert not hasattr(sys, "_cp_pwn")
    try:
        load_surrogate_pickle(payload)
    except Exception:
        pass
    assert not hasattr(sys, "_cp_pwn")


def test_dateutil_tz_reexports_are_surrogates():
    """dateutil.tz re-exports os/sys; those names must not resolve live."""
    import io
    import os
    import sys

    from code_puppy.session_surrogate_unpickler import SurrogateBase, SurrogateUnpickler

    unpickler = SurrogateUnpickler(io.BytesIO(b""))
    for name, real in (("os", os), ("sys", sys)):
        resolved = unpickler.find_class("dateutil.tz", name)
        assert resolved is not real, name
        assert issubclass(resolved, SurrogateBase), name


def test_exit_quit_help_do_not_resolve_to_real_callables():
    """builtins.exit/quit/help must resolve to surrogates, not the real callables.

    The real ones raise ``SystemExit`` (a ``BaseException``) past the migration's
    ``except Exception`` and would kill the process on load.
    """
    import builtins
    import io

    from code_puppy.session_surrogate_unpickler import SurrogateBase, SurrogateUnpickler

    for name in ("exit", "quit", "help"):
        unpickler = SurrogateUnpickler(io.BytesIO(b""))
        resolved = unpickler.find_class("builtins", name)
        assert resolved is not getattr(builtins, name), name
        assert issubclass(resolved, SurrogateBase), name
