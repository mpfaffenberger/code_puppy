"""ACP Agent implementation for Code Puppy.

Bridges Code Puppy's pydantic-ai agent system to the Agent Client Protocol
using the official ``agent-client-protocol`` Python SDK.

This single module replaces the previous 13+ file infrastructure
(stdio_server, acp_server, session_store, event_store, event_types,
tool_approvals, hitl_bridge, filesystem_ops, terminal_ops,
message_utils, run_engine, uvicorn_compat, commands) by leveraging
what the SDK already provides.

Usage:
    from code_puppy.plugins.acp_gateway.agent import CodePuppyAgent
    await run_agent(CodePuppyAgent(), use_unstable_protocol=True)
"""

from __future__ import annotations

import asyncio
import copy
from collections import OrderedDict
import logging
import os
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from code_puppy.plugins.acp_gateway.session_context import session_context

from acp import (
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
    text_block,
    update_agent_message,
    update_agent_thought_text,
    update_plan,
    plan_entry,
    start_tool_call,
    update_tool_call,
    tool_content,
)
from acp.exceptions import RequestError
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    AudioContentBlock,
    AuthenticateResponse,
    AuthMethod,
    AvailableCommand,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    ForkSessionResponse,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    ListSessionsResponse,
    LoadSessionResponse,
    McpServerStdio,
    ModelInfo,
    PermissionOption,
    ResumeSessionResponse,
    ResourceContentBlock,
    SessionCapabilities,
    SessionConfigOption,
    SessionConfigOptionSelect,
    SessionConfigSelectOption,
    SessionForkCapabilities,
    SessionInfo,
    SessionListCapabilities,
    SessionMode,
    SessionResumeCapabilities,
    SessionModelState,
    SessionModeState,
    SetSessionConfigOptionResponse,
    SetSessionModeResponse,
    SetSessionModelResponse,
    SseMcpServer,
    TextContentBlock,
    ToolCallUpdate,
)

logger = logging.getLogger(__name__)

# Wire-level debugging — enable via ACP_DEBUG=1 to log every outbound
# notification and response payload to stderr.
_ACP_DEBUG = os.getenv("ACP_DEBUG", "").lower() in ("1", "true", "yes")


def _log_wire(label: str, payload: Any) -> None:
    """Log a wire-level payload to stderr when ACP_DEBUG is enabled."""
    if not _ACP_DEBUG:
        return
    try:
        if hasattr(payload, "model_dump"):
            data = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        else:
            data = payload
        sys.stderr.write(f"[ACP-DEBUG] {label}: {json.dumps(data, indent=2)}\n")
        sys.stderr.flush()
    except Exception as exc:
        sys.stderr.write(f"[ACP-DEBUG] {label}: <serialize error: {exc}>\n")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_AGENT_NAME = os.getenv("ACP_AGENT_NAME", "code-puppy")

# Maximum number of concurrent sessions before LRU eviction kicks in.
MAX_SESSIONS = int(os.getenv("ACP_MAX_SESSIONS", "100"))
from code_puppy.plugins.acp_gateway.config import ACPConfig as _ACPConfig

# Auth config — single source of truth from config.py
_acp_cfg = _ACPConfig.from_env()
ACP_AUTH_REQUIRED = _acp_cfg.auth_required
ACP_AUTH_TOKEN = _acp_cfg.auth_token

# ---------------------------------------------------------------------------
# Mode definitions — maps Code Puppy permission tiers to ACP SessionMode
# ---------------------------------------------------------------------------

_ACP_MODES: list[SessionMode] = [
    SessionMode(id="read", name="Read Only", description="Exploration and search only"),
    SessionMode(id="write", name="Write", description="File modifications allowed"),
    SessionMode(id="execute", name="Execute", description="Shell commands allowed"),
    SessionMode(id="yolo", name="Full Access", description="All operations auto-approved"),
]

_MODE_IDS = frozenset(m.id for m in _ACP_MODES)
_DEFAULT_MODE = "yolo"

# Tool names that represent potentially dangerous operations.
_DANGEROUS_TOOLS = frozenset({
    # Shell / terminal
    "run_terminal_cmd", "run_command", "execute_command",
    "bash", "shell", "terminal",
    # File mutations
    "write_file", "edit_file", "create_file", "delete_file",
    "apply_diff", "patch_file", "rename_file", "move_file",
})

# Write-class tools (allowed from "write" mode upward).
_WRITE_TOOLS = frozenset({
    "write_file", "edit_file", "create_file", "delete_file",
    "apply_diff", "patch_file", "rename_file", "move_file",
})

# Execute-class tools (allowed from "execute" mode upward).
_EXECUTE_TOOLS = frozenset({
    "run_terminal_cmd", "run_command", "execute_command",
    "bash", "shell", "terminal",
})

# What each mode auto-approves.  ``None`` means *everything*.
_MODE_ALLOWED: dict[str, frozenset[str] | None] = {
    "read": frozenset(),                # nothing dangerous auto-approved
    "write": _WRITE_TOOLS,              # file mutations ok
    "execute": _WRITE_TOOLS | _EXECUTE_TOOLS,  # files + shell ok
    "yolo": None,                       # everything auto-approved
}


def _tool_kind(tool_name: str) -> str:
    """Map a tool name to an ACP ``ToolCallUpdate.kind`` value."""
    if tool_name in _EXECUTE_TOOLS:
        return "execute"
    if tool_name in _WRITE_TOOLS:
        return "edit"
    return "other"


def _get_version() -> str:
    """Return Code Puppy package version or fallback."""
    try:
        from code_puppy import __version__
        return __version__ or "0.0.0-dev"
    except Exception:
        return "0.0.0-dev"


# ---------------------------------------------------------------------------
# Session state (lightweight — SDK handles transport/protocol)
# ---------------------------------------------------------------------------

