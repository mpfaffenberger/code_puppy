"""Single source of truth for 'persist a named session and fire plugin hooks.'

Sits between the pure-I/O ``session_storage`` module and the callers that
need session lifecycle orchestration in one place:

- ``cli_runner.execute_single_prompt`` -- headless ``-p -r`` save-back
- ``cli_runner.main`` -- lazy-create on ``-r missing-name``
- ``config.auto_save_session_if_enabled`` -- standard autosave hook firing
- ``command_line.session_commands.handle_dump_context_command`` -- ``/dump_context``

Why a separate module rather than putting this on top of ``session_storage``?
Storage primitives are pure I/O -- they have no business knowing what
``post_autosave`` means or that a plugin system exists. Hoisting that
orchestration into a thin lifecycle module keeps each layer single-purpose and
gives future session hooks (``on_session_create`` and friends) an obvious home.
"""

from __future__ import annotations

import concurrent.futures
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from code_puppy.session_storage import SessionMetadata, save_session

if TYPE_CHECKING:
    from code_puppy.agents.base_agent import BaseAgent

# Write-side validator. Read-side path resolution stays permissive so users
# can keep passing absolute paths to existing ``.pkl`` files -- the lazy-create
# path is the only place we create files from user-supplied strings.
_SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# Reserved prefix for system-generated auto-flavored names. User input matching
# this is rejected so users can never squat on the auto-generated namespace and
# confuse the autosave-menu UX or break TTY-keyed resume.
_RESERVED_PREFIX = "auto_session_"

# Matches the headroom used by ``config.auto_save_session_if_enabled`` so
# plugin authors only have to honour one budget.
_POST_AUTOSAVE_TIMEOUT_S = 4.0


def is_valid_session_name(name: str, *, allow_reserved_prefix: bool = False) -> bool:
    """Return True if ``name`` is a safe slug.

    Bare-slug regex + an explicit reject of all-dot names. All-dot names
    would not actually escape the sessions dir (the ``.pkl`` suffix is
    appended, so ``.`` becomes ``.pkl`` rather than ``.``), but they still
    produce cosmetically broken hidden filenames with no recoverable session
    name and so are rejected on quality-of-life grounds.

    ``allow_reserved_prefix=False`` (default) additionally rejects names
    starting with ``auto_session_`` so user input cannot collide with the
    auto-generated namespace. Call sites validating user input pass the
    default; the stored-name validator (which legitimately sees
    ``auto_session_*`` filenames on disk) passes ``True``.
    """
    if not _SESSION_NAME_RE.match(name):
        return False
    if set(name) <= {"."}:
        return False
    if not allow_reserved_prefix and name.startswith(_RESERVED_PREFIX):
        return False
    return True


def persist_named_session(
    agent: "BaseAgent",
    session_name: str,
    *,
    base_dir: Path,
    auto_saved: bool = False,
    success_message_template: Optional[str] = None,
) -> SessionMetadata:
    """Save ``agent.get_message_history()`` under ``session_name`` and fire hooks.

    ``auto_saved`` distinguishes the originating intent for plugins that care:
    pass ``True`` for system-triggered writes (autosave, the headless
    save-back at end of ``-p``), pass ``False`` for user-intent writes like
    ``/dump_context``. The bit is preserved in ``SessionMetadata`` so
    downstream consumers can filter.

    ``success_message_template`` (optional) is a format string with these
    available substitutions: ``{message_count}``, ``{total_tokens}``,
    ``{pickle_path}``, ``{metadata_path}``, ``{session_name}``. When provided,
    the formatted result is emitted via ``emit_success`` so a caller like
    ``/dump_context`` can keep its existing user-facing line without
    bifurcating the helper. When omitted, no success line is emitted (the
    correct behavior for silent save-back paths like ``-r NAME`` and
    periodic autosave).

    Returns the ``SessionMetadata`` produced by ``save_session`` so callers can
    surface their own UX as well.
    """
    metadata = save_session(
        history=agent.get_message_history(),
        session_name=session_name,
        base_dir=base_dir,
        timestamp=datetime.now().isoformat(),
        token_estimator=agent.estimate_tokens_for_message,
        auto_saved=auto_saved,
    )
    if success_message_template is not None:
        try:
            from code_puppy.messaging import emit_success

            emit_success(
                success_message_template.format(
                    message_count=metadata.message_count,
                    total_tokens=metadata.total_tokens,
                    pickle_path=metadata.pickle_path,
                    metadata_path=metadata.metadata_path,
                    session_name=session_name,
                )
            )
        except (KeyError, IndexError, ValueError):
            # KeyError: template references an unknown {field}.
            # IndexError: positional placeholder out of range.
            # ValueError: bad format spec like "{x:!}". All three are bugs
            # in the caller-supplied template, not transient failures --
            # swallow so the save path keeps running, but DON'T swallow
            # MemoryError / KeyboardInterrupt / etc.
            pass
    # NOTE: deliberately does NOT fire ``fire_post_autosave_callback``.
    # The ``post_autosave`` hook is reserved for the periodic background
    # auto-save path (``config.auto_save_session_if_enabled``); firing it
    # from /dump_context and headless ``-r NAME -p ...`` save-back too
    # would change plugin-visible behavior for callers that registered
    # against the hook (e.g. ``a downstream token-quota plugin``
    # would print the quota line after every explicit /dump_context).
    # Pre-unification semantics: only periodic auto-save fires the hook.
    return metadata


