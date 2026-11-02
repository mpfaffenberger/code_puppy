"""Opt-in boot timeline recorder (``CODE_PUPPY_BOOT_TRACE``).

Unset/empty/``0``/``off`` disables everything; ``stderr`` streams tagged JSONL
to a dup of fd 2; an absolute path creates a new JSONL file. Anything else is
silently disabled. The variable is read once, at first import, and removed from
``os.environ`` so child processes never inherit it (a ``stderr`` child would
interleave its own trace lines into captured tool output). While disabled this
module imports only ``os`` and every call returns a shared no-op.

Recorder faults never reach callers; exceptions leaving a ``with span(...)``
block always propagate unchanged. Delivery is lossy by design: see
``_boot_trace_sink`` for queue, drop and shutdown semantics.
"""

import os

_ENV_VAR = "CODE_PUPPY_BOOT_TRACE"


def _resolve_target(raw: str | None) -> str | None:
    if not raw or raw in ("0", "off"):
        return None
    if raw == "stderr" or os.path.isabs(raw):
        return raw
    return None


_TARGET = _resolve_target(os.environ.pop(_ENV_VAR, None))

if _TARGET is not None:
    import atexit
    import contextvars
    import hashlib
    import re
    import threading
    import time
    import uuid

    from code_puppy import _boot_trace_sink

    _CURRENT = contextvars.ContextVar("code_puppy_boot_span", default=None)
    _PHASE_RE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")
    _IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
    _NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}")
    _HASHED_RE = re.compile(r"h:[0-9a-f]{16}")
    _SPAN_ID_RE = re.compile(r"[0-9a-f]{1,16}")

_TIERS = ("installed", "builtin", "user", "project")
_OUTCOMES = (
    "ok",
    "error",
    "timeout",
    "tls",
    "dns",
    "other",
    "remote",
    "fallback",
    "unavailable",
    "control_exit",
)
_SKIP_REASONS = (
    "acp",
    "disabled",
    "not_installed",
    "cached",
    "non_tty",
    "env",
    "shadowed",
    "refused",
    "retired",
    "non_interactive",
    "terminal",
)
_MAX_INT = 2**53 - 1
_MAX_NAMES = 128
_HEARTBEAT_INTERVAL_S = 1.0

# Names of the official core-plugin entry points; tests pin this list.
_OFFICIAL_PLUGINS = (
    "acp",
    "agent_skills",
    "agent_creator_skill",
    "attachment_references",
    "aws_bedrock",
    "background_agents",
    "azure_foundry",
    "auto_continue",
    "btw",
    "chatgpt_oauth",
    "claude_code_hooks",
    "claude_code_oauth",
    "code_puppy_agent",
    "computer_use",
    "completion_notification",
    "context_indicator",
    "copilot_auth",
    "customizable_commands",
    "dbos_durable_exec",
    "destructive_command_guard",
    "emoji_filter",
    "empty_html_comment_filter",
    "example_custom_command",
    "execution_environment",
    "file_permission_handler",
    "flux_bootstrap",
    "force_push_guard",
    "fork",
    "frontend_emitter",
    "grok_oauth",
    "herdr",
    "hook_creator",
    "hook_manager",
    "jev_grep",
    "logfire_oauth",
    "logfire_sessions",
    "mcp_binding_prompt",
    "meta_oauth",
    "namespace_skill_search",
    "no_tools",
    "obsidian_agent",
    "ollama",
    "ollama_setup",
    "openrouter_oauth",
    "plugin_list",
    "pop_command",
    "profiles",
    "prompt_newline",
    "prune",
    "puppy_kennel",
    "pstack",
    "puppy_spinner",
    "qa_kitten_skill",
    "quick_resume",
    "resume_hint",
    "review_pr",
    "session_namer",
    "setup_cli",
    "spill",
    "stack_dump",
    "statusline",
    "steer_queue",
    "subagent_panel",
    "switch_agent_resume",
    "theme",
    "timestamp_heartbeat",
    "universal_constructor",
    "web_retriever_skill",
    "wiggum",
    "yolo_cli",
)