class _SessionState:
    """Per-session state for multi-turn conversations.

    Tracks pydantic-ai message history, mode, working directory, and
    metadata so successive prompts within the same ACP session share
    conversational context.
    """

    __slots__ = (
        "session_id",
        "agent_name",
        "message_history",
        "mode",
        "cwd",
        "created_at",
        "mcp_servers",
    )

    def __init__(
        self,
        session_id: str,
        agent_name: str = DEFAULT_AGENT_NAME,
        mode: str = _DEFAULT_MODE,
        cwd: str = "",
        mcp_servers: list | None = None,
    ) -> None:
        self.session_id = session_id
        self.agent_name = agent_name
        self.message_history: list = []
        self.mode = mode
        self.cwd = cwd
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.mcp_servers: list | None = mcp_servers


# Per-session model overrides.  Stored externally because _SessionState
# uses __slots__ and adding new slots would break existing pickled sessions.
_session_model_overrides: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(
    prompt: list[
        TextContentBlock
        | ImageContentBlock
        | AudioContentBlock
        | ResourceContentBlock
        | EmbeddedResourceContentBlock
    ],
) -> str:
    """Pull plain text out of ACP content blocks."""
    parts: list[str] = []
    for block in prompt:
        text = (
            block.get("text", "")
            if isinstance(block, dict)
            else getattr(block, "text", "")
        )
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip()


def _safe_serialize_args(args: Any) -> dict:
    """Safely serialize tool args for logging / event payloads."""
    if args is None:
        return {}
    if isinstance(args, dict):
        return {
            k: (str(v)[:200] if isinstance(v, str) and len(str(v)) > 200 else v)
            for k, v in args.items()
        }
    try:
        return {"raw": str(args)[:500]}
    except Exception:
        return {}