class ResumeTargetError(Exception):
    """Raised by :func:`resolve_or_create_resume_target` for unrecoverable inputs.

    ``message`` is suitable for ``emit_error``; ``hint`` (optional) carries
    a follow-on ``emit_info`` line. The CLI layer is responsible for
    rendering and exiting; this module raises rather than calling
    ``sys.exit`` so the resolver is testable without spawning subprocesses.
    """

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


def resolve_or_create_resume_target(
    resume_target: str,
    *,
    sessions_dir: Path,
    allow_lazy_create: bool,
) -> tuple[str, Path, bool]:
    """Resolve the ``-r`` argument to ``(session_name, session_dir, lazy_created)``.

    Resolution order:

    1. ``<resume_target>`` is a path ending in ``.pkl`` that exists --
       load directly from that file. ``lazy_created=False``.
    2. ``<sessions_dir>/<resume_target>.pkl`` exists -- load that named
       session. ``lazy_created=False``.
    3. ``<resume_target>`` is a path (any extension) that exists -- load it.
       ``lazy_created=False``.
    4. ``<resume_target>`` is a bare slug ending in ``.pkl`` with no path
       separator -- strip the ``.pkl`` suffix and fall through to lazy-create
       under the bare name. Prevents accidental ``foo.pkl.pkl`` creation
       when users instinctively append the extension. Case-sensitive
       match against ``.pkl`` exactly (``Path.suffix`` semantics); ``foo.PKL``
       does NOT normalize -- ``.pkl`` is the documented spelling.
    5. Nothing matched. If ``allow_lazy_create`` is True AND the target is a
       safe slug, lazy-create an empty session under that name in
       ``sessions_dir`` and return ``lazy_created=True``. Otherwise raise
       :class:`ResumeTargetError`.

    Every returning branch validates the returned ``session_name`` against
    ``is_valid_session_name(..., allow_reserved_prefix=True)`` so callers
    (notably ``pin_current_session_name``) can rely on the resolver never
    handing back a pathological name. Pre-existing on-disk files with
    non-slug stems (e.g. legacy ``My Project.pkl`` from old unguarded
    ``/dump_context``) raise :class:`ResumeTargetError` with a hint to
    rename, rather than crashing later inside the pin.

    Branches 1-3 are read-only and intentionally permissive about path shape.
    Branches 4-5 are the only write-side paths, so the bare-slug reserved-
    prefix rule is applied via ``is_valid_session_name`` (default
    ``allow_reserved_prefix=False``) ONLY there -- swapping the order would
    either break legitimate absolute-path resume or weaken the traversal
    guard.
    """
    resume_path = Path(resume_target)
    if resume_path.suffix == ".pkl" and resume_path.exists():
        return _validated_branch_result(
            resume_path.stem, resume_path.parent, False, sessions_dir
        )

    named = sessions_dir / f"{resume_target}.pkl"
    if named.exists():
        return _validated_branch_result(
            resume_target, sessions_dir, False, sessions_dir
        )

    if resume_path.exists():
        return _validated_branch_result(
            resume_path.stem, resume_path.parent, False, sessions_dir
        )

    # Branch 4: bare-name normalization. "foo.pkl" with no path separator
    # and a valid bare-name slug after suffix strip --> treat as "foo".
    # Avoids the historical ``foo.pkl.pkl`` lazy-create bug.
    normalized_target = resume_target
    if (
        resume_path.suffix == ".pkl"
        and "/" not in resume_target
        and "\\" not in resume_target
        and is_valid_session_name(resume_path.stem, allow_reserved_prefix=False)
    ):
        normalized_target = resume_path.stem

    if not allow_lazy_create:
        raise ResumeTargetError(
            f"Resume target not found: {resume_target}",
        )

    # Lazy-create gate: user-input reserved-prefix protection. The
    # post-creation validation below uses allow_reserved_prefix=True
    # (stored-name semantics) so the same name we just allowed in passes
    # the resolver's output guard.
    if not is_valid_session_name(normalized_target, allow_reserved_prefix=False):
        raise ResumeTargetError(
            f"Invalid session name for lazy-create: {normalized_target!r}",
            hint=(
                "Session names must be 1-128 chars of [A-Za-z0-9._-] "
                "and may not start with 'auto_session_' (reserved)."
            ),
        )

    create_empty_session(normalized_target, base_dir=sessions_dir)
    return _validated_branch_result(normalized_target, sessions_dir, True, sessions_dir)