def _is_uint(value) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and (0 <= value <= _MAX_INT)
    )


def _valid_unit(n, of) -> bool:
    return _is_uint(n) and _is_uint(of) and n <= of


def _valid_phase(phase) -> bool:
    return (
        isinstance(phase, str)
        and len(phase) <= 64
        and _PHASE_RE.fullmatch(phase) is not None
    )


def _classify(exc: BaseException) -> tuple[str, dict]:
    """Map a leaving exception to ``(terminal kind, attr overrides)``."""
    if isinstance(exc, SystemExit):
        if exc.code is None or exc.code == 0:
            return "end", {"outcome": "control_exit"}
        return "error", {"outcome": "control_exit", "exceptionClass": "SystemExit"}
    name = type(exc).__name__
    extra = {"outcome": "error"}
    if _IDENT_RE.fullmatch(name):
        extra["exceptionClass"] = name
    return "error", extra


class Span:
    """No-op span; also the shared handle returned whenever tracing is off."""

    __slots__ = ()
    id: str | None = None

    def __enter__(self) -> "Span":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def update(self, **attrs) -> None:
        return None

    def set_unit(self, n: int, of: int) -> None:
        return None

    def skip(self, reason: str) -> None:
        return None

    def error(self, exception_class: str) -> None:
        return None


_NOOP = Span()


class _LiveSpan(Span):
    def __init__(self, rec, phase, parent, attrs, unit, root=False):
        self.id = None
        self._rec = rec
        self._phase = phase
        self._explicit_parent = parent
        self._attrs = attrs
        self._unit = unit
        self._fixed_total = unit[1] if unit else None
        self._root = root
        self._parent = None
        self._skip_reason = None
        self._error = False
        self._prev = None
        self._start_ns = 0
        self._started = False
        self._done = False

    def _start(self, push: bool) -> None:
        rec = self._rec
        if not self._root:
            self._parent = rec.resolve_parent(self._explicit_parent)
        self.id = rec.sink.next_span_id()
        self._start_ns = time.monotonic_ns()
        rec.emit(
            self._phase,
            self.id,
            self._parent,
            "start",
            self._start_ns,
            self._attrs,
            unit=self._unit,
        )
        if push:
            self._prev = _CURRENT.get()
            _CURRENT.set(self)
        self._started = True

    def __enter__(self) -> "_LiveSpan":
        try:
            self._start(push=True)
        except Exception:
            pass
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if self._started and not self._root:
                _CURRENT.set(self._prev)
            self.finish(exc)
        except Exception:
            pass
        return False

    def update(self, **attrs) -> None:
        if not self._done:
            self._attrs.update(self._rec.clean_attrs(attrs))

    def set_unit(self, n: int, of: int) -> None:
        if self._done:
            return
        if _valid_unit(n, of) and of == self._fixed_total:
            self._unit = (n, of)
        else:
            self._rec.reject()

    def skip(self, reason: str) -> None:
        if self._done:
            return
        if isinstance(reason, str) and reason in _SKIP_REASONS:
            self._skip_reason = reason
        else:
            self._rec.reject()

    def error(self, exception_class: str) -> None:
        if self._done:
            return
        self._error = True
        self.update(exceptionClass=exception_class)

    def finish(self, exc: BaseException | None = None, exit_code=None) -> None:
        """Emit the single terminal. Precedence: exception > exit code > error > skip."""
        if not self._started or self._done:
            return
        self._done = True
        kind, reason, attrs = "end", None, dict(self._attrs)
        if exc is not None:
            kind, extra = _classify(exc)
            attrs.update(extra)
        elif exit_code:
            kind = "error"
            attrs["outcome"] = "control_exit"
        elif self._error:
            kind = "error"
            attrs.setdefault("outcome", "error")
        elif self._skip_reason is not None:
            kind, reason = "skip", self._skip_reason
        now_ns = time.monotonic_ns()
        self._rec.emit(
            self._phase,
            self.id,
            self._parent,
            kind,
            now_ns,
            attrs,
            dur_ms=(now_ns - self._start_ns) / 1e6,
            unit=self._unit,
            reason=reason,
        )