def _extract_plan_steps(thinking_content: str) -> list[dict]:
    """Try to extract structured plan steps from agent thinking."""
    steps: list[dict] = []
    patterns = [
        r"(?:^|\n)\s*(\d+)[.)]+\s+(.+)",
        r"(?:^|\n)\s*[Ss]tep\s+(\d+)[:.]+\s*(.+)",
        r"(?:^|\n)\s*[-*]\s+(.+)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, thinking_content)
        if len(matches) >= 2:
            for i, match in enumerate(matches):
                if isinstance(match, tuple):
                    step_num = match[0] if match[0].isdigit() else str(i + 1)
                    desc = match[-1].strip()
                else:
                    step_num = str(i + 1)
                    desc = match.strip()
                steps.append({"step": int(step_num), "description": desc[:200]})
            break
    return steps


def _build_mode_state(current_mode: str) -> SessionModeState:
    """Build a ``SessionModeState`` from the current mode ID."""
    return SessionModeState(
        available_modes=_ACP_MODES,
        current_mode_id=current_mode,
    )


def _build_config_options(current_agent: str = "") -> list[SessionConfigOption]:
    """Build the list of configurable session options exposed via ACP.

    Each option maps to a Code Puppy ``config.py`` primitive.
    The ``current_agent`` parameter reflects the session's active agent.
    """
    options: list[SessionConfigOption] = []
    try:
        from code_puppy import config as cp_config

        # auto_save toggle
        current_auto_save = "true" if cp_config.get_auto_save_session() else "false"
        options.append(
            SessionConfigOption(
                root=SessionConfigOptionSelect(
                    id="auto_save",
                    name="Auto-save sessions",
                    type="select",
                    description="Persist session history automatically after each prompt",
                    current_value=current_auto_save,
                    options=[
                        SessionConfigSelectOption(name="Enabled", value="true"),
                        SessionConfigSelectOption(name="Disabled", value="false"),
                    ],
                )
            )
        )

        # safety_level
        current_safety = cp_config.get_safety_permission_level()
        options.append(
            SessionConfigOption(
                root=SessionConfigOptionSelect(
                    id="safety_level",
                    name="Safety level",
                    type="select",
                    description="Risk threshold for tool execution approval",
                    current_value=current_safety,
                    options=[
                        SessionConfigSelectOption(name="None", value="none"),
                        SessionConfigSelectOption(name="Low", value="low"),
                        SessionConfigSelectOption(name="Medium", value="medium"),
                        SessionConfigSelectOption(name="High", value="high"),
                        SessionConfigSelectOption(name="Critical", value="critical"),
                    ],
                )
            )
        )
    except Exception:
        logger.debug("Could not read Code Puppy config for ACP options", exc_info=True)

    # active_agent selector — populated from discovered agents
    try:
        from code_puppy.plugins.acp_gateway.agent_adapter import (
            discover_agents_sync,
        )

        agents = discover_agents_sync()
        if agents:
            agent_options = [
                SessionConfigSelectOption(
                    name=a.display_name or a.name,
                    value=a.name,
                    description=a.description or "",
                )
                for a in agents
            ]
            effective = current_agent or DEFAULT_AGENT_NAME
            # Ensure current value exists in the list
            valid_values = {o.value for o in agent_options}
            if effective not in valid_values:
                effective = agent_options[0].value

            options.append(
                SessionConfigOption(
                    root=SessionConfigOptionSelect(
                        id="active_agent",
                        name="Active agent",
                        type="select",
                        description="Select the AI agent personality and capabilities",
                        current_value=effective,
                        options=agent_options,
                    )
                )
            )
    except Exception:
        logger.debug("Could not discover agents for config options", exc_info=True)

    return options


def _build_model_state() -> SessionModelState | None:
    """Build a ``SessionModelState`` listing all available LLM models.

    Uses ``ModelFactory.load_config()`` to discover every model the user
    can switch to.  Reads the current model from the ``session_model``
    ContextVar first (per-session override), falling back to the global
    ``get_global_model_name()``.

    Returns ``None`` if models cannot be loaded so the response field
    is simply omitted rather than failing hard.
    """
    try:
        from code_puppy.model_factory import ModelFactory
        from code_puppy.config import get_global_model_name
        from code_puppy.plugins.acp_gateway.session_context import get_session_model

        models_config = ModelFactory.load_config()
        if not models_config:
            return None

        # Per-session model takes precedence over global
        current_model = get_session_model() or get_global_model_name() or ""

        available: list[ModelInfo] = []
        for name, cfg in models_config.items():
            description_parts: list[str] = []
            model_type = cfg.get("type", "") if isinstance(cfg, dict) else ""
            if model_type:
                description_parts.append(model_type)
            ctx = cfg.get("context_length") if isinstance(cfg, dict) else None
            if ctx:
                description_parts.append(f"{ctx:,} ctx")
            available.append(
                ModelInfo(
                    model_id=name,
                    name=name,
                    description=" · ".join(description_parts) if description_parts else None,
                )
            )

        if not available:
            return None

        # If current model is not in the list, fall back to first
        valid_ids = {m.model_id for m in available}
        if current_model not in valid_ids:
            current_model = available[0].model_id

        return SessionModelState(
            available_models=available,
            current_model_id=current_model,
        )
    except Exception:
        logger.debug("Could not build model state for ACP", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# CodePuppyAgent — full ACP Agent protocol implementation
# ---------------------------------------------------------------------------

class CodePuppyAgent(Agent):
    """ACP Agent that bridges to Code Puppy's pydantic-ai agent system.

    Implements the **complete** Agent protocol (SDK v0.10.8).  The SDK
    handles all transport concerns (stdio JSON-RPC, content blocks, etc.).
    This class only contains the *business logic*: loading a Code Puppy
    agent, running a prompt through pydantic-ai, and streaming results
    back through the SDK's ``Client`` interface.
    """

    def __init__(self, default_agent: str = DEFAULT_AGENT_NAME) -> None:
        self._conn: Client | None = None
        self._default_agent = default_agent
        self._sessions: OrderedDict[str, _SessionState] = OrderedDict()
        self._running_tasks: dict[str, asyncio.Task] = {}
        # Stored during initialize for downstream capability checks
        self._client_capabilities: ClientCapabilities | None = None
        self._client_info: Implementation | None = None
        self._authenticated: bool = not ACP_AUTH_REQUIRED

    def _register_session(self, session: _SessionState) -> None:
        """Store a session, evicting the oldest if capacity is exceeded."""
        sid = session.session_id
        if sid in self._sessions:
            self._sessions.move_to_end(sid)
        self._sessions[sid] = session
        # LRU eviction: drop oldest sessions when limit is exceeded
        while len(self._sessions) > MAX_SESSIONS:
            evicted_id, evicted = self._sessions.popitem(last=False)
            logger.info("Session evicted (LRU): %s", evicted_id)
            _session_model_overrides.pop(evicted_id, None)

    # ------------------------------------------------------------------
    # ACP lifecycle
    # ------------------------------------------------------------------

    def on_connect(self, conn: Client) -> None:
        """Called by the SDK when the transport is established."""
        self._conn = conn
        logger.info("ACP connection established")

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        """Handshake — negotiate version and exchange capabilities.

        Stores client capabilities for downstream use (e.g. deciding
        whether to call ``fs/read_text_file`` or ``terminal/create``)
        and returns full agent capabilities.
        """
        self._client_capabilities = client_capabilities
        self._client_info = client_info
        logger.info(
            "ACP initialize: protocol_version=%d, client=%s",
            protocol_version,
            client_info,
        )

        auth_methods: list[AuthMethod] = []
        if ACP_AUTH_REQUIRED:
            auth_methods.append(
                AuthMethod(id="bearer", name="Bearer Token", description="Pre-shared bearer token")
            )

        response = InitializeResponse(
            protocol_version=protocol_version,
            agent_info=Implementation(name="code-puppy", version=_get_version()),
            agent_capabilities=AgentCapabilities(
                load_session=True,
                session_capabilities=SessionCapabilities(
                    fork=SessionForkCapabilities(),
                    list=SessionListCapabilities(),
                    resume=SessionResumeCapabilities(),
                ),
            ),
            auth_methods=auth_methods,
        )
        _log_wire("initialize RESPONSE", response)
        return response

    async def authenticate(
        self,
        method_id: str,
        **kwargs: Any,
    ) -> AuthenticateResponse | None:
        """Verify client identity.

        Currently supports ``bearer`` token validation.  When auth is
        not required (``ACP_AUTH_REQUIRED=false``), this is never called
        by compliant clients because ``initialize`` returns no auth methods.
        """
        if not ACP_AUTH_REQUIRED:
            self._authenticated = True
            return AuthenticateResponse()

        if method_id != "bearer":
            raise RequestError.method_not_found(f"authenticate/{method_id}")

        # The token is expected in _meta or via transport headers.
        # For stdio, the client passes it as a kwarg forwarded by the SDK.
        token = kwargs.get("token", "")
        if not token:
            meta = kwargs.get("_meta", {}) or {}
            token = meta.get("token", "")

        if not ACP_AUTH_TOKEN or token != ACP_AUTH_TOKEN:
            raise RequestError.auth_required("Invalid or missing bearer token")

        self._authenticated = True
        logger.info("Client authenticated via bearer token")
        return AuthenticateResponse()

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        """Create a new conversation session with full mode/config state.

        Available commands are sent as a follow-up notification AFTER the
        response is delivered so the client already knows the session_id.
        """
        session_id = uuid4().hex
        session = _SessionState(
            session_id=session_id,
            agent_name=self._default_agent,
            cwd=cwd,
            mcp_servers=list(mcp_servers) if mcp_servers else None,
        )
        self._register_session(session)
        logger.info("New session: %s (cwd=%s)", session_id, cwd)

        # Fire-and-forget: send available commands AFTER response is written.
        # asyncio.create_task (not deprecated ensure_future) + store ref to
        # prevent garbage collection of the fire-and-forget coroutine.
        loop = asyncio.get_running_loop()
        loop.call_soon(
            lambda sid=session_id: self._running_tasks.setdefault(
                f"_notify_{sid}",
                asyncio.create_task(self._send_available_commands(sid)),
            ),
        )

        response = NewSessionResponse(
            session_id=session_id,
            modes=_build_mode_state(session.mode),
            models=_build_model_state(),
            config_options=_build_config_options(current_agent=session.agent_name) or None,
        )
        _log_wire("new_session RESPONSE", response)
        return response

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> LoadSessionResponse | None:
        """Load a previously persisted session.

        Checks in-memory sessions first, then falls back to Code Puppy's
        ``session_storage`` pickle persistence layer.
        """
        # In-memory hit
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.cwd = cwd
            if mcp_servers:
                session.mcp_servers = list(mcp_servers)
            logger.info("Loaded session %s from memory", session_id)
            return LoadSessionResponse(
                modes=_build_mode_state(session.mode),
                models=_build_model_state(),
                config_options=_build_config_options(current_agent=session.agent_name) or None,
            )

        # Disk persistence
        try:
            from code_puppy import session_storage, config as cp_config

            base_dir = Path(cp_config.AUTOSAVE_DIR)
            history = session_storage.load_session(session_id, base_dir)

            session = _SessionState(
                session_id=session_id,
                agent_name=self._default_agent,
                cwd=cwd,
                mcp_servers=list(mcp_servers) if mcp_servers else None,
            )
            session.message_history = list(history) if history else []
            self._register_session(session)

            logger.info(
                "Loaded session %s from disk (%d messages)",
                session_id,
                len(session.message_history),
            )
            return LoadSessionResponse(
                modes=_build_mode_state(session.mode),
                models=_build_model_state(),
                config_options=_build_config_options(current_agent=session.agent_name) or None,
            )

        except Exception:
            logger.warning("Session %s not found on disk", session_id, exc_info=True)
            return None

    async def list_sessions(
        self,
        cursor: str | None = None,
        cwd: str | None = None,
        **kwargs: Any,
    ) -> ListSessionsResponse:
        """List available sessions (in-memory + persisted on disk).

        Supports cursor-based pagination (page size = 50).
        """
        all_sessions: list[SessionInfo] = []

        # In-memory sessions
        for sid, state in self._sessions.items():
            if cwd and state.cwd != cwd:
                continue
            all_sessions.append(
                SessionInfo(
                    session_id=sid,
                    cwd=state.cwd or "",
                    title=f"Session with {state.agent_name}",
                    updated_at=state.created_at,
                )
            )

        # Persisted sessions from disk
        try:
            from code_puppy import session_storage, config as cp_config

            base_dir = Path(cp_config.AUTOSAVE_DIR)
            disk_names = session_storage.list_sessions(base_dir)
            memory_ids = set(self._sessions.keys())

            for name in disk_names:
                if name in memory_ids:
                    continue
                all_sessions.append(
                    SessionInfo(
                        session_id=name,
                        cwd=cwd or "",
                        title=name,
                    )
                )
        except Exception:
            logger.debug("Could not list disk sessions", exc_info=True)

        # Sort by updated_at descending (most recent first)
        all_sessions.sort(
            key=lambda s: s.updated_at or "",
            reverse=True,
        )

        # Cursor-based pagination
        page_size = 50
        start_idx = 0
        if cursor:
            try:
                start_idx = int(cursor)
            except ValueError:
                start_idx = 0

        page = all_sessions[start_idx : start_idx + page_size]
        next_cursor = (
            str(start_idx + page_size)
            if start_idx + page_size < len(all_sessions)
            else None
        )

        return ListSessionsResponse(sessions=page, next_cursor=next_cursor)

    async def set_session_mode(
        self,
        mode_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> SetSessionModeResponse | None:
        """Switch the operating mode for a session.

        Maps to Code Puppy's permission tiers (read / write / execute / yolo).
        """
        if mode_id not in _MODE_IDS:
            raise RequestError.invalid_params(
                f"Unknown mode: {mode_id}. Valid: {', '.join(sorted(_MODE_IDS))}"
            )

        session = self._sessions.get(session_id)
        if session is None:
            raise RequestError.invalid_params(f"Unknown session: {session_id}")

        session.mode = mode_id
        logger.info("[%s] mode changed to '%s'", session_id, mode_id)

        # Notify client of the mode change
        if self._conn is not None:
            try:
                from acp.schema import CurrentModeUpdate
                await self._conn.session_update(
                    session_id=session_id,
                    update=CurrentModeUpdate(
                        session_update="current_mode_update",
                        current_mode_id=mode_id,
                    ),
                )
            except Exception:
                logger.debug("Failed to send mode update notification", exc_info=True)

        return SetSessionModeResponse()

    async def set_session_model(
        self,
        model_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> SetSessionModelResponse | None:
        """Switch the LLM model for this session only.

        Stores the model override per-session rather than calling the
        global ``set_model_and_reload_agent()``.  The override is read
        by ``_run_agent`` via ``session._model_override`` and pushed
        into the ``session_model`` ContextVar so downstream code
        (``_build_model_state``, tool modules) sees the right model.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise RequestError.invalid_params(f"Unknown session: {session_id}")

        try:
            from code_puppy.model_factory import ModelFactory

            models_config = ModelFactory.load_config()
            if model_id not in models_config:
                available = ", ".join(sorted(models_config.keys())[:10])
                raise RequestError.invalid_params(
                    f"Unknown model: {model_id}. Available: {available}…"
                )

            # Store per-session instead of changing globally
            _session_model_overrides[session_id] = model_id
            logger.info("[%s] per-session model set to '%s'", session_id, model_id)
        except RequestError:
            raise
        except Exception:
            logger.exception("[%s] failed to set model '%s'", session_id, model_id)
            raise RequestError.invalid_params(f"Cannot set model: {model_id}")

        # Notify client of the model change
        if self._conn is not None:
            try:
                from acp.schema import CurrentModelUpdate
                await self._conn.session_update(
                    session_id=session_id,
                    update=CurrentModelUpdate(
                        session_update="current_model_update",
                        current_model_id=model_id,
                    ),
                )
            except Exception:
                logger.debug("Failed to send model update notification", exc_info=True)

        return SetSessionModelResponse()

    async def set_config_option(
        self,
        config_id: str,
        session_id: str,
        value: str,
        **kwargs: Any,
    ) -> SetSessionConfigOptionResponse | None:
        """Update a session configuration option.

        Maps ACP config IDs to Code Puppy's ``config.py`` key-value store.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise RequestError.invalid_params(f"Unknown session: {session_id}")

        try:
            from code_puppy import config as cp_config

            if config_id == "auto_save":
                cp_config.set_auto_save_session(value.lower() in ("true", "1", "yes"))
            elif config_id == "safety_level":
                valid_levels = {"none", "low", "medium", "high", "critical"}
                if value.lower() not in valid_levels:
                    raise RequestError.invalid_params(
                        f"Invalid safety level: {value}. Valid: {', '.join(sorted(valid_levels))}"
                    )
                cp_config.set_value("safety_permission_level", value.lower())
            elif config_id == "active_agent":
                from code_puppy.agents import get_available_agents

                available = get_available_agents()
                if value not in available:
                    raise RequestError.invalid_params(
                        f"Unknown agent: {value}. "
                        f"Available: {', '.join(sorted(available.keys())[:10])}"
                    )
                session.agent_name = value
            else:
                # Generic passthrough for unknown config keys
                cp_config.set_value(config_id, value)

            logger.info("[%s] config '%s' set to '%s'", session_id, config_id, value)

            # Build updated options for the response (pass current agent)
            updated_options = _build_config_options(
                current_agent=session.agent_name,
            )

            # Notify client of the config change
            if self._conn is not None:
                try:
                    from acp.schema import ConfigOptionUpdate
                    await self._conn.session_update(
                        session_id=session_id,
                        update=ConfigOptionUpdate(
                            session_update="config_option_update",
                            config_options=updated_options,
                        ),
                    )
                except Exception:
                    logger.debug("Failed to send config update notification", exc_info=True)

        except RequestError:
            raise
        except Exception:
            logger.exception("[%s] failed to set config '%s'", session_id, config_id)
            raise RequestError.internal_error(f"Failed to set config: {config_id}")

        return SetSessionConfigOptionResponse(
            config_options=_build_config_options(current_agent=session.agent_name),
        )

    async def fork_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> ForkSessionResponse:
        """Fork (deep-copy) an existing session into a new independent session.

        The new session starts with a copy of the parent's message history
        but evolves independently from that point forward (UNSTABLE).
        """
        parent = self._sessions.get(session_id)
        if parent is None:
            raise RequestError.invalid_params(f"Unknown session to fork: {session_id}")

        new_id = uuid4().hex
        child = _SessionState(
            session_id=new_id,
            agent_name=parent.agent_name,
            mode=parent.mode,
            cwd=cwd,
            mcp_servers=list(mcp_servers) if mcp_servers else parent.mcp_servers,
        )
        child.message_history = copy.deepcopy(parent.message_history)
        self._register_session(child)

        logger.info("Forked session %s -> %s (%d messages)", session_id, new_id, len(child.message_history))
        return ForkSessionResponse(
            session_id=new_id,
            modes=_build_mode_state(child.mode),
            models=_build_model_state(),
            config_options=_build_config_options(current_agent=child.agent_name) or None,
        )

    async def resume_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> ResumeSessionResponse:
        """Resume an existing session (in-memory or from disk) (UNSTABLE).

        If the session is in memory it is re-attached; otherwise the
        disk persistence layer is tried via ``load_session``.
        """
        # Try in-memory first
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.cwd = cwd
            if mcp_servers:
                session.mcp_servers = list(mcp_servers)
            logger.info("Resumed session %s from memory", session_id)
            return ResumeSessionResponse(
                modes=_build_mode_state(session.mode),
                models=_build_model_state(),
                config_options=_build_config_options(current_agent=session.agent_name) or None,
            )

        # Try loading from disk
        load_result = await self.load_session(cwd=cwd, session_id=session_id, mcp_servers=mcp_servers)
        if load_result is not None:
            return ResumeSessionResponse(
                modes=load_result.modes,
                models=load_result.models,
                config_options=load_result.config_options,
            )

        raise RequestError.invalid_params(f"Session not found: {session_id}")

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        """Run a Code Puppy agent on the user's prompt.

        Extracts text from the ACP content blocks, loads the
        appropriate pydantic-ai agent, executes the prompt, and
        streams results back via ``session_update``.
        """
        text = _extract_text(prompt)
        if not text:
            await self._send_text(session_id, "No prompt text found in the request.")
            return PromptResponse(stop_reason="end_turn")

        session = self._sessions.get(session_id)
        if session is not None:
            self._sessions.move_to_end(session_id)
        if session is None:
            # Auto-create session for convenience
            session = _SessionState(session_id=session_id, agent_name=self._default_agent)
            self._register_session(session)

        logger.info(
            "[%s] prompt (agent=%s): %s",
            session_id,
            session.agent_name,
            text[:120],
        )

        try:
            # Notify client of active safety mode before execution
            if session.mode != "yolo":
                await self._send_thought(
                    session_id,
                    f"\U0001f512 Mode '{session.mode}' — tool approval is advisory only. "
                    f"Tools will execute and violations will be flagged post-execution. "
                    f"Full HITL blocking requires pydantic-ai tool hooks (planned).",
                )

            result_text, tool_events, was_streamed = await self._run_agent(session, text)

            # Audit: flag tools that would need approval in this mode
            await self._audit_tool_events(session_id, tool_events, session.mode)

            # Stream tool events as thoughts for visibility
            await self._stream_tool_events(session_id, tool_events)

            # Send the final agent response (only if batch — streaming
            # already emitted text chunks incrementally)
            if not was_streamed:
                await self._send_text(session_id, result_text)

            # Auto-persist session if enabled
            await self._auto_persist_session(session)

            return PromptResponse(stop_reason="end_turn")

        except asyncio.CancelledError:
            logger.info("[%s] prompt cancelled", session_id)
            return PromptResponse(stop_reason="cancelled")

        except Exception:
            logger.exception("[%s] prompt failed", session_id)
            await self._send_text(
                session_id,
                f"[error] Agent '{session.agent_name}' encountered an error. "
                f"Check server logs for details.",
            )
            return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Cancel a running prompt."""
        task = self._running_tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()
            logger.info("[%s] cancellation requested", session_id)

    # ------------------------------------------------------------------
    # Extension methods (custom Code Puppy features)
    # ------------------------------------------------------------------

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle custom extension methods.

        Supported extensions:
            - ``x/list-agents``: List available Code Puppy agents.
            - ``x/set-agent``:   Switch the agent for a session.
            - ``x/agent-info``:  Get metadata for a specific agent.
        """
        if method == "x/list-agents":
            return await self._ext_list_agents()
        elif method == "x/set-agent":
            return self._ext_set_agent(params)
        elif method == "x/agent-info":
            return await self._ext_agent_info(params)
        else:
            return {"error": f"Unknown extension method: {method}"}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle custom extension notifications (fire-and-forget)."""
        logger.debug("Extension notification: %s %s", method, params)

    # ------------------------------------------------------------------
    # Core execution bridge to pydantic-ai
    # ------------------------------------------------------------------

    async def _run_agent(
        self,
        session: _SessionState,
        prompt_text: str,
    ) -> tuple[str, list[dict], bool]:
        """Load a Code Puppy agent and execute the prompt through pydantic-ai.

        Headless execution — no signal handlers, no spinners, no keyboard
        listeners.  Restores and persists message history for multi-turn
        conversations within the ACP session.

        Attempts real-time streaming via ``run_stream()`` first, falling
        back to batch ``run()`` when streaming is unavailable.

        Sets session-scoped ContextVars (CWD, model) so that downstream
        tool modules resolve paths and models per-session.

        Returns:
            ``(result_text, tool_events, was_streamed)``
        """
        from code_puppy.agents import load_agent

        # Determine per-session model override (if any)
        _per_session_model: str | None = _session_model_overrides.get(session.session_id)

        with session_context(cwd=session.cwd or None, model=_per_session_model):
            return await self._run_agent_inner(session, prompt_text)

    async def _run_agent_inner(
        self,
        session: _SessionState,
        prompt_text: str,
    ) -> tuple[str, list[dict], bool]:
        """Inner implementation of _run_agent, executed within session context."""
        from code_puppy.agents import load_agent

        agent = load_agent(session.agent_name)

        # Log MCP server passthrough (ACP → Code Puppy conversion is
        # deferred until the MCP lifecycle manager supports dynamic
        # per-session server injection).
        if session.mcp_servers:
            logger.info(
                "[%s] session has %d ACP MCP server(s) attached (passthrough stored)",
                session.session_id,
                len(session.mcp_servers),
            )

        # Build (or reuse) the underlying pydantic-ai Agent
        pydantic_agent = (
            agent.code_generation_agent or agent.reload_code_generation_agent()
        )

        # Restore session history (empty list on first turn)
        agent.set_message_history(session.message_history)
        history = agent.get_message_history()

        # Prepend system prompt on first turn only, mirroring
        # BaseAgent.run_with_mcp behaviour.
        if len(history) == 0:
            from code_puppy.model_utils import prepare_prompt_for_model

            system_prompt = agent.get_full_system_prompt()
            puppy_rules = agent.load_puppy_rules()
            if puppy_rules:
                system_prompt += f"\n{puppy_rules}"

            prepared = prepare_prompt_for_model(
                model_name=agent.get_model_name() or "default",
                system_prompt=system_prompt,
                user_prompt=prompt_text,
                prepend_system_to_user=True,
            )
            prompt_text = prepared.user_prompt

        # ------- streaming path -------
        try:
            return await self._run_agent_streamed(
                pydantic_agent, session, prompt_text, history,
            )
        except (AttributeError, TypeError, NotImplementedError) as exc:
            logger.info(
                "[%s] streaming not available (%s), falling back to batch",
                session.agent_name,
                type(exc).__name__,
            )

        # ------- batch fallback -------
        return await self._run_agent_batch(
            pydantic_agent, agent, session, prompt_text, history,
        )

    async def _run_agent_streamed(
        self,
        pydantic_agent: Any,
        session: _SessionState,
        prompt_text: str,
        history: list,
    ) -> tuple[str, list[dict], bool]:
        """Execute the prompt via ``run_stream()`` and emit chunks in real time."""
        full_text = ""
        async with pydantic_agent.run_stream(
            prompt_text,
            message_history=history,
        ) as stream_result:
            async for chunk in stream_result.stream_text(delta=True):
                if chunk:
                    await self._send_text(session.session_id, chunk)
                    full_text += chunk

            # Persist conversation after the stream is fully consumed
            if hasattr(stream_result, "all_messages"):
                session.message_history = list(stream_result.all_messages())

            logger.debug(
                "[%s] session %s streamed, now has %d messages",
                session.agent_name,
                session.session_id,
                len(session.message_history),
            )

            tool_events = self._extract_tool_events(stream_result)
            return full_text, tool_events, True

    async def _run_agent_batch(
        self,
        pydantic_agent: Any,
        agent: Any,
        session: _SessionState,
        prompt_text: str,
        history: list,
    ) -> tuple[str, list[dict], bool]:
        """Execute the prompt via batch ``run()`` (non-streaming fallback)."""
        result = await pydantic_agent.run(
            prompt_text,
            message_history=history,
        )

        # Persist updated conversation for future turns
        if hasattr(result, "all_messages"):
            session.message_history = list(result.all_messages())
        else:
            session.message_history = agent.get_message_history()

        logger.debug(
            "[%s] session %s now has %d messages",
            session.agent_name,
            session.session_id,
            len(session.message_history),
        )

        text = self._extract_result_text(result)
        tool_events = self._extract_tool_events(result)
        return text, tool_events, False

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    async def _auto_persist_session(self, session: _SessionState) -> None:
        """Save session to disk if auto-save is enabled."""
        try:
            from code_puppy import config as cp_config

            if not cp_config.get_auto_save_session():
                return

            from code_puppy import session_storage

            base_dir = Path(cp_config.AUTOSAVE_DIR)
            base_dir.mkdir(parents=True, exist_ok=True)

            session_storage.save_session(
                history=session.message_history,
                session_name=session.session_id,
                base_dir=base_dir,
                timestamp=datetime.now(timezone.utc).isoformat(),
                token_estimator=lambda msgs: len(str(msgs)) // 4,
                auto_saved=True,
            )

            # Cleanup old sessions
            max_sessions = cp_config.get_max_saved_sessions()
            session_storage.cleanup_sessions(base_dir, max_sessions)

            logger.debug("[%s] session auto-persisted", session.session_id)

        except Exception:
            logger.debug("Auto-persist failed for session %s", session.session_id, exc_info=True)

    # ------------------------------------------------------------------
    # HITL — Human-in-the-loop tool approval
    #
    # CURRENT STATE: Advisory only (post-execution audit).
    # Tools execute freely through pydantic-ai; _audit_tool_events()
    # flags violations after the fact.  Full blocking HITL requires
    # intercepting pydantic-ai tool calls via on_model_response hooks
    # or a custom tool wrapper — planned for a follow-up PR.
    #
    # _request_tool_approval() is implemented and tested but not yet
    # wired into the execution pipeline.
    # ------------------------------------------------------------------

    @staticmethod
    def _should_require_approval(tool_name: str, mode: str) -> bool:
        """Return *True* if *tool_name* requires user approval under *mode*.

        In ``yolo`` mode nothing requires approval.  In stricter modes
        only tools explicitly allowed by the mode tier are auto-approved;
        everything else needs user confirmation.
        """
        allowed = _MODE_ALLOWED.get(mode)
        if allowed is None:          # yolo – everything auto-approved
            return False
        if tool_name not in _DANGEROUS_TOOLS:  # safe tool
            return False
        return tool_name not in allowed

    async def _request_tool_approval(
        self,
        session_id: str,
        tool_name: str,
        tool_call_id: str | None = None,
    ) -> bool:
        """Ask the IDE client to approve a tool invocation.

        Returns ``True`` if the client allows the call (or if no
        connection is available — fail-open to preserve headless
        compatibility).
        """
        if self._conn is None:
            return True

        try:
            tc_id = tool_call_id or tool_name
            tool_call = ToolCallUpdate(
                tool_call_id=tc_id,
                title=tool_name,
                kind=_tool_kind(tool_name),
                status="pending",
            )
            options = [
                PermissionOption(
                    option_id="allow",
                    name="Allow",
                    kind="allow_once",
                ),
                PermissionOption(
                    option_id="deny",
                    name="Deny",
                    kind="reject_once",
                ),
            ]
            resp = await self._conn.request_permission(
                options=options,
                session_id=session_id,
                tool_call=tool_call,
            )
            # DeniedOutcome.outcome == "cancelled"
            if hasattr(resp, "outcome") and hasattr(resp.outcome, "outcome"):
                return resp.outcome.outcome != "cancelled"
            return True
        except Exception:
            logger.debug(
                "Tool approval request failed for %s, auto-approving",
                tool_name,
                exc_info=True,
            )
            return True

    async def _audit_tool_events(
        self,
        session_id: str,
        tool_events: list[dict],
        mode: str,
    ) -> None:
        """After a run, warn about tools that would have needed approval."""
        if mode == "yolo":
            return

        flagged: list[str] = []
        for ev in tool_events:
            if ev.get("type") != "tool_call":
                continue
            name = ev.get("tool_name", "")
            if self._should_require_approval(name, mode):
                flagged.append(name)

        if flagged:
            names = ", ".join(sorted(set(flagged)))
            await self._send_thought(
                session_id,
                f"\u26a0\ufe0f Mode '{mode}' — these tool(s) executed without approval "
                f"(advisory mode): {names}. Full HITL blocking is planned.",
            )

    # ------------------------------------------------------------------
    # Result extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_result_text(result: Any) -> str:
        """Pull text from a pydantic-ai RunResult."""
        if result is None:
            return ""
        # pydantic-ai >= 0.1 uses .output, older uses .data
        output = getattr(result, "output", None)
        if output is not None:
            return str(output)
        data = getattr(result, "data", None)
        if data is not None:
            return str(data)
        return str(result)

    @staticmethod
    def _extract_tool_events(result: Any) -> list[dict]:
        """Extract tool-call events from a pydantic-ai result for ACP visibility."""
        events: list[dict] = []
        try:
            from pydantic_ai.messages import (
                ModelRequest,
                ModelResponse,
                ThinkingPart,
                ToolCallPart,
                ToolReturnPart,
            )

            all_messages_fn = getattr(result, "all_messages", None)
            if all_messages_fn is None:
                return events

            for msg in all_messages_fn():
                if isinstance(msg, ModelResponse):
                    for part in msg.parts:
                        if isinstance(part, ToolCallPart):
                            events.append({
                                "type": "tool_call",
                                "tool_name": part.tool_name,
                                "tool_call_id": getattr(part, "tool_call_id", None),
                                "args": _safe_serialize_args(part.args),
                            })
                        elif isinstance(part, ThinkingPart):
                            content = part.content or ""
                            events.append({
                                "type": "thinking",
                                "content": content[:500],
                            })
                            plan_steps = _extract_plan_steps(content)
                            if plan_steps:
                                events.append({
                                    "type": "plan",
                                    "steps": plan_steps,
                                })
                elif isinstance(msg, ModelRequest):
                    for part in msg.parts:
                        if isinstance(part, ToolReturnPart):
                            events.append({
                                "type": "tool_result",
                                "tool_call_id": getattr(part, "tool_call_id", None),
                                "tool_name": getattr(part, "tool_name", None),
                                "content": str(part.content)[:1000] if part.content else "",
                            })
        except ImportError:
            logger.debug("pydantic_ai messages not available for tool extraction")
        except Exception:
            logger.exception("Error extracting tool events")
        return events

    # ------------------------------------------------------------------
    # Streaming helpers (send updates back to the ACP client)
    # ------------------------------------------------------------------

    async def _send_text(self, session_id: str, text: str) -> None:
        """Send a text message chunk to the client."""
        if self._conn is None:
            logger.warning("No connection — cannot send text")
            return
        chunk = update_agent_message(text_block(text))
        await self._conn.session_update(session_id=session_id, update=chunk)

    async def _send_thought(self, session_id: str, text: str) -> None:
        """Send a thought/reasoning chunk to the client."""
        if self._conn is None:
            return
        chunk = update_agent_thought_text(text)
        await self._conn.session_update(session_id=session_id, update=chunk)

    async def _send_plan(self, session_id: str, steps: list[dict]) -> None:
        """Send a structured plan update to the client."""
        if self._conn is None or not steps:
            return
        entries = [
            plan_entry(
                content=s.get("description", ""),
                status="pending",
            )
            for s in steps
        ]
        await self._conn.session_update(
            session_id=session_id,
            update=update_plan(entries),
        )

    async def _send_available_commands(self, session_id: str) -> None:
        """Send the list of available slash commands to the client.

        Agent switching is handled by the ``active_agent`` config option
        (dropdown selector).  Mode / model switching uses native ACP
        selectors.  This notification is reserved for actual slash
        commands that the user types inline.
        """
        if self._conn is None:
            return
        try:
            from acp.schema import AvailableCommandsUpdate

            commands: list[AvailableCommand] = []
            # Future: add real slash commands here (e.g. /help, /clear)

            update = AvailableCommandsUpdate(
                session_update="available_commands_update",
                available_commands=commands,
            )
            _log_wire("available_commands NOTIFICATION", update)
            await self._conn.session_update(
                session_id=session_id,
                update=update,
            )
        except Exception:
            logger.debug("Failed to send available commands", exc_info=True)

    async def _stream_tool_events(self, session_id: str, events: list[dict]) -> None:
        """Stream tool events as thoughts so the client sees agent activity."""
        if self._conn is None or not events:
            return

        for event in events:
            event_type = event.get("type", "")

            if event_type == "thinking":
                content = event.get("content", "")
                if content:
                    await self._send_thought(session_id, content)

            elif event_type == "tool_call":
                tool_name = event.get("tool_name", "unknown")
                args = event.get("args", {})
                try:
                    chunk = start_tool_call(tool_name)
                    await self._conn.session_update(
                        session_id=session_id, update=chunk
                    )
                except Exception:
                    # Fallback: send as thought if start_tool_call fails
                    await self._send_thought(
                        session_id,
                        f"[tool] {tool_name}({args})",
                    )

            elif event_type == "tool_result":
                tool_name = event.get("tool_name", "unknown")
                content = event.get("content", "")
                try:
                    chunk = update_tool_call(tool_content(content[:500]))
                    await self._conn.session_update(
                        session_id=session_id, update=chunk
                    )
                except Exception:
                    # Fallback: send as thought
                    await self._send_thought(
                        session_id,
                        f"[result] {tool_name}: {content[:200]}",
                    )

            elif event_type == "plan":
                steps = event.get("steps", [])
                if steps:
                    await self._send_plan(session_id, steps)

    # ------------------------------------------------------------------
    # Extension method implementations
    # ------------------------------------------------------------------

    async def _ext_list_agents(self) -> dict[str, Any]:
        """List all available Code Puppy agents."""
        from code_puppy.plugins.acp_gateway.agent_adapter import discover_agents

        agents = await discover_agents()
        return {
            "agents": [
                {
                    "name": a.name,
                    "display_name": a.display_name,
                    "description": a.description,
                }
                for a in agents
            ]
        }

    def _ext_set_agent(self, params: dict[str, Any]) -> dict[str, Any]:
        """Switch the agent for a given session."""
        session_id = params.get("session_id", "")
        agent_name = params.get("agent_name", "")

        if not session_id or not agent_name:
            return {"error": "session_id and agent_name are required"}

        session = self._sessions.get(session_id)
        if session is None:
            return {"error": f"Unknown session: {session_id}"}

        # Validate agent exists in registry
        try:
            from code_puppy.agents import get_available_agents
            available = get_available_agents()
            if agent_name not in available:
                return {
                    "error": f"Unknown agent: {agent_name}. "
                    f"Available: {', '.join(sorted(available.keys())[:10])}"
                }
        except Exception:
            logger.debug("Could not validate agent name", exc_info=True)

        session.agent_name = agent_name
        logger.info("[%s] agent switched to '%s'", session_id, agent_name)
        return {"status": "ok", "agent_name": agent_name}

    async def _ext_agent_info(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get metadata for a specific agent."""
        from code_puppy.plugins.acp_gateway.agent_adapter import build_agent_metadata

        agent_name = params.get("agent_name", self._default_agent)
        metadata = build_agent_metadata(agent_name)
        if metadata is None:
            return {"error": f"Agent not found: {agent_name}"}
        return metadata


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

async def run_code_puppy_agent(agent_name: str = DEFAULT_AGENT_NAME) -> None:
    """Start the Code Puppy ACP agent over stdio.

    This is the primary entry point. The SDK handles the entire
    stdio JSON-RPC transport — we just provide the Agent implementation.
    """
    logger.info("Starting Code Puppy ACP agent (default_agent=%s)", agent_name)
    await run_agent(
        CodePuppyAgent(default_agent=agent_name),
        use_unstable_protocol=True,
    )