def _validated_branch_result(
    name: str,
    session_dir: Path,
    lazy_created: bool,
    sessions_dir: Path,
) -> tuple[str, Path, bool]:
    """Validate a resolver-output tuple before returning it.

    Closes the contract gap where the resolver was permissive about read
    paths but the singleton ``pin_current_session_name`` is strict --
    without this, a pre-existing legacy file like ``My Project.pkl`` would
    pass the resolver and then crash startup inside the pin. We raise here
    instead so ``cli_runner``'s existing try/except can exit 1 cleanly
    with a useful hint.
    """
    if not is_valid_session_name(name, allow_reserved_prefix=True):
        raise ResumeTargetError(
            f"Session name {name!r} is not a valid slug.",
            hint=(
                f"Rename the file under {sessions_dir} to match "
                f"[A-Za-z0-9._-]{{1,128}} and try again."
            ),
        )
    return name, session_dir, lazy_created


def create_empty_session(session_name: str, *, base_dir: Path) -> SessionMetadata:
    """Materialise an empty named session (used for ``-r missing-name``).

    Goes through ``save_session`` (not a hand-rolled ``write_bytes``) so the
    new file lands with the same atomic-write + metadata-JSON guarantees as
    any other session — which means ``/autosave_load`` and friends won't
    crash on a half-formed lazy-created entry.
    """
    return save_session(
        history=[],
        session_name=session_name,
        base_dir=base_dir,
        timestamp=datetime.now().isoformat(),
        token_estimator=lambda _msg: 0,
        auto_saved=False,
    )


def fire_post_autosave_callback(metadata: SessionMetadata) -> None:
    """Best-effort fire of the ``post_autosave`` callback. Never raises.

    Wrapped in a ``ThreadPoolExecutor`` because ``_trigger_callbacks_sync``
    silently skips async callbacks when invoked from inside a running event
    loop (see ``callbacks.py`` -- the sync trigger only calls ``asyncio.run``
    when no loop is active). The worker thread has no loop, so async plugin
    hooks fire correctly from both sync command handlers and async CLI paths.

    Hook failures are swallowed silently -- post_autosave is a decorative
    plugin surface (quota lines, dashboards) and a misbehaving plugin must
    never poison the save path or surface a user-visible error after a
    successful write. If you want disk-level forensics on plugin failures,
    add them here (and they will apply to every caller -- autosave,
    headless save-back, /dump_context, etc.) rather than at any single
    call site.
    """
    try:
        from code_puppy import callbacks

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                callbacks._trigger_callbacks_sync, "post_autosave", metadata
            )
            future.result(timeout=_POST_AUTOSAVE_TIMEOUT_S)
    except Exception:
        # Hook is decorative; never block the save path on it.
        pass