class _Recorder:
    def __init__(self, target: str) -> None:
        self.t0_ns = time.monotonic_ns()
        self.boot_id = uuid.uuid4().hex
        self.salt = os.urandom(16)
        self.names = set(_OFFICIAL_PLUGINS)
        self.lock = threading.Lock()
        self.began = False
        self.root: _LiveSpan | None = None
        self.root_id: str | None = None
        self.heartbeat = None
        self.sink = _boot_trace_sink.Sink(
            target, boot_id=self.boot_id, t0_ns=self.t0_ns
        )

    def reject(self) -> None:
        try:
            self.sink.record_drop()
        except Exception:
            pass

    def emit(
        self,
        phase,
        span_id,
        parent,
        kind,
        now_ns,
        attrs,
        *,
        dur_ms=None,
        unit=None,
        reason=None,
    ) -> None:
        if self.heartbeat is not None:
            self.heartbeat.note_activity()
        event = {"v": 1, "bootId": self.boot_id, "phase": phase, "span": span_id}
        if parent is not None:
            event["parent"] = parent
        event["kind"] = kind
        event["tMonoMs"] = round((now_ns - self.t0_ns) / 1e6, 3)
        event["tWallMs"] = time.time_ns() // 1_000_000
        if dur_ms is not None:
            event["durMs"] = round(dur_ms, 3)
        event["attrs"] = dict(attrs)
        if unit is not None:
            event["unit"] = {"n": unit[0], "of": unit[1]}
        if reason is not None:
            event["reason"] = reason
        self.sink.offer(event)

    def resolve_parent(self, explicit) -> str | None:
        if explicit is not None:
            if isinstance(explicit, str) and _SPAN_ID_RE.fullmatch(explicit):
                return explicit
            self.reject()
        current = _CURRENT.get()
        return current.id if current is not None else self.root_id

    def _valid_attr(self, key, value) -> bool:
        if key == "plugin":
            return isinstance(value, str) and (
                value in self.names or _HASHED_RE.fullmatch(value) is not None
            )
        if key == "tier":
            return isinstance(value, str) and value in _TIERS
        if key == "count":
            return _is_uint(value)
        if key in ("cached", "network_attempted"):
            return isinstance(value, bool)
        if key == "outcome":
            return isinstance(value, str) and value in _OUTCOMES
        if key == "exceptionClass":
            return isinstance(value, str) and _IDENT_RE.fullmatch(value) is not None
        return False

    def clean_attrs(self, attrs) -> dict:
        if attrs is None:
            return {}
        if not isinstance(attrs, dict):
            self.reject()
            return {}
        clean = {}
        for key, value in attrs.items():
            if key not in _ALLOWED_ATTRS:
                continue  # allowlist filter, not an error
            if self._valid_attr(key, value):
                clean[key] = value
            else:
                self.reject()
        return clean

    def new_span(self, phase, parent, attrs, unit) -> Span:
        if not _valid_phase(phase):
            self.reject()
            return _NOOP
        if unit is not None:
            if isinstance(unit, tuple) and len(unit) == 2 and _valid_unit(*unit):
                unit = (unit[0], unit[1])
            else:
                self.reject()
                unit = None
        return _LiveSpan(self, phase, parent, self.clean_attrs(attrs), unit)

    def begin(self) -> None:
        with self.lock:
            if self.began:
                return
            self.began = True
            root = _LiveSpan(self, "boot", None, {}, None, root=True)
            root._start(push=False)
            self.root, self.root_id = root, root.id
        self.mark("py.main_reached", None, None)
        # Lazy: the heartbeat module is never imported while tracing is off.
        from code_puppy import _boot_trace_heartbeat

        self.heartbeat = _boot_trace_heartbeat.Heartbeat(
            lambda: self.mark("boot.heartbeat", self.root_id, None),
            interval_s=_HEARTBEAT_INTERVAL_S,
        )
        self.heartbeat.start()

    def mark(self, phase, parent, attrs) -> None:
        if not _valid_phase(phase):
            self.reject()
            return
        span_id = self.sink.next_span_id()
        now_ns = time.monotonic_ns()
        self.emit(
            phase,
            span_id,
            self.resolve_parent(parent),
            "mark",
            now_ns,
            self.clean_attrs(attrs),
        )

    def plugin_attrs(self, tier, name) -> dict:
        if not (isinstance(tier, str) and tier in _TIERS and isinstance(name, str)):
            return {}
        if tier in ("installed", "builtin") and name in self.names:
            identity = name
        else:
            material = b"\0".join(
                (self.salt, tier.encode(), name.encode("utf-8", "backslashreplace"))
            )
            identity = "h:" + hashlib.sha256(material).hexdigest()[:16]
        return {"tier": tier, "plugin": identity}

    def register_names(self, names) -> None:
        if not isinstance(names, (tuple, list, set, frozenset)):
            return
        with self.lock:
            for name in names:
                if len(self.names) >= _MAX_NAMES:
                    break
                if isinstance(name, str) and _NAME_RE.fullmatch(name):
                    self.names.add(name)


_ALLOWED_ATTRS = frozenset(
    (
        "plugin",
        "tier",
        "count",
        "cached",
        "network_attempted",
        "outcome",
        "exceptionClass",
    )
)


def _create_recorder() -> "_Recorder | None":
    try:
        rec = _Recorder(_TARGET)
        atexit.register(rec.sink.request_stop)
        return rec
    except Exception:
        return None


_rec = _create_recorder() if _TARGET is not None else None


def begin_boot() -> None:
    """Open the root ``boot`` span once; later calls are no-ops."""
    if _rec is None:
        return
    try:
        _rec.begin()
    except Exception:
        pass


def end_boot(exc: BaseException | None = None, *, exit_code: int | None = None) -> None:
    """Close the root span (idempotent) and drain the writer (bounded wait)."""
    if _rec is None:
        return
    try:
        if _rec.heartbeat is not None:
            _rec.heartbeat.stop()  # before the root terminal
        if _rec.root is not None:
            _rec.root.finish(exc, exit_code)
    except Exception:
        pass
    try:
        _rec.sink.request_stop()
    except Exception:
        pass


def span(
    phase: str,
    *,
    parent: str | None = None,
    attrs: dict | None = None,
    unit: tuple[int, int] | None = None,
) -> Span:
    if _rec is None:
        return _NOOP
    try:
        return _rec.new_span(phase, parent, attrs, unit)
    except Exception:
        return _NOOP


def current_span() -> Span:
    """Innermost open span of this context; never the global root."""
    if _rec is None:
        return _NOOP
    current = _CURRENT.get()
    return _NOOP if current is None else current


def mark(phase: str, *, parent: str | None = None, attrs: dict | None = None) -> None:
    if _rec is None:
        return
    try:
        _rec.mark(phase, parent, attrs)
    except Exception:
        pass


def enabled() -> bool:
    """True when tracing is on (a recorder exists)."""
    return _rec is not None


def plugin_attrs(tier: str, name: str) -> dict:
    """Return ``{"tier", "plugin"}`` with the plugin's privacy-safe identity."""
    if _rec is None:
        return {}
    try:
        return _rec.plugin_attrs(tier, name)
    except Exception:
        return {}


def register_plugin_names(names: tuple[str, ...]) -> None:
    """Extend the reviewed-name registry (cap 128 total); no-op when disabled."""
    if _rec is None:
        return
    try:
        _rec.register_names(names)
    except Exception:
        pass
